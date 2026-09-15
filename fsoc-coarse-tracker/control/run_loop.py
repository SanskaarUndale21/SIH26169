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
from control.stepper import PointingStepper
from perf_logging.performance_logger import RunMetrics, write_run_log
from perception.frame_source import FrameSource
from perception.pipeline import PerceptionTrackingPipeline, Telemetry
from simulator.link_budget import (LinkBudgetConfig, is_handoff_ready, pointing_loss_db,
                                    px_error_to_angular_error)


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
        # PointingStepper owns the PID controller + hybrid spiral/raster
        # search logic; shared with gui/main_window.py so both entry
        # points drive the PTZ identically (see control/stepper.py).
        self.stepper = PointingStepper(config, camera) if camera is not None else None
        self.actuator: Actuator = SimulatorActuator(ptz) if ptz is not None else NullActuator()
        self.ground_truth_fn = ground_truth_fn
        self.link_cfg = LinkBudgetConfig.from_config(config)
        self.metrics = RunMetrics()
        self.telemetry_log: List[Telemetry] = []
        self.on_telemetry: Optional[Callable[[Telemetry, "any"], None]] = None

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

            if self.stepper is not None and frame.fov_deg is not None:
                dt_ctrl = 1.0 / max(self.frame_source.get_fps(), 1.0)
                pan_rate, tilt_rate = self.stepper.step(telemetry, frame.image.shape[1],
                                                         frame.image.shape[0], dt_ctrl)
                self.actuator.command(pan_rate, tilt_rate, dt_ctrl)
                telemetry.pointing_command_deg = (pan_rate, tilt_rate)

            proc_ms = (time.perf_counter() - t0) * 1000.0

            tracking_error = self._tracking_error(telemetry)
            angular_error = link_loss = None
            handoff_ready = None
            if tracking_error is not None and frame.fov_deg is not None:
                angular_error = px_error_to_angular_error(tracking_error, frame.fov_deg[0], frame.image.shape[1])
                link_loss = pointing_loss_db(angular_error, self.link_cfg.beam_divergence_urad)
                handoff_ready = is_handoff_ready(angular_error, self.link_cfg.fine_stage_capture_range_urad)
            self.metrics.record_frame(telemetry.timestamp, telemetry.lock_state, tracking_error, proc_ms,
                                       angular_error_urad=angular_error, link_loss_db=link_loss,
                                       handoff_ready=handoff_ready)
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
