"""Starter files offered by the web console's "New algorithm" button."""

DETECTOR = '''"""{title}

Describe your detector here.
"""
import numpy as np

from algorithms.api import Detection, Detector


class {cls}(Detector):
    name = "{title}"
    description = "One line shown in the algorithm pickers."
    # Parameters appear as sliders in the console. Plain values work too: {{"k": 5.0}}
    params = {{
        "threshold": {{"default": 200, "min": 0, "max": 255, "step": 1, "help": "Brightness cut-off"}},
    }}

    def setup(self):
        # Runs once. self.ctx has frame_width, frame_height, fov_deg,
        # target_size_px, max_pan_deg_s, frame_rate_hz and the full config.
        pass

    def detect(self, image):
        # image: 2D uint8 numpy array. Return every candidate you find;
        # the loop picks the one nearest the tracker's estimate.
        ys, xs = np.nonzero(image >= self.p["threshold"])
        if len(xs) == 0:
            return []
        return [Detection(float(xs.mean()), float(ys.mean()), score=float(len(xs)))]
'''

TRACKER = '''"""{title}

Describe your tracker here.
"""
from algorithms.api import Tracker


class {cls}(Tracker):
    name = "{title}"
    description = "One line shown in the algorithm pickers."
    params = {{
        "smoothing": {{"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "help": "0 = raw, 1 = frozen"}},
    }}

    def setup(self):
        self.estimate = None

    def update(self, dt, measurement):
        # measurement: (x, y) of the chosen detection, or None when missed.
        # Return your (x, y) estimate, or None while you have no track.
        if measurement is None:
            return self.estimate
        if self.estimate is None:
            self.estimate = measurement
        else:
            a = self.p["smoothing"]
            self.estimate = (a * self.estimate[0] + (1 - a) * measurement[0],
                             a * self.estimate[1] + (1 - a) * measurement[1])
        return self.estimate
'''

CONTROLLER = '''"""{title}

Describe your pointing controller here.
"""
from algorithms.api import Controller


class {cls}(Controller):
    name = "{title}"
    description = "One line shown in the algorithm pickers."
    params = {{
        "gain": {{"default": 2.5, "min": 0.0, "max": 20.0, "step": 0.1, "help": "deg/s per degree of error"}},
    }}

    def setup(self):
        pass

    def reset(self):
        # Called when the beacon is lost and the search takes over.
        pass

    def compute(self, err_x_deg, err_y_deg, dt):
        # Error of the estimate from the image centre, in degrees
        # (positive = right / down). Return (pan_rate, tilt_rate) in deg/s;
        # the gimbal clamps them to its speed limits.
        return self.p["gain"] * err_x_deg, self.p["gain"] * err_y_deg
'''

TEMPLATES = {"detector": DETECTOR, "tracker": TRACKER, "controller": CONTROLLER}


def render(slot: str, title: str, cls: str) -> str:
    return TEMPLATES[slot].format(title=title, cls=cls)
