"""Perception+Tracking module entry point (Section 5.2/5.3).

Consumes a Frame (from either FrameSource implementation) and produces a
Telemetry record. Stateless with respect to frame source: never imports
from simulator/, only from perception/frame_source.py's Frame dataclass.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from perception.detector import Candidate, DetectorConfig, detect, select_best_candidate
from perception.frame_source import Frame
from perception.imm_tracker import IMMConfig, IMMTracker
from perception.lock_state import LockStateMachine
from perception.search_patterns import SpiralSearchPattern


@dataclass
class Telemetry:
    frame_id: int
    timestamp: float
    detected: bool
    centroid_px: Optional[Tuple[float, float]]
    predicted_px: Tuple[float, float]
    confidence: float
    lock_state: Literal["searching", "acquiring", "locked", "reacquiring"]
    pointing_command_deg: Tuple[float, float] = (0.0, 0.0)


def _turn_rate(v1: Tuple[float, float], v2: Tuple[float, float], dt: float) -> float:
    """Signed angular rate (rad/s) between two consecutive velocity
    vectors, via atan2 of the cross/dot product -- robust to the vectors'
    magnitudes differing (unlike a naive angle subtraction)."""
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    dtheta = math.atan2(cross, dot)
    return dtheta / max(dt, 1e-6)


class PerceptionTrackingPipeline:
    def __init__(self, config: dict, frame_width: int, frame_height: int):
        self.detector_cfg = DetectorConfig.from_config(config)
        self.imm_cfg = IMMConfig.from_config(config)
        lock_cfg = config.get("tracker", {})
        self.lock_sm = LockStateMachine(
            confirm_frames=lock_cfg.get("acquiring_confirm_frames", 4),
            reacquire_timeout_frames=lock_cfg.get("reacquire_timeout_frames", 30),
        )
        self.tracker: Optional[IMMTracker] = None
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.search = SpiralSearchPattern(frame_width / 2, frame_height / 2,
                                           max_radius=max(frame_width, frame_height) / 2)
        self._last_t: Optional[float] = None
        self.gate_radius = 60.0
        self._pre_lock_history: deque = deque(maxlen=3)  # (t, x, y) of raw detections before a track exists

    def process(self, frame: Frame) -> Telemetry:
        dt = 1 / 30.0 if self._last_t is None else max(1e-3, frame.timestamp - self._last_t)
        self._last_t = frame.timestamp

        candidates = detect(frame.image, self.detector_cfg)

        predicted = self.tracker.position if self.tracker is not None else None
        gate = self.gate_radius if self.lock_sm.state == "locked" else max(self.frame_width, self.frame_height)
        best = select_best_candidate(candidates, predicted, gate_radius=gate)

        if best is None and self.lock_sm.state in ("searching", "reacquiring") and candidates:
            # during search, bias toward whichever candidate is nearest the
            # current spiral search probe point instead of the (absent) IMM prediction
            probe = self.search.next_point()
            best = select_best_candidate(candidates, probe, gate_radius=gate)

        detected = best is not None
        measurement = (best.x, best.y) if best else None

        if self.tracker is None and detected:
            hist = self._pre_lock_history
            # only use recent, contiguous history (stale gaps -> restart)
            if hist and (frame.timestamp - hist[-1][0]) > 1.0:
                hist.clear()
            hist.append((frame.timestamp, measurement[0], measurement[1]))

            if len(hist) >= 3:
                # Three consecutive raw detections: seed both velocity and
                # turn-rate (omega) directly from finite differences instead
                # of leaving the CT model's omega at 0 and waiting for it to
                # implicitly correlate with position residuals over ~1s of
                # measurement updates -- that implicit convergence was
                # previously producing a large (~35px), multi-frame
                # tracking-error spike right after lock on curving motion,
                # which would fail Section 10's <=10px-while-locked target.
                (t0, x0, y0), (t1, x1, y1), (t2, x2, y2) = hist
                dt1, dt2 = t1 - t0, t2 - t1
                v1 = ((x1 - x0) / dt1, (y1 - y0) / dt1)
                v2 = ((x2 - x1) / dt2, (y2 - y1) / dt2)
                omega = _turn_rate(v1, v2, dt2)
                self.tracker = IMMTracker(self.imm_cfg, measurement, v2)
                self.tracker.models[1].x[4] = omega  # index 1 = CT model
            elif len(hist) == 2:
                (t0, x0, y0), (t1, x1, y1) = hist
                dt_meas = t1 - t0
                init_vel = ((x1 - x0) / dt_meas, (y1 - y0) / dt_meas)
                self.tracker = IMMTracker(self.imm_cfg, measurement, init_vel)
            else:
                # first-ever raw detection: not enough history yet -- wait.
                detected = False
                measurement = None

        if self.tracker is not None:
            self.tracker.step(dt, measurement)
            predicted_px = self.tracker.position
        else:
            predicted_px = (self.frame_width / 2, self.frame_height / 2)

        state = self.lock_sm.update(detected)
        if state == "reacquiring":
            self.search.recenter(*predicted_px)
        elif state == "searching" and self.tracker is None:
            pass  # spiral search continues around frame centre until first detection

        n_models = len(self.tracker.models) if self.tracker else 1
        confidence = float(max(self.tracker.mode_probs)) if (self.tracker and detected) else (0.3 if detected else 0.0)

        return Telemetry(
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            detected=detected,
            centroid_px=measurement,
            predicted_px=predicted_px,
            confidence=confidence,
            lock_state=state,
        )
