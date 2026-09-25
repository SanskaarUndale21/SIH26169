"""Example tracker plugin: alpha-beta filter.

The fixed-gain ancestor of the Kalman filter: predict with constant
velocity, then correct position by alpha and velocity by beta times the
residual. Cheap and easy to reason about.
"""
from algorithms.api import Tracker


class AlphaBetaTracker(Tracker):
    name = "Alpha-beta filter (example)"
    description = "Constant-velocity prediction with fixed position and velocity gains."
    params = {
        "alpha": {"default": 0.85, "min": 0.05, "max": 1.0, "step": 0.05, "help": "Position correction gain"},
        "beta": {"default": 0.3, "min": 0.0, "max": 2.0, "step": 0.05, "help": "Velocity correction gain"},
    }

    def setup(self):
        self.pos = None
        self.vel = (0.0, 0.0)

    def update(self, dt, measurement):
        if self.pos is None:
            if measurement is None:
                return None
            self.pos = measurement
            return self.pos
        px = self.pos[0] + self.vel[0] * dt
        py = self.pos[1] + self.vel[1] * dt
        if measurement is not None:
            rx, ry = measurement[0] - px, measurement[1] - py
            a, b = self.p["alpha"], self.p["beta"]
            px, py = px + a * rx, py + a * ry
            self.vel = (self.vel[0] + b * rx / dt, self.vel[1] + b * ry / dt)
        self.pos = (px, py)
        return self.pos

    def confidence(self, detected):
        return 0.9 if detected else 0.2
