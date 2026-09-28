"""Drives the PTZ during searching/reacquiring lock states, per Section 7.4.

While `locked`/`acquiring`, the PID controller (pid_controller.py) owns the
pointing command. While `searching` (no track ever established, or track
lost long enough to fall back from reacquiring), this module instead sweeps
the boresight in an outward raster pattern at max slew rate so the camera
physically searches the reachable area, rather than sitting idle waiting
for the target to wander into view. While `reacquiring`, it does the same
but centred on the IMM's last known position (velocity-informed), which is
what keeps re-acquisition fast (much smaller area than a full rescan).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass
class RasterSweepDriver:
    """Boustrophedon (back-and-forth) raster scan: sweeps pan at max speed
    across the accessible width, then makes a discrete tilt step of one
    row-height before reversing sweep direction, repeating until it covers
    the configured +/- range and wrapping back to start. Implemented as an
    explicit two-phase state machine (pan-sweep, then tilt-step) so the
    tilt axis actually advances by a full row each time instead of a single
    frame's worth of motion, which a naive per-frame direction flip would
    produce."""
    max_pan_speed: float
    max_tilt_speed: float
    half_width_deg: float = 20.0
    half_height_deg: float = 12.0
    row_step_deg: float = 3.0
    _pan_offset: float = 0.0
    _tilt_offset: float = 0.0
    _pan_direction: int = 1
    _tilt_direction: int = 1
    _phase: str = "pan"          # "pan" | "tilt_step"
    _tilt_step_remaining_deg: float = 0.0

    def next_rate(self, dt: float) -> Tuple[float, float]:
        if self._phase == "pan":
            self._pan_offset += self._pan_direction * self.max_pan_speed * dt
            if abs(self._pan_offset) >= self.half_width_deg:
                self._pan_offset = self.half_width_deg * (1 if self._pan_direction > 0 else -1)
                self._pan_direction *= -1
                self._phase = "tilt_step"
                self._tilt_step_remaining_deg = self.row_step_deg
                return 0.0, self._tilt_direction * self.max_tilt_speed
            return self._pan_direction * self.max_pan_speed, 0.0
        else:  # tilt_step
            step = min(self._tilt_step_remaining_deg, self.max_tilt_speed * dt)
            self._tilt_step_remaining_deg -= step
            self._tilt_offset += self._tilt_direction * step
            if self._tilt_step_remaining_deg <= 1e-6:
                if abs(self._tilt_offset) >= self.half_height_deg:
                    self._tilt_direction *= -1  # wrap back and keep sweeping
                self._phase = "pan"
            return 0.0, self._tilt_direction * self.max_tilt_speed if self._tilt_step_remaining_deg > 1e-6 else 0.0

    def reset(self):
        self._pan_offset = 0.0
        self._tilt_offset = 0.0
        self._pan_direction = 1
        self._tilt_direction = 1
        self._phase = "pan"
        self._tilt_step_remaining_deg = 0.0


@dataclass
class SpiralSweepDriver:
    """Velocity-informed spiral search: steers at max slew rate toward a
    sequence of waypoints laid out on an outward (Archimedean) spiral,
    expanding from wherever it's re-centred (the IMM's last predicted
    position for re-acquisition, or the initial boresight for first
    acquisition -- a bounded-radius default target spawn, see scene.py,
    means this reaches it far faster than a full raster scan).

    Waypoint-based (steer toward the next point, advance once close) rather
    than an analytic constant-angular-rate spiral: at bounded max slew
    speed, holding angular rate fixed makes the tangential velocity
    component (which scales with radius) blow past the speed budget almost
    immediately, capping the *achievable* radius far below the intended
    search extent -- an earlier version of this driver hit exactly that
    trap. Waypoint-steering instead always moves at the full max_speed
    toward wherever it's trying to go next, so radius genuinely grows.
    """
    max_speed: float
    radial_step_deg: float = 2.0     # spiral pitch: outward distance per revolution step
    angle_step_deg: float = 40.0     # angular spacing between successive waypoints
    max_radius_deg: float = 25.0
    arrive_tol_deg: float = 0.5
    _pos: Tuple[float, float] = (0.0, 0.0)   # tracked (pan, tilt) offset from centre
    _radius_deg: float = 0.0
    _angle_deg: float = 0.0

    def recenter(self):
        self._pos = (0.0, 0.0)
        self._radius_deg = 0.0
        self._angle_deg = 0.0

    def _waypoint(self) -> Tuple[float, float]:
        import math
        theta = math.radians(self._angle_deg)
        return self._radius_deg * math.cos(theta), self._radius_deg * math.sin(theta)

    def next_rate(self, dt: float) -> Tuple[float, float]:
        import math
        wx, wy = self._waypoint()
        dx, dy = wx - self._pos[0], wy - self._pos[1]
        dist = math.hypot(dx, dy)
        if dist < self.arrive_tol_deg:
            self._angle_deg += self.angle_step_deg
            self._radius_deg += self.radial_step_deg * (self.angle_step_deg / 360.0)
            if self._radius_deg > self.max_radius_deg:
                self._radius_deg = 0.0
                self._angle_deg = 0.0
            wx, wy = self._waypoint()
            dx, dy = wx - self._pos[0], wy - self._pos[1]
            dist = math.hypot(dx, dy)
        if dist > 1e-9:
            pan_rate = self.max_speed * dx / dist
            tilt_rate = self.max_speed * dy / dist
        else:
            pan_rate = tilt_rate = 0.0
        self._pos = (self._pos[0] + pan_rate * dt, self._pos[1] + tilt_rate * dt)
        return pan_rate, tilt_rate


@dataclass
class CuedSearchDriver:
    """Search around an on-board computer (OBC) pointing cue.

    Steers at full slew rate to the cued direction, then spirals outward
    around it with rings spaced at most `ring_step_deg` apart (under one
    field of view, so no gap is left), out to `extent_deg` (3 sigma of the
    cue uncertainty). The cue is re-read every step, so a moving predicted
    direction is followed. Works in absolute gimbal angles (the gimbal's own
    encoders), which a real pointing assembly always has. `exhausted` turns
    True once the whole 3 sigma area has been covered; the caller then falls
    back to a full-field raster."""
    max_speed: float
    ring_step_deg: float
    extent_deg: float
    angle_step_deg: float = 30.0
    arrive_tol_deg: float = 0.3
    _radius_deg: float = 0.0
    _angle_deg: float = 0.0
    exhausted: bool = False

    def reset(self):
        self._radius_deg = 0.0
        self._angle_deg = 0.0
        self.exhausted = False

    def next_rate(self, pos_deg: Tuple[float, float], cue_deg: Tuple[float, float], dt: float) -> Tuple[float, float]:
        import math
        def waypoint():
            th = math.radians(self._angle_deg)
            return cue_deg[0] + self._radius_deg * math.cos(th), cue_deg[1] + self._radius_deg * math.sin(th)
        wx, wy = waypoint()
        dx, dy = wx - pos_deg[0], wy - pos_deg[1]
        dist = math.hypot(dx, dy)
        if dist < self.arrive_tol_deg:
            # advance along the spiral; keep angular spacing roughly constant in arc length
            step = self.angle_step_deg if self._radius_deg < 1e-6 else min(
                self.angle_step_deg, math.degrees(self.ring_step_deg / max(self._radius_deg, 1e-6)))
            self._angle_deg += step
            self._radius_deg += self.ring_step_deg * step / 360.0
            if self._radius_deg > self.extent_deg:
                self.exhausted = True
            wx, wy = waypoint()
            dx, dy = wx - pos_deg[0], wy - pos_deg[1]
            dist = math.hypot(dx, dy)
        if dist <= 1e-9:
            return 0.0, 0.0
        # slow down on arrival so we don't overshoot the waypoint every frame
        speed = min(self.max_speed, dist / max(dt, 1e-6))
        return speed * dx / dist, speed * dy / dist
