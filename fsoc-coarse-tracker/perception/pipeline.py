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

import numpy as np

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
        self._recent_history: deque = deque(maxlen=3)  # (t, x, y) of the last few raw detections
        self._velocity_seeded = False  # have we already done the one-time finite-diff velocity/omega seed?

    def process(self, frame: Frame) -> Telemetry:
        dt = 1 / 30.0 if self._last_t is None else max(1e-3, frame.timestamp - self._last_t)
        self._last_t = frame.timestamp

        candidates = detect(frame.image, self.detector_cfg)

        predicted = self.tracker.position if self.tracker is not None else None
        # Gate tightly around the IMM's prediction whenever a track exists
        # (acquiring, locked, or reacquiring-with-a-stale-track) -- only a
        # pure "never seen it yet" search has no prediction to trust and
        # needs the wide, whole-frame gate. Gating loosely throughout
        # "acquiring" (an earlier version of this pipeline did) let the
        # confirm-frames counter advance on a different noise blob each
        # frame instead of the same physical target.
        gate = self.gate_radius if predicted is not None else max(self.frame_width, self.frame_height)
        best = select_best_candidate(candidates, predicted, gate_radius=gate)

        if best is None and self.lock_sm.state in ("searching", "reacquiring") and candidates:
            # during search, bias toward whichever candidate is nearest the
            # current spiral search probe point instead of the (absent) IMM prediction
            probe = self.search.next_point()
            best = select_best_candidate(candidates, probe, gate_radius=gate)

        detected = best is not None
        measurement = (best.x, best.y) if best else None

        # Recent-detection history feeds a one-time finite-difference
        # velocity/turn-rate seed (below) -- it is NOT used to gate lock-
        # state confirmation on pixel-distance consistency between
        # consecutive points. An earlier version tried that (reject a
        # "too fast" jump between consecutive pre-lock detections), but
        # while the search is actively sweeping, the *camera itself* is
        # slewing at up to the PTZ speed limit -- which in camera-frame
        # pixels can dwarf any real target's own motion -- so a stationary
        # target looks like it's "jumping" just from the boresight moving
        # under it. Perception deliberately has no dependency on the
        # simulator/actuator to separate that out. Robustness against
        # locking onto noise instead comes from: the detector's target-
        # size-derived blob filter, the nonzero background level fixing
        # the noise-sigma estimate (see technical report Sec. 9.2), and
        # gating tightly around the IMM's own prediction from the very
        # first raw detection onward (the tracker is created immediately
        # below, not after a multi-frame wait).
        hist = self._recent_history
        if detected:
            if hist and (frame.timestamp - hist[-1][0]) > 1.0:
                hist.clear()
                self._velocity_seeded = False
            hist.append((frame.timestamp, measurement[0], measurement[1]))
        else:
            hist.clear()
            self._velocity_seeded = False

        if self.tracker is None and detected:
            # Create the tracker immediately on the very first raw
            # detection, zero-velocity, so a real target is picked up (and
            # the search stops chasing away from it, since select_best_
            # candidate above will gate tightly around this prediction
            # starting next frame) from frame one, rather than waiting
            # several frames to estimate velocity first.
            self.tracker = IMMTracker(self.imm_cfg, measurement)
        elif self.tracker is not None and detected and not self._velocity_seeded and len(hist) >= 3:
            # One-time correction, once 3 consistent (now IMM-gated, so
            # trustworthy) measurements have accumulated: overwrite the
            # velocity/turn-rate the filter would otherwise have to
            # converge onto implicitly over ~1s of updates. This is what
            # keeps the tracking-error transient right after lock small on
            # fast-curving motion (Section 10's <=10px-while-locked
            # target) without needing to delay track creation itself.
            (t0, x0, y0), (t1, x1, y1), (t2, x2, y2) = hist
            dt1, dt2 = t1 - t0, t2 - t1
            v1 = ((x1 - x0) / dt1, (y1 - y0) / dt1)
            v2 = ((x2 - x1) / dt2, (y2 - y1) / dt2)
            omega = _turn_rate(v1, v2, dt2)
            for m in self.tracker.models:
                m.x[2], m.x[3] = v2
                # Re-inflate the velocity covariance after directly
                # overwriting the state: leaving P as the (small, post-
                # several-Kalman-updates) value it had converged to would
                # make the filter overconfident about a state that just
                # jumped externally, which was observed to occasionally
                # produce an ill-conditioned innovation covariance a few
                # frames later (a NumPy OverflowError in the mode-
                # probability likelihood calculation).
                m.P[2, 2] = m.P[3, 3] = max(m.P[2, 2], 100.0)
                m.P[0, 2] = m.P[2, 0] = m.P[1, 3] = m.P[3, 1] = 0.0
            self.tracker.models[1].x[4] = omega  # index 1 = CT model
            self.tracker.models[1].P[4, 4] = max(self.tracker.models[1].P[4, 4], 0.05)
            if abs(omega) > 0.15:
                self.tracker.mode_probs = np.array([0.15, 0.70, 0.15])
            self._velocity_seeded = True

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
