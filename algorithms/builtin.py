"""Built-in algorithms: the tuned defaults plus simple baselines, all
written against the same public API (algorithms/api.py) a user plugin
uses, so a comparison against them is a fair one."""
from __future__ import annotations

import math
from collections import deque

import cv2
import numpy as np

from algorithms.api import Controller, Detection, Detector, Tracker
from control.pid_controller import PIDPointingController
from perception.detector import DetectorConfig, detect as dog_detect
from perception.imm_tracker import IMMConfig, IMMTracker


# ---------------------------------------------------------------- detectors

class DoGDetector(Detector):
    name = "Difference of Gaussians (default)"
    description = ("Median pre-filter, difference-of-Gaussians band-pass, threshold at k times "
                   "the robust noise level, blob size filter from the target size, intensity-weighted "
                   "centroid. Tuned in the Beacon detector settings.")

    def setup(self):
        self.cfg = DetectorConfig.from_config(self.ctx.config)

    def detect(self, image):
        return [Detection(c.x, c.y, score=c.peak_intensity, area=c.area) for c in dog_detect(image, self.cfg)]


class ThresholdCentroidDetector(Detector):
    name = "Global threshold + centroid"
    description = "Baseline: threshold at mean + k sigma of the whole frame, then centroid of each blob."
    params = {
        "k": {"default": 5.0, "min": 1.0, "max": 15.0, "step": 0.5, "help": "Threshold in noise sigmas above the mean"},
        "min_area": {"default": 4, "min": 1, "max": 200, "step": 1, "help": "Smallest blob kept, px"},
    }

    def detect(self, image):
        img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean, std = float(img.mean()), float(img.std()) + 1e-6
        mask = (img > mean + self.p["k"] * std).astype(np.uint8)
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out = []
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area >= self.p["min_area"]:
                out.append(Detection(float(cents[i][0]), float(cents[i][1]), score=float(area), area=area))
        return out


class LearnedDetector(Detector):
    name = "Learned CNN detector (experimental)"
    description = ("A small convolutional network, trained on simulator frames under every disturbance, scores "
                   "candidate spots and regresses the beacon centre. It is the only built-in detector that still "
                   "locks when every disturbance is at maximum, but it drops more frames than the classical detector "
                   "under ordinary heavy noise, so it is not the default. Runs through OpenCV, no torch needed. "
                   "Retrain with tools/train_detector.py.")
    params = {
        "min_score": {"default": 0.6, "min": 0.05, "max": 0.99, "step": 0.05,
                      "help": "Network confidence needed to accept a spot as the beacon"},
        "max_proposals": {"default": 48, "min": 4, "max": 200, "step": 4,
                          "help": "Candidate spots scored per frame (more = slower, fewer misses)"},
        "refine": {"default": True, "help": "Refine the network's position with a local intensity centroid"},
    }

    def setup(self):
        from algorithms.api import AlgorithmError
        from algorithms.learned import OnnxBeaconNet
        try:
            self.net = OnnxBeaconNet()
        except FileNotFoundError as exc:
            raise AlgorithmError(f"{exc}. Train it with: python tools/train_detector.py")

    def detect(self, image):
        from algorithms.learned import noise_stats, patches, propose
        img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        pts = propose(img, max_n=int(self.p["max_proposals"]))
        if len(pts) == 0:
            return []
        out = self.net(patches(img, pts), pad_to=int(self.p["max_proposals"]))
        score = 1.0 / (1.0 + np.exp(-out[:, 0]))
        keep = np.nonzero(score >= self.p["min_score"])[0]
        dets = []
        if len(keep) and self.p["refine"]:
            smooth = cv2.medianBlur(img, 3)
            med, sigma = noise_stats(smooth)
            floor = med + 2.0 * sigma
            r = max(self.ctx.target_size_px) // 2 + 3
        for i in keep[np.argsort(-score[keep])]:
            x = float(pts[i, 0] + np.clip(out[i, 1], -6, 6))
            y = float(pts[i, 1] + np.clip(out[i, 2], -6, 6))
            if self.p["refine"]:
                x, y = _local_centroid(smooth, x, y, floor, r)
            if all((x - d.x) ** 2 + (y - d.y) ** 2 > 16 for d in dets):  # merge duplicates within 4 px
                dets.append(Detection(x, y, score=float(score[i])))
        return dets


def _local_centroid(smooth, x, y, floor, r):
    """Intensity centroid of pixels above the frame's noise floor in a window
    sized to the beacon around (x, y); falls back to (x, y) with no signal."""
    h, w = smooth.shape
    x0, x1 = max(0, int(round(x)) - r), min(w, int(round(x)) + r + 1)
    y0, y1 = max(0, int(round(y)) - r), min(h, int(round(y)) + r + 1)
    win = np.clip(smooth[y0:y1, x0:x1].astype(np.float32) - floor, 0, None)
    tot = win.sum()
    if tot <= 0:
        return x, y
    ys, xs = np.mgrid[y0:y1, x0:x1]
    return float((xs * win).sum() / tot), float((ys * win).sum() / tot)


# ----------------------------------------------------------------- trackers

