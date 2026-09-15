"""Target motion models: straight line, circular, figure-of-8, random walk.

Each model is parametrized by time t (seconds since simulation start) and
returns a world-frame (x, y) pixel position. Straight-line motion reflects
off the screen bounds so the target stays in the world indefinitely.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Protocol, Tuple


class MotionModel(Protocol):
    def position(self, t: float) -> Tuple[float, float]: ...


@dataclass
class StraightLineMotion:
    x0: float
    y0: float
    width: int
    height: int
    speed_px_s: float = 60.0
    angle_deg: float = 30.0

    def position(self, t: float) -> Tuple[float, float]:
        vx = self.speed_px_s * math.cos(math.radians(self.angle_deg))
        vy = self.speed_px_s * math.sin(math.radians(self.angle_deg))
        x = self.x0 + vx * t
        y = self.y0 + vy * t
        # reflect off bounds (triangle-wave folding) so motion stays on screen
        x = _reflect(x, self.width)
        y = _reflect(y, self.height)
        return x, y


def _reflect(v: float, limit: float) -> float:
    period = 2 * limit
    v = v % period
    if v > limit:
        v = period - v
    return v


@dataclass
class CircularMotion:
    cx: float
    cy: float
    width: int
    height: int
    radius_px: float = 300.0
    period_s: float = 20.0

    def position(self, t: float) -> Tuple[float, float]:
        omega = 2 * math.pi / self.period_s
        x = self.cx + self.radius_px * math.cos(omega * t)
        y = self.cy + self.radius_px * math.sin(omega * t)
        return _clamp(x, self.width), _clamp(y, self.height)


@dataclass
class Figure8Motion:
    cx: float
    cy: float
    width: int
    height: int
    A_px: float = 300.0
    B_px: float = 200.0
    period_s: float = 24.0

    def position(self, t: float) -> Tuple[float, float]:
        # Lissajous a:b = 1:2 -> classic figure-8
        a, b = 1.0, 2.0
        w = 2 * math.pi / self.period_s
        x = self.cx + self.A_px * math.sin(a * w * t)
        y = self.cy + self.B_px * math.sin(b * w * t)
        return _clamp(x, self.width), _clamp(y, self.height)


@dataclass
class RandomWalkMotion:
    x0: float
    y0: float
    width: int
    height: int
    speed_px_s: float = 80.0
    theta_std_deg: float = 15.0
    _last_t: float = 0.0
    _x: float = None
    _y: float = None
    _heading_deg: float = None

    def __post_init__(self):
        self._x = self.x0
        self._y = self.y0
        self._heading_deg = random.uniform(0, 360)

    def position(self, t: float) -> Tuple[float, float]:
        # Ornstein-Uhlenbeck-smoothed heading random walk, integrated since last call.
        dt = max(0.0, t - self._last_t)
        self._last_t = t
        if dt > 0:
            self._heading_deg += random.gauss(0, self.theta_std_deg * math.sqrt(dt))
            vx = self.speed_px_s * math.cos(math.radians(self._heading_deg))
            vy = self.speed_px_s * math.sin(math.radians(self._heading_deg))
            nx = self._x + vx * dt
            ny = self._y + vy * dt
            if nx < 0 or nx > self.width:
                self._heading_deg = 180 - self._heading_deg
                nx = min(max(nx, 0), self.width)
            if ny < 0 or ny > self.height:
                self._heading_deg = -self._heading_deg
                ny = min(max(ny, 0), self.height)
            self._x, self._y = nx, ny
        return self._x, self._y


@dataclass
class SpiralMotion:
    cx: float
    cy: float
    width: int
    height: int
    r0_px: float = 20.0
    k_px_s: float = 15.0
    period_s: float = 6.0

    def position(self, t: float) -> Tuple[float, float]:
        omega = 2 * math.pi / self.period_s
        r = self.r0_px + self.k_px_s * t
        r = r % (min(self.width, self.height) / 2.0)
        x = self.cx + r * math.cos(omega * t)
        y = self.cy + r * math.sin(omega * t)
        return _clamp(x, self.width), _clamp(y, self.height)


def _clamp(v: float, limit: float) -> float:
    return min(max(v, 0), limit)


def make_motion_model(kind: str, x0: float, y0: float, width: int, height: int,
                       params: dict) -> MotionModel:
    p = params.get(kind, {}) if params else {}
    if kind == "straight_line":
        return StraightLineMotion(x0, y0, width, height, **p)
    if kind == "circular":
        return CircularMotion(x0, y0, width, height, **p)
    if kind == "figure8":
        return Figure8Motion(x0, y0, width, height, **p)
    if kind == "random":
        return RandomWalkMotion(x0, y0, width, height, **p)
    if kind == "spiral":
        return SpiralMotion(x0, y0, width, height, **p)
    raise ValueError(f"unknown motion model: {kind}")
