"""Virtual camera model: world<->camera-pixel mapping and PTZ kinematics.

Uses the small-angle linear model explicitly allowed by the spec: the
target's angular offset from the camera boresight is computed, then mapped
linearly across the configured FOV to pixel coordinates.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class CameraModel:
    width_px: int = 640
    height_px: int = 480
    fov_x_deg: float = 4.0
    fov_y_deg: float = 3.0
    # boresight world position (what the camera is centred on, world px)
    world_x: float = 1000.0
    world_y: float = 1000.0
    # degrees-per-world-pixel scale: how much the boresight moves in world
    # pixels for each degree of pan/tilt. Chosen so the full screen is
    # reachable by panning/tilting across a reasonable angular range.
    world_px_per_deg: float = 50.0

    @property
    def px_per_deg_x(self) -> float:
        return self.width_px / self.fov_x_deg

    @property
    def px_per_deg_y(self) -> float:
        return self.height_px / self.fov_y_deg

    def world_to_camera_px(self, x_t: float, y_t: float) -> Tuple[float, float]:
        """Map a world position to camera pixel coords using the linear
        small-angle FOV model. Returns coords that may lie outside the
        image bounds when the target is outside the FOV."""
        dx_world = x_t - self.world_x
        dy_world = y_t - self.world_y
        angle_offset_x_deg = dx_world / self.world_px_per_deg
        angle_offset_y_deg = dy_world / self.world_px_per_deg
        u = self.width_px / 2 + angle_offset_x_deg * self.px_per_deg_x
        v = self.height_px / 2 + angle_offset_y_deg * self.px_per_deg_y
        return u, v

    def is_in_fov(self, u: float, v: float) -> bool:
        return 0 <= u <= self.width_px and 0 <= v <= self.height_px

    def pan_tilt_to_world(self) -> Tuple[float, float]:
        return self.world_x, self.world_y


@dataclass
class PTZActuator:
    """Camera boresight actuator with clamped pan/tilt rate, matching
    Section 6.3. Operates directly in world pixels for the boresight
    (equivalent to pan/tilt degrees scaled by world_px_per_deg)."""
    camera: CameraModel
    max_pan_speed_deg_s: float = 5.0
    max_tilt_speed_deg_s: float = 5.0

    def step(self, pan_rate_cmd_deg_s: float, tilt_rate_cmd_deg_s: float, dt: float):
        pan_rate = _clamp(pan_rate_cmd_deg_s, self.max_pan_speed_deg_s)
        tilt_rate = _clamp(tilt_rate_cmd_deg_s, self.max_tilt_speed_deg_s)
        self.camera.world_x += pan_rate * dt * self.camera.world_px_per_deg
        self.camera.world_y += tilt_rate * dt * self.camera.world_px_per_deg


def _clamp(v: float, limit: float) -> float:
    return max(-limit, min(limit, v))
