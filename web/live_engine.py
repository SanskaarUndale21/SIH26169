"""Runs a real, live TrackingRunner in a background thread so the web
console can start/stop/configure simulation runs, not just view past
results.

This deliberately imports from simulator/perception/control -- the same
real code path gui/main_window.py drives, not a reimplementation -- so a
run started from the browser behaves identically to one started from the
desktop app. Only one run is live at a time (a single module-level
LiveEngine instance); starting a second run while one is active is
rejected (409) rather than silently stopping the first.

Besides per-frame telemetry, the engine keeps the latest camera image and
a world-state snapshot (camera boresight + true target positions on the
full screen) so the Live page can show the actual virtual camera feed and
a whole-screen map, not just derived numbers.
"""
from __future__ import annotations

import json
import os
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


class _PacedSource:
    """Wraps a FrameSource so frames come out no faster than its own fps
    (real-time camera behaviour). Processing still happens as fast as it
    can inside each frame period; processing_time_per_frame_ms in the log
    is the honest compute-cost number either way."""

    def __init__(self, inner):
        self.inner = inner
        self._period = 1.0 / max(inner.get_fps(), 1.0)
        self._next = None

    def get_frame(self):
        now = time.perf_counter()
        if self._next is None:
            self._next = now
        wait = self._next - now
        if wait > 0:
            time.sleep(wait)
        self._next = max(self._next + self._period, time.perf_counter() - self._period)
        return self.inner.get_frame()

    def get_fps(self):
        return self.inner.get_fps()

    def is_live(self):
        return self.inner.is_live()

    def __getattr__(self, name):
        return getattr(self.inner, name)


class LiveEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._runner: Optional[TrackingRunner] = None
        self._frames_lock = threading.Lock()
        self._new_frames: List[dict] = []
        self._run_name: Optional[str] = None
        self._error: Optional[str] = None
        self._saved: Optional[dict] = None
        self._snapshot = None      # (image ndarray, frame record dict, world dict)
        self._snapshot_seq = 0
        self._info: dict = {}
        self._output_dir: Optional[str] = None
        self._started_at: Optional[float] = None

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, config: dict, output_dir: str, video_path: Optional[str] = None,
              realtime: bool = True) -> dict:
        if self.is_running():
            raise RuntimeError("a run is already active, stop it first")

        self._stop_flag = False
        self._error = None
        self._saved = None
        self._snapshot = None
        self._output_dir = output_dir
        with self._frames_lock:
            self._new_frames = []
        run_name = time.strftime("run_%Y%m%d_%H%M%S")
        self._run_name = run_name

        camera = ptz = engine = None
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
        source = _PacedSource(frame_source) if realtime else frame_source

        ground_truth_fn = (lambda: frame_source.last_ground_truth) if camera is not None else None
        runner = TrackingRunner(config, source, camera=camera, ptz=ptz, ground_truth_fn=ground_truth_fn)

        screen = config["screen"]
        self._info = {
            "mode": "video" if video_path else "simulator",
            "video_name": os.path.basename(video_path) if video_path else None,
            "realtime": realtime,
            "screen": [screen["width"], screen["height"]],
            "fps_target": frame_source.get_fps(),
            "motion": None if video_path else config["target"].get("motion"),
            "num_targets": None if video_path else config["target"].get("num_targets", 1),
            "preset": config.get("scenario_preset"),
        }

        def on_telemetry(telemetry, frame):
            record = asdict(runner._make_frame_record(telemetry, frame))
            world = None
            if engine is not None:
                fov_w = camera.fov_x_deg * camera.world_px_per_deg
                fov_h = camera.fov_y_deg * camera.world_px_per_deg
                world = {
                    "cam": [camera.world_x, camera.world_y],
                    "fov": [fov_w, fov_h],
                    "targets": [list(t.position(engine.t)) for t in engine.scene.targets],
                }
            with self._frames_lock:
                self._new_frames.append(record)
                self._snapshot = (frame.image, record, world)
                self._snapshot_seq += 1

        runner.on_telemetry = on_telemetry
        self._runner = runner
        self._started_at = time.time()

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
                # Save whether the run was stopped or ended on its own
                # (video file finished), so no run is ever lost.
                try:
                    self._save(config)
                except Exception as exc:
                    self._error = self._error or f"could not save log: {exc}"

        t = threading.Thread(target=run_thread, daemon=True)
        with self._lock:
            self._thread = t
        t.start()
        return {"run_name": run_name, **self._info}

    def _save(self, config: dict):
        if self._runner is None or self._saved is not None or self._runner.metrics.frame_count == 0:
            return
        result = self._runner.save_log(self._output_dir, run_name=self._run_name)
        # scenario snapshot next to the log, so the report page can say
        # exactly what was run
        with open(os.path.join(self._output_dir, f"{self._run_name}_config.json"), "w") as f:
            json.dump({"info": self._info, "config": config}, f, indent=2, default=str)
        self._saved = {
            "run_name": self._run_name,
            "metrics": result.metrics,
            "json_path": result.json_path,
            "frames_path": result.frames_path,
        }

    def stop(self) -> dict:
        if self._runner is None:
            raise RuntimeError("no active or completed run to stop")
        self._stop_flag = True
        if self._thread is not None:
            self._thread.join(timeout=15)
        return self._saved or {"run_name": self._run_name, "metrics": None}

    def pop_new_frames(self) -> list:
        with self._frames_lock:
            frames, self._new_frames = self._new_frames, []
            return frames

    def snapshot(self):
        """(seq, image, record, world) of the most recent frame, or None."""
        with self._frames_lock:
            if self._snapshot is None:
                return None
            return (self._snapshot_seq, *self._snapshot)

    def status(self) -> dict:
        metrics = self._runner.metrics.finalize() if self._runner is not None else None
        return {
            "running": self.is_running(),
            "run_name": self._run_name,
            "error": self._error,
            "saved": self._saved is not None,
            "info": self._info,
            "metrics": metrics,
            "frames": self._runner.metrics.frame_count if self._runner is not None else 0,
        }


# Module-level singleton: one live engine per server process, matching
# the "one simulation engine" mental model the console presents.
engine = LiveEngine()
