"""Multi-pass learning of the on-board computer's pointing-cue error.

A LEO link sees the same partner several times a day. The OBC's predicted
direction has a systematic error that repeats on every pass (ephemeris or
mounting error) plus fresh random error. After each acquisition the
terminal knows where the beacon really was (boresight angle plus the
beacon's position in the image), so it can measure

    z = raw_cue - measured_direction = systematic_bias + this pass's error

and estimate the systematic part with a Kalman filter across passes. The
next pass's cue is corrected by the estimate, and the search area shrinks
to the remaining uncertainty, which cuts acquisition time: the ISRO mentor
suggestion of using a model to anticipate the next pass.

    b_k = b_(k-1) + K (z - b_(k-1)),   K = P / (P + R),   P <- (1 - K) P
    R = sigma^2 (per-pass cue error), P0 = prior variance of the bias
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class PassLearner:
    link: str = "link-1"
    prior_sigma_deg: float = 2.0          # how large the systematic error might be before any pass
    bias: Tuple[float, float] = (0.0, 0.0)
    P: float = None                        # variance of the bias estimate (deg^2), per axis
    passes: int = 0
    history: List[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.P is None:
            self.P = self.prior_sigma_deg ** 2

    def apply(self, cue):
        """Correct the cue in place: subtract the learned bias and widen or
        narrow its uncertainty to what is actually still unknown."""
        cue.correction_deg = tuple(self.bias)
        # remaining error = this pass's random error + what we don't yet know of the bias
        cue.sigma_eff_deg = math.sqrt(cue.sigma_deg ** 2 + self.P)

    def observe(self, cue, measured_direction_deg, t: float):
        """Learn from one acquisition: measured beacon direction vs raw cue."""
        rx, ry = cue.raw(t)
        # the cue's error this pass (cue minus where the beacon really was);
        # the learned bias is subtracted from future cues in apply()
        z = (rx - measured_direction_deg[0], ry - measured_direction_deg[1])
        R = max(cue.sigma_deg, 0.02) ** 2
        K = self.P / (self.P + R)
        self.bias = (self.bias[0] + K * (z[0] - self.bias[0]), self.bias[1] + K * (z[1] - self.bias[1]))
        self.P = (1 - K) * self.P
        self.passes += 1
        self.history.append({"pass": self.passes, "measured_offset_deg": [round(z[0], 4), round(z[1], 4)],
                             "bias_estimate_deg": [round(self.bias[0], 4), round(self.bias[1], 4)],
                             "bias_sigma_deg": round(math.sqrt(self.P), 4)})

    # -- persistence (one file per link, so live runs can learn across sessions) --
    @classmethod
    def load(cls, directory: str, link: str, prior_sigma_deg: float = 2.0) -> "PassLearner":
        path = Path(directory) / f"{link}.json"
        if path.exists():
            try:
                d = json.loads(path.read_text())
                d["bias"] = tuple(d["bias"])
                return cls(**d)
            except (ValueError, KeyError, TypeError):
                pass
        return cls(link=link, prior_sigma_deg=prior_sigma_deg)

    def save(self, directory: str):
        os.makedirs(directory, exist_ok=True)
        (Path(directory) / f"{self.link}.json").write_text(json.dumps(asdict(self), indent=1))
