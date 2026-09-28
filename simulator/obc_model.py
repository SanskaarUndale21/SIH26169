"""On-board computer (OBC) pointing cue.

On orbit the satellite's computer tells the coarse pointing assembly
roughly where the other terminal is, from orbit and attitude knowledge
(ISRO mentor guidance, PS 26169). The prediction is uncertain: small for a
satellite-to-ground link, larger for an inter-satellite link, where the
camera has to scan around the predicted direction.

This module simulates that prediction. It lives in the simulator because
it is derived from the true beacon motion; the pointing loop only ever
receives the noisy prediction, never the truth.

    predicted(t) = true_direction(t) + link_bias + pass_error

- link_bias:  systematic error of this link (ephemeris or mounting error),
              the same on every pass. This is what multi-pass learning can
              estimate and remove (algorithms/pass_learner.py).
- pass_error: fresh random error each pass, N(0, sigma) per axis.

Directions are gimbal pan/tilt in degrees relative to the boresight zero
(the screen centre, where the camera starts).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class OBCCue:
    target: object                      # simulator.scene.Target (truth; never passed to perception)
    ref_world_xy: Tuple[float, float]   # boresight zero in world px
    world_px_per_deg: float
    sigma_deg: float
    bias_deg: Tuple[float, float]
    pass_error_deg: Tuple[float, float]
    correction_deg: Tuple[float, float] = (0.0, 0.0)   # applied by a learner, subtracted from the raw cue
    sigma_eff_deg: Optional[float] = None               # uncertainty after learning (defaults to sigma_deg)

    def true_direction(self, t: float) -> Tuple[float, float]:
        x, y = self.target.position(t)
        return ((x - self.ref_world_xy[0]) / self.world_px_per_deg,
                (y - self.ref_world_xy[1]) / self.world_px_per_deg)

    def raw(self, t: float) -> Tuple[float, float]:
        """What the OBC reports, before any learned correction."""
        tx, ty = self.true_direction(t)
        return (tx + self.bias_deg[0] + self.pass_error_deg[0],
                ty + self.bias_deg[1] + self.pass_error_deg[1])

    def at(self, t: float) -> Tuple[float, float]:
        """The cue handed to the pointing loop (raw minus learned correction)."""
        rx, ry = self.raw(t)
        return rx - self.correction_deg[0], ry - self.correction_deg[1]

    @property
    def sigma(self) -> float:
        return self.sigma_eff_deg if self.sigma_eff_deg is not None else self.sigma_deg

    def error_deg(self, t: float = 0.0) -> float:
        """Angular distance between the handed-over cue and the truth."""
        cx, cy = self.at(t)
        tx, ty = self.true_direction(t)
        return math.hypot(cx - tx, cy - ty)


class CueView:
    """What an algorithm plugin may see of the cue: the predicted direction
    and its uncertainty, never the truth behind it."""

    def __init__(self, cue: OBCCue):
        self._cue = cue

    def at(self, t: float) -> Tuple[float, float]:
        """Predicted beacon direction (pan, tilt) in degrees from the boresight zero."""
        return self._cue.at(t)

    @property
    def sigma_deg(self) -> float:
        return self._cue.sigma


def link_bias(link_seed: int, bias_deg) -> Tuple[float, float]:
    """The link's systematic error. An explicit [x, y] in config wins;
    otherwise a magnitude is given a direction fixed by the link seed, so
    every pass of the same link has the same bias."""
    if isinstance(bias_deg, (list, tuple)):
        return float(bias_deg[0]), float(bias_deg[1])
    mag = float(bias_deg or 0.0)
    ang = random.Random(int(link_seed)).uniform(0, 2 * math.pi)
    return mag * math.cos(ang), mag * math.sin(ang)


def cue_from_config(config: dict, scene, world_px_per_deg: float,
                    rng: Optional[random.Random] = None) -> Optional[OBCCue]:
    c = config.get("cue") or {}
    if not c.get("enabled") or not scene.targets:
        return None
    rng = rng or random
    sigma = float(c.get("sigma_deg", 0.5))
    scr = config.get("screen", {})
    return OBCCue(
        target=scene.targets[0],
        ref_world_xy=(scr.get("width", 2000) / 2, scr.get("height", 2000) / 2),
        world_px_per_deg=world_px_per_deg,
        sigma_deg=sigma,
        bias_deg=link_bias(c.get("link_seed", 1), c.get("bias_deg", 0.0)),
        pass_error_deg=(rng.gauss(0, sigma), rng.gauss(0, sigma)),
    )
