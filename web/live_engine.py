"""Runs a real, live TrackingRunner in a background thread so the web
control page can start/stop/configure simulation runs, not just view
past results.

This deliberately imports from simulator/perception/control -- the same
real code path gui/main_window.py drives, not a reimplementation -- so a
run started from the browser behaves identically to one started from the
desktop app. This is the coupling the original read-only dashboard
avoided on purpose (see dashboard_server.py's earlier docstring); it was
traded away deliberately because the product now needs a genuinely
interactive web engine, not just a viewer. Only one run is live at a
time (a single module-level LiveEngine instance) -- this matches "one
simulation engine," and starting a second run while one is active is
rejected (409) rather than silently stopping the first.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict
from typing import List, Optional

from control.run_loop import TrackingRunner
from perception.frame_source import SimulatorFrameSource, VideoFileFrameSource
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene


class LiveEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._runner: Optional[TrackingRunner] = None
        self._frame_source = None
        self._frames_lock = threading.Lock()
        self._new_frames: List[dict] = []
        self._run_name: Optional[str] = None
        self._error: Optional[str] = None
        self._last_result = None

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, config: dict, video_path: Optional[str] = None) -> dict:
        if self.is_running():
            raise RuntimeError("a run is already active -- stop it first")

        self._stop_flag = False
        self._error = None
        self._last_result = None
        with self._frames_lock:
            self._new_frames = []
        run_name = time.strftime("run_%Y%m%d_%H%M%S")
        self._run_name = run_name

        camera = ptz = None
        if video_path:
            frame_source = VideoFileFrameSource(video_path)
        else:
            scene = Scene.from_config(config)
            cam_cfg = config["camera"]
            camera = CameraModel(
                width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                world_x=config["screen"]["width"] / 2, world_y=config["screen"]["height"] / 2,
            )
            ptz = PTZActuator(camera, config["ptz"]["max_pan_speed_deg_s"], config["ptz"]["max_tilt_speed_deg_s"])
            dcfg = DisturbanceConfig.from_config(config)
            engine = SimulatorEngine(scene, camera, dcfg)
            frame_source = SimulatorFrameSource(engine, fps=cam_cfg["update_rate_hz"])
        self._frame_source = frame_source

        ground_truth_fn = (lambda: frame_source.last_ground_truth) if camera is not None else None
        runner = TrackingRunner(config, frame_source, camera=camera, ptz=ptz, ground_truth_fn=ground_truth_fn)

        def on_telemetry(telemetry, frame):
            record = runner._make_frame_record(telemetry, frame)
            with self._frames_lock:
                self._new_frames.append(asdict(record))

        runner.on_telemetry = on_telemetry
        self._runner = runner

        def run_thread():
            try:
                runner.run(stop_flag=lambda: self._stop_flag)
            except Exception as exc:  # surfaced via status() rather than crashing the server
                self._error = str(exc)
            finally:
                if isinstance(frame_source, VideoFileFrameSource):
                    try:
                        frame_source.release()
                    except Exception:
                        pass

        t = threading.Thread(target=run_thread, daemon=True)
        with self._lock:
            self._thread = t
        t.start()
        return {"run_name": run_name}

    def stop(self, output_dir: str) -> dict:
        if self._runner is None:
            raise RuntimeError("no active or completed run to stop")
        self._stop_flag = True
        if self._thread is not None:
            self._thread.join(timeout=15)
        result = self._runner.save_log(output_dir, run_name=self._run_name)
        self._last_result = result
        return {
            "run_name": self._run_name,
            "metrics": result.metrics,
            "json_path": result.json_path,
            "frames_path": result.frames_path,
        }

    def pop_new_frames(self) -> list:
        with self._frames_lock:
            frames, self._new_frames = self._new_frames, []
            return frames

    def status(self) -> dict:
        metrics = self._runner.metrics.finalize() if self._runner is not None else None
        return {
            "running": self.is_running(),
            "run_name": self._run_name,
            "error": self._error,
            "metrics": metrics,
        }


# Module-level singleton: one live engine per server process, matching
# the "one simulation engine" mental model this control page presents.
engine = LiveEngine()
