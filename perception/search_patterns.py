"""Search / re-acquisition patterns (Section 7.4).

Both patterns return a suggested (x, y) camera-pixel point to bias
detection gating toward -- since this virtual camera renders the whole FOV
every frame (there's no physical narrower sub-window to slew independently
of the PTZ), "scanning" here means widening/biasing the detector's search
gate over a spiral/raster path while the PID controller (Section 8.1) does
the actual physical panning toward the best current guess.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class RasterSearchPattern:
    width: int
    height: int
    step_px: int = 40
    _i: int = 0

    def next_point(self) -> Tuple[float, float]:
        cols = max(1, self.width // self.step_px)
        row = self._i // cols
        col = self._i % cols
        rows = max(1, self.height // self.step_px)
        self._i = (self._i + 1) % (cols * rows)
        return col * self.step_px, row * self.step_px

    def reset(self):
        self._i = 0


@dataclass
class SpiralSearchPattern:
    """Velocity-informed spiral search: expands outward from a centre
    point (typically the IMM's last predicted position, optionally
    projected forward by its velocity) rather than blind full-frame
    scanning -- this is what keeps re-acquisition time down (Section 7.4)."""
    cx: float
    cy: float
    max_radius: float = 320.0
    growth_px_per_step: float = 6.0
    angle_step_deg: float = 35.0
    _radius: float = 0.0
    _angle_deg: float = 0.0

    def recenter(self, cx: float, cy: float):
        self.cx, self.cy = cx, cy
        self._radius = 0.0
        self._angle_deg = 0.0

    def next_point(self) -> Tuple[float, float]:
        x = self.cx + self._radius * math.cos(math.radians(self._angle_deg))
        y = self.cy + self._radius * math.sin(math.radians(self._angle_deg))
        self._angle_deg += self.angle_step_deg
        self._radius += self.growth_px_per_step / (360.0 / self.angle_step_deg)
        if self._radius > self.max_radius:
            self._radius = 0.0
        return x, y
