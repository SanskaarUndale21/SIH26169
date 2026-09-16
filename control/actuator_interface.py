"""Actuator interface: adapts a pan/tilt rate command onto whatever PTZ
implementation is behind it (the simulator's PTZActuator in-process, or in
principle a real gimbal driver). Kept separate from pid_controller.py so
the controller has zero dependency on the simulator module."""
from __future__ import annotations

from typing import Protocol


class Actuator(Protocol):
    def command(self, pan_rate_deg_s: float, tilt_rate_deg_s: float, dt: float) -> None: ...


class SimulatorActuator:
    """Drives a simulator.camera_model.PTZActuator."""

    def __init__(self, ptz):
        self.ptz = ptz

    def command(self, pan_rate_deg_s: float, tilt_rate_deg_s: float, dt: float) -> None:
        self.ptz.step(pan_rate_deg_s, tilt_rate_deg_s, dt)


class NullActuator:
    """No-op actuator for video-file mode, where there is no PTZ to drive
    (Benchmark-2 bypasses the camera/PTZ entirely) -- the pointing command
    is still computed and logged, just never applied."""

    def command(self, pan_rate_deg_s: float, tilt_rate_deg_s: float, dt: float) -> None:
        pass