def _turn_rate(v1, v2, dt):
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    return math.atan2(cross, dot) / max(dt, 1e-6)


class IMMTrackerAlgo(Tracker):
    name = "Interacting multiple model (default)"
    description = ("Blends constant-velocity, coordinated-turn and random-walk Kalman filters. Seeds "
                   "velocity and turn rate from the first three detections. Tuned in the Motion filter settings.")

    def setup(self):
        self.cfg = IMMConfig.from_config(self.ctx.config)
        self.trk = None
        self.hist = deque(maxlen=3)
        self.seeded = False
        self.t = 0.0

    def update(self, dt, m):
        self.t += dt
        hist = self.hist
        if m is not None:
            if hist and (self.t - hist[-1][0]) > 1.0:
                hist.clear()
                self.seeded = False
            hist.append((self.t, m[0], m[1]))
        else:
            hist.clear()
            self.seeded = False

        if self.trk is None and m is not None:
            self.trk = IMMTracker(self.cfg, m)
        elif self.trk is not None and m is not None and not self.seeded and len(hist) >= 3:
            # one-time finite-difference velocity/turn-rate seed (see technical report Sec. 5)
            (t0, x0, y0), (t1, x1, y1), (t2, x2, y2) = hist
            dt1, dt2 = t1 - t0, t2 - t1
            v1 = ((x1 - x0) / dt1, (y1 - y0) / dt1)
            v2 = ((x2 - x1) / dt2, (y2 - y1) / dt2)
            omega = _turn_rate(v1, v2, dt2)
            for mdl in self.trk.models:
                mdl.x[2], mdl.x[3] = v2
                mdl.P[2, 2] = mdl.P[3, 3] = max(mdl.P[2, 2], 100.0)
                mdl.P[0, 2] = mdl.P[2, 0] = mdl.P[1, 3] = mdl.P[3, 1] = 0.0
            self.trk.models[1].x[4] = omega
            self.trk.models[1].P[4, 4] = max(self.trk.models[1].P[4, 4], 0.05)
            if abs(omega) > 0.15:
                self.trk.mode_probs = np.array([0.15, 0.70, 0.15])
            self.seeded = True

        if self.trk is None:
            return None
        self.trk.step(dt, m)
        return self.trk.position

    def confidence(self, detected):
        if self.trk is not None and detected:
            return float(max(self.trk.mode_probs))
        return 0.3 if detected else 0.0


class KalmanCVTracker(Tracker):
    name = "Constant-velocity Kalman"
    description = "Baseline: a single 4-state constant-velocity Kalman filter."
    params = {
        "process_noise": {"default": 30.0, "min": 0.1, "max": 500.0, "step": 0.5, "help": "Acceleration noise, px/s²"},
        "measurement_noise": {"default": 1.0, "min": 0.1, "max": 50.0, "step": 0.1, "help": "Centroid noise, px"},
    }

    def setup(self):
        self.x = None
        self.P = None

    def update(self, dt, m):
        if self.x is None:
            if m is None:
                return None
            self.x = np.array([m[0], m[1], 0.0, 0.0])
            self.P = np.diag([4.0, 4.0, 400.0, 400.0])
            return m
        F = np.array([[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        q = self.p["process_noise"] ** 2
        G = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + G @ (np.eye(2) * q) @ G.T
        if m is not None:
            H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
            R = np.eye(2) * self.p["measurement_noise"] ** 2
            S = H @ self.P @ H.T + R
            K = self.P @ H.T @ np.linalg.inv(S)
            self.x = self.x + K @ (np.asarray(m) - H @ self.x)
            self.P = (np.eye(4) - K @ H) @ self.P
        return float(self.x[0]), float(self.x[1])


class HoldLastTracker(Tracker):
    name = "No filter (hold last detection)"
    description = "Baseline: the estimate is the latest raw detection, held while the beacon is missed."

    def setup(self):
        self.last = None

    def update(self, dt, m):
        if m is not None:
            self.last = m
        return self.last


# -------------------------------------------------------------- controllers

class PIDController(Controller):
    name = "PID (default)"
    description = "Independent pan and tilt PID loops with anti-windup. Tuned in the Pointing loop settings."

    def setup(self):
        self.pid = PIDPointingController(self.ctx.config)

    def compute(self, ex, ey, dt):
        return self.pid.compute(ex, ey, dt)

    def reset(self):
        self.pid.reset()


class ProportionalController(Controller):
    name = "Proportional only"
    description = "Baseline: rate = gain x error on each axis. Lags moving targets by design."
    params = {"gain": {"default": 3.0, "min": 0.1, "max": 20.0, "step": 0.1, "help": "deg/s per degree of error"}}

    def compute(self, ex, ey, dt):
        return self.p["gain"] * ex, self.p["gain"] * ey


BUILTINS = {
    "detector": {"dog": DoGDetector, "cnn": LearnedDetector, "threshold": ThresholdCentroidDetector},
    "tracker": {"imm": IMMTrackerAlgo, "kalman_cv": KalmanCVTracker, "hold_last": HoldLastTracker},
    "controller": {"pid": PIDController, "p_only": ProportionalController},
}
DEFAULTS = {"detector": "dog", "tracker": "imm", "controller": "pid"}
