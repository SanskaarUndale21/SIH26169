"""Public API for plugging your own algorithms into the tracker.

The coarse-alignment loop has three swappable stages. Subclass one of the
base classes below in a .py file inside `user_algorithms/`, and it shows
up in the web console (New run, Algorithms, Compare) and the desktop app:

    Detector    image -> list of candidate beacon positions
    Tracker     chosen measurement (or None) -> estimated beacon position
    Controller  pointing error in degrees -> pan/tilt rate command

Everything else (gating the detections against the estimate, the
searching/acquiring/locked state machine, the search pattern while
nothing is seen, the camera and gimbal simulation, and all metrics) is
shared, so two algorithms compared on the same scenario and seed differ
only in the stage you swapped.

Minimal example (user_algorithms/my_detector.py):

    import numpy as np
    from algorithms.api import Detector, Detection

    class BrightestPixel(Detector):
        name = "Brightest pixel"
        description = "Takes the single brightest pixel as the beacon."
        params = {"min_level": {"default": 200, "min": 0, "max": 255, "step": 1}}

        def detect(self, image):
            y, x = np.unravel_index(np.argmax(image), image.shape)
            if image[y, x] < self.p["min_level"]:
                return []
            return [Detection(float(x), float(y), score=float(image[y, x]))]

Coordinates are camera pixels, origin top-left, x right, y down.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Detection:
    """One candidate beacon position found in a frame."""
    x: float
    y: float
    score: float = 1.0      # higher = more beacon-like; used when there is no track yet
    area: int = 0           # optional blob area in pixels


@dataclass
class AlgoContext:
    """What an algorithm knows about the run it is part of. Read-only."""
    frame_width: int
    frame_height: int
    fov_deg: Optional[Tuple[float, float]] = None     # None for video input
    target_size_px: Tuple[int, int] = (10, 10)
    max_pan_deg_s: float = 5.0
    max_tilt_deg_s: float = 5.0
    frame_rate_hz: float = 30.0
    config: Dict[str, Any] = field(default_factory=dict)  # full run config
    # On-board computer pointing cue, or None: .at(t) -> (pan, tilt) degrees
    # from the boresight zero, and .sigma_deg. Filled in before the first frame.
    cue: Any = None

    @property
    def px_per_deg(self) -> Optional[Tuple[float, float]]:
        if not self.fov_deg:
            return None
        return self.frame_width / self.fov_deg[0], self.frame_height / self.fov_deg[1]


class AlgorithmError(RuntimeError):
    """Raised when a plugged-in algorithm crashes or returns something
    malformed. The message names the algorithm and stage."""


def normalize_params(spec: Dict[str, Any]) -> Dict[str, dict]:
    """params may be given as {"k": 5} or {"k": {"default": 5, "min": 0, ...}}."""
    out = {}
    for key, v in (spec or {}).items():
        d = dict(v) if isinstance(v, dict) else {"default": v}
        default = d.get("default")
        if isinstance(default, bool):
            kind = "bool"
        elif isinstance(default, int):
            kind = "int"
        elif isinstance(default, float):
            kind = "float"
        else:
            kind = "text"
        d.setdefault("kind", kind)
        d.setdefault("label", key.replace("_", " ").capitalize())
        out[key] = d
    return out


class Algorithm:
    slot: str = ""
    name: str = ""
    description: str = ""
    params: Dict[str, Any] = {}

    def __init__(self, ctx: AlgoContext, **params):
        self.ctx = ctx
        spec = normalize_params(self.params)
        self.p: Dict[str, Any] = {k: d["default"] for k, d in spec.items()}
        for k, v in params.items():
            if k not in spec:
                continue
            kind = spec[k]["kind"]
            try:
                if kind == "int":
                    v = int(round(float(v)))
                elif kind == "float":
                    v = float(v)
                elif kind == "bool":
                    v = bool(v)
                else:
                    v = str(v)
            except (TypeError, ValueError):
                raise AlgorithmError(f"{self.display_name()}: parameter '{k}' must be {kind}, got {v!r}")
            self.p[k] = v
        self.setup()

    @classmethod
    def display_name(cls) -> str:
        return cls.name or cls.__name__

    def setup(self):
        """Optional: build state once, after self.ctx and self.p are set."""

    def reset(self):
        """Optional: clear internal state (called when tracking is lost for controllers)."""


class Detector(Algorithm):
    slot = "detector"

    def detect(self, image) -> List[Detection]:
        """image: 2D uint8 numpy array (monochrome). Return every candidate;
        the loop picks the one closest to the tracker's estimate."""
        raise NotImplementedError


class Tracker(Algorithm):
    slot = "tracker"

    def update(self, dt: float, measurement: Optional[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
        """Called once per frame. measurement is the chosen detection (x, y),
        or None if the beacon was not seen this frame. Return your estimate
        of the beacon position (x, y), or None if you have no track yet."""
        raise NotImplementedError

    def confidence(self, detected: bool) -> float:
        """Optional: 0..1 confidence shown in the console and logs."""
        return 1.0 if detected else 0.0


class Controller(Algorithm):
    slot = "controller"

    def compute(self, err_x_deg: float, err_y_deg: float, dt: float) -> Tuple[float, float]:
        """Called every frame while the beacon is tracked. err_*_deg is how
        far the estimate is from the image centre (positive = right/down).
        Return (pan_rate, tilt_rate) in deg/s; the gimbal clamps them to its
        speed limits."""
        raise NotImplementedError


SLOTS = {"detector": Detector, "tracker": Tracker, "controller": Controller}


# ---- output checking used by the pipeline -------------------------------

def check_detections(out, name: str) -> List[Detection]:
    if out is None:
        return []
    if not isinstance(out, (list, tuple)):
        raise AlgorithmError(f"Detector '{name}' must return a list of Detection, got {type(out).__name__}")
    dets = []
    for d in out:
        if isinstance(d, Detection):
            det = d
        elif isinstance(d, (list, tuple)) and len(d) >= 2:
            det = Detection(float(d[0]), float(d[1]), float(d[2]) if len(d) > 2 else 1.0)
        else:
            raise AlgorithmError(f"Detector '{name}' returned {d!r}; use Detection(x, y) or (x, y)")
        if not (math.isfinite(det.x) and math.isfinite(det.y)):
            raise AlgorithmError(f"Detector '{name}' returned a non-finite position {det.x, det.y}")
        dets.append(det)
    return dets


def check_point(out, name: str, what: str) -> Optional[Tuple[float, float]]:
    if out is None:
        return None
    try:
        x, y = float(out[0]), float(out[1])
    except Exception:
        shape = "(pan_rate, tilt_rate)" if what == "Controller" else "(x, y) or None"
        raise AlgorithmError(f"{what} '{name}' must return {shape}, got {out!r}")
    if not (math.isfinite(x) and math.isfinite(y)):
        raise AlgorithmError(f"{what} '{name}' returned a non-finite value {out!r}")
    return x, y
