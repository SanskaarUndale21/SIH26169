"""Perception+Tracking module entry point (Section 5.2/5.3).

Consumes a Frame (from either FrameSource implementation) and produces a
Telemetry record. Stateless with respect to frame source: never imports
from simulator/, only from perception/frame_source.py's Frame dataclass.
"""
from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

from algorithms import registry
from algorithms.api import AlgorithmError, check_detections, check_point
from perception.detector import Candidate, select_best_candidate
from perception.frame_source import Frame
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


class PerceptionTrackingPipeline:
    """Detection -> gating -> tracking -> lock state, with the detector and
    tracker stages supplied by the algorithm registry (algorithms/), so a
    user plugin swaps in without touching this loop. The defaults ("dog"
    detector, "imm" tracker) reproduce the original hard-wired pipeline."""

    def __init__(self, config: dict, frame_width: int, frame_height: int):
        lock_cfg = config.get("tracker", {})
        self.lock_sm = LockStateMachine(
            confirm_frames=lock_cfg.get("acquiring_confirm_frames", 4),
            reacquire_timeout_frames=lock_cfg.get("reacquire_timeout_frames", 30),
        )
        self.ctx = registry.context_from_config(config, frame_width, frame_height)
        self.detector = registry.create("detector", config, self.ctx)
        self.tracker = registry.create("tracker", config, self.ctx)
        self._det_name = self.detector.display_name()
        self._trk_name = self.tracker.display_name()
        self._estimate: Optional[Tuple[float, float]] = None
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.search = SpiralSearchPattern(frame_width / 2, frame_height / 2,
                                           max_radius=max(frame_width, frame_height) / 2)
        self._last_t: Optional[float] = None
        self.gate_radius = 60.0

    def process(self, frame: Frame) -> Telemetry:
        dt = 1 / 30.0 if self._last_t is None else max(1e-3, frame.timestamp - self._last_t)
        self._last_t = frame.timestamp
        if self.ctx.fov_deg is None and frame.fov_deg is not None:
            self.ctx.fov_deg = tuple(frame.fov_deg)

        try:
            raw = self.detector.detect(frame.image)
        except AlgorithmError:
            raise
        except Exception as exc:
            raise AlgorithmError(f"Detector '{self._det_name}' crashed on frame {frame.frame_id}: "
                                 f"{exc}\n{traceback.format_exc(limit=4)}")
        candidates = [Candidate(d.x, d.y, d.area, d.score) for d in check_detections(raw, self._det_name)]

        predicted = self._estimate
        # Gate tightly around the current estimate whenever a track exists;
        # only a pure "never seen it yet" search uses the whole-frame gate,
        # so the confirm-frames counter can't advance on a different noise
        # blob each frame.
        gate = self.gate_radius if predicted is not None else max(self.frame_width, self.frame_height)
        best = select_best_candidate(candidates, predicted, gate_radius=gate)

        if best is None and self.lock_sm.state in ("searching", "reacquiring") and candidates:
            # during search, bias toward the candidate nearest the spiral probe point
            probe = self.search.next_point()
            best = select_best_candidate(candidates, probe, gate_radius=gate)

        detected = best is not None
        measurement = (best.x, best.y) if best else None

        try:
            est = self.tracker.update(dt, measurement)
        except AlgorithmError:
            raise
        except Exception as exc:
            raise AlgorithmError(f"Tracker '{self._trk_name}' crashed on frame {frame.frame_id}: "
                                 f"{exc}\n{traceback.format_exc(limit=4)}")
        self._estimate = check_point(est, self._trk_name, "Tracker")
        predicted_px = self._estimate if self._estimate is not None else (self.frame_width / 2, self.frame_height / 2)

        state = self.lock_sm.update(detected)
        if state == "reacquiring":
            self.search.recenter(*predicted_px)

        try:
            confidence = float(self.tracker.confidence(detected))
        except Exception:
            confidence = 1.0 if detected else 0.0

        return Telemetry(
            frame_id=frame.frame_id,
            timestamp=frame.timestamp,
            detected=detected,
            centroid_px=measurement,
            predicted_px=predicted_px,
            confidence=confidence,
            lock_state=state,
        )