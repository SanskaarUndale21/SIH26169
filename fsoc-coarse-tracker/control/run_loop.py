"""Ties Simulator/VideoFile -> Perception+Tracking -> Control+GUI together
for one run. This is the orchestration Section 5's diagram describes;
kept separate from gui/ so it can run headlessly (tests, benchmark matrix)
or be driven by the Qt GUI.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from control.actuator_interface import Actuator, NullActuator, SimulatorActuator
from control.pid_controller import PIDPointingController
from control.search_driver import RasterSweepDriver, SpiralSweepDriver
from perf_logging.performance_logger import RunMetrics, write_run_log
from perception.frame_source import FrameSource
from perception.pipeline import PerceptionTrackingPipeline, Telemetry


@dataclass
class RunResult:
    metrics: dict
    telemetry_log: List[Telemetry] = field(default_factory=list)
    json_path: Optional[str] = None
    csv_path: Optional[str] = None


class TrackingRunner:
    def __init__(self, config: dict, frame_source: FrameSource,
                 camera=None, ptz=None,
                 ground_truth_fn: Optional[Callable[[], list]] = None):
        """camera: simulator.camera_model.CameraModel, only present in
        simulator mode (used to convert pixel error -> degrees for PID and
        to know px_per_deg). ptz: simulator.camera_model.PTZActuator to
        drive, or None for video-file mode (NullActuator)."""
        self.config = config
        self.frame_source = frame_source
        self.camera = camera
        self.pipeline: Optional[PerceptionTrackingPipeline] = None
        self.controller = PIDPointingController(config)
        self.actuator: Actuator = SimulatorActuator(ptz) if ptz is not None else NullActuator()
        self.ground_truth_fn = ground_truth_fn
        self.metrics = RunMetrics()
        self.telemetry_log: List[Telemetry] = []
        self.on_telemetry: Optional[Callable[[Telemetry, "any"], None]] = None

        max_pan = config.get("ptz", {}).get("max_pan_speed_deg_s", 5.0)
        max_tilt = config.get("ptz", {}).get("max_tilt_speed_deg_s", 5.0)
        # Initial acquisition uses an outward spiral centred on the starting
        # boresight (fast for the bounded-radius default spawn -- see
        # scene.py); reacquisition uses a separate spiral instance centred
        # on the IMM's last known position. A raster driver is also
        # available (control/search_driver.py) for exhaustive full-range
        # coverage if a deployment's target spawn distribution needs it.
        self.raster_search = RasterSweepDriver(max_pan, max_tilt)
        self.initial_search = SpiralSweepDriver(min(max_pan, max_tilt))
        self.spiral_search = SpiralSweepDriver(min(max_pan, max_tilt))
        self._prev_lock_state: Optional[str] = None

    def run(self, max_frames: Optional[int] = None, max_duration_s: Optional[float] = None,
            stop_flag: Optional[Callable[[], bool]] = None) -> RunResult:
        frame = self.frame_source.get_frame()
        if frame is None:
            raise RuntimeError("frame source produced no frames")
        self.pipeline = PerceptionTrackingPipeline(self.config, frame.image.shape[1], frame.image.shape[0])

        n = 0
        t_start = time.perf_counter()
        while frame is not None:
            if stop_flag is not None and stop_flag():
                break
            t0 = time.perf_counter()
            telemetry = self.pipeline.process(frame)

            pan_rate = tilt_rate = 0.0
            if self.camera is not None and frame.fov_deg is not None:
                dt_ctrl = 1.0 / max(self.frame_source.get_fps(), 1.0)
                if telemetry.lock_state in ("locked", "acquiring"):
                    px_per_deg_x = self.camera.px_per_deg_x
                    px_per_deg_y = self.camera.px_per_deg_y
                    err_x_deg = (telemetry.predicted_px[0] - frame.image.shape[1] / 2) / px_per_deg_x
                    err_y_deg = (telemetry.predicted_px[1] - frame.image.shape[0] / 2) / px_per_deg_y
                    pan_rate, tilt_rate = self.controller.compute(err_x_deg, err_y_deg, dt_ctrl)
                elif telemetry.lock_state == "reacquiring":
                    if self._prev_lock_state != "reacquiring":
                        self.spiral_search.recenter()
                    pan_rate, tilt_rate = self.spiral_search.next_rate(dt_ctrl)
                    self.controller.reset()
                else:  # searching
                    pan_rate, tilt_rate = self.initial_search.next_rate(dt_ctrl)
                    self.controller.reset()
                self.actuator.command(pan_rate, tilt_rate, dt_ctrl)
                telemetry.pointing_command_deg = (pan_rate, tilt_rate)
                self._prev_lock_state = telemetry.lock_state

            proc_ms = (time.perf_counter() - t0) * 1000.0

            tracking_error = self._tracking_error(telemetry)
            self.metrics.record_frame(telemetry.timestamp, telemetry.lock_state, tracking_error, proc_ms)
            self.telemetry_log.append(telemetry)
            if self.on_telemetry:
                self.on_telemetry(telemetry, frame)

            n += 1
            if max_frames is not None and n >= max_frames:
                break
            if max_duration_s is not None and (time.perf_counter() - t_start) >= max_duration_s:
                break
            frame = self.frame_source.get_frame()

        result_metrics = self.metrics.finalize()
        return RunResult(metrics=result_metrics, telemetry_log=self.telemetry_log)

    def _tracking_error(self, telemetry: Telemetry) -> Optional[float]:
        if self.ground_truth_fn is None:
            return None
        gts = self.ground_truth_fn()
        if not gts:
            return None
        px, py = telemetry.predicted_px
        return min(math.hypot(px - gx, py - gy) for gx, gy in gts)

    def save_log(self, output_dir: str, run_name: Optional[str] = None, metrics: Optional[dict] = None) -> RunResult:
        m = metrics or self.metrics.finalize()
        json_path, csv_path = write_run_log(m, output_dir, run_name)
        return RunResult(metrics=m, telemetry_log=self.telemetry_log, json_path=json_path, csv_path=csv_path)
