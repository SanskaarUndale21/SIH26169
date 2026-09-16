"""PID pointing controller (Section 8.1). Converts a pixel error into a
pan/tilt rate command, clamped to the actuator's max speed."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PIDAxis:
    kp: float
    ki: float
    kd: float
    max_speed: float
    _integral: float = 0.0
    _prev_error: float = 0.0
    _has_prev: bool = False

    def step(self, error_deg: float, dt: float) -> float:
        self._integral += error_deg * dt
        # anti-windup: clamp integral so it can't alone exceed the speed limit
        max_i = self.max_speed / max(self.ki, 1e-6)
        self._integral = max(-max_i, min(max_i, self._integral))
        derivative = (error_deg - self._prev_error) / dt if self._has_prev else 0.0
        self._prev_error = error_deg
        self._has_prev = True
        out = self.kp * error_deg + self.ki * self._integral + self.kd * derivative
        return max(-self.max_speed, min(self.max_speed, out))

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._has_prev = False


class PIDPointingController:
    def __init__(self, config: dict):
        pid_cfg = config.get("control", {}).get("pid", {})
        ptz_cfg = config.get("ptz", {})
        pan_cfg = pid_cfg.get("pan", {"kp": 2.5, "ki": 0.15, "kd": 0.35})
        tilt_cfg = pid_cfg.get("tilt", {"kp": 2.5, "ki": 0.15, "kd": 0.35})
        max_pan = ptz_cfg.get("max_pan_speed_deg_s", 5.0)
        max_tilt = ptz_cfg.get("max_tilt_speed_deg_s", 5.0)
        self.pan = PIDAxis(pan_cfg["kp"], pan_cfg["ki"], pan_cfg["kd"], max_pan)
        self.tilt = PIDAxis(tilt_cfg["kp"], tilt_cfg["ki"], tilt_cfg["kd"], max_tilt)

    def compute(self, error_x_deg: float, error_y_deg: float, dt: float) -> tuple[float, float]:
        pan_rate = self.pan.step(error_x_deg, dt)
        tilt_rate = self.tilt.step(error_y_deg, dt)
        return pan_rate, tilt_rate

    def reset(self):
        self.pan.reset()
        self.tilt.reset()
