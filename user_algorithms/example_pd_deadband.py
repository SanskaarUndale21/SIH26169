"""Example controller plugin: PD with a deadband.

Proportional-derivative rate control that stops commanding motion once
the error is inside a small deadband, trading a little residual error for
a quieter gimbal.
"""
from algorithms.api import Controller


class PDDeadbandController(Controller):
    name = "PD with deadband (example)"
    description = "Proportional-derivative rate command, zero inside a small error deadband."
    params = {
        "kp": {"default": 3.0, "min": 0.0, "max": 20.0, "step": 0.1, "help": "deg/s per degree"},
        "kd": {"default": 0.25, "min": 0.0, "max": 5.0, "step": 0.05, "help": "deg/s per deg/s of error change"},
        "deadband_deg": {"default": 0.01, "min": 0.0, "max": 0.5, "step": 0.005, "help": "No motion below this error"},
    }

    def setup(self):
        self.prev = None

    def reset(self):
        self.prev = None

    def compute(self, err_x_deg, err_y_deg, dt):
        if self.prev is None:
            dx = dy = 0.0
        else:
            dx = (err_x_deg - self.prev[0]) / dt
            dy = (err_y_deg - self.prev[1]) / dt
        self.prev = (err_x_deg, err_y_deg)
        db = self.p["deadband_deg"]
        pan = 0.0 if abs(err_x_deg) < db else self.p["kp"] * err_x_deg + self.p["kd"] * dx
        tilt = 0.0 if abs(err_y_deg) < db else self.p["kp"] * err_y_deg + self.p["kd"] * dy
        return pan, tilt
