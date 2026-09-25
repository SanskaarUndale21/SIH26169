"""Example detector plugin: matched filter.

Correlates the frame with a box the size of the configured beacon, then
keeps local maxima that stand well above the background. A textbook
point-target detector, included to show the plugin API and to give the
built-in difference-of-Gaussians detector something real to compete with.
"""
import cv2
import numpy as np

from algorithms.api import Detection, Detector


class MatchedFilterDetector(Detector):
    name = "Matched filter (example)"
    description = "Box matched filter at the beacon size, local maxima above k sigma."
    params = {
        "k": {"default": 6.0, "min": 1.0, "max": 20.0, "step": 0.5,
              "help": "Detection threshold in background sigmas"},
        "max_candidates": {"default": 10, "min": 1, "max": 100, "step": 1,
                           "help": "Keep at most this many strongest peaks"},
    }

    def setup(self):
        w, h = self.ctx.target_size_px
        self.kernel = (max(3, w | 1), max(3, h | 1))  # odd sizes

    def detect(self, image):
        img = cv2.medianBlur(image, 3).astype(np.float32)
        resp = cv2.boxFilter(img, -1, self.kernel)
        sample = resp[::4, ::4]
        med = float(np.median(sample))
        sigma = 1.4826 * float(np.median(np.abs(sample - med))) + 1e-6
        peaks = (resp == cv2.dilate(resp, np.ones((9, 9), np.uint8))) & (resp > med + self.p["k"] * sigma)
        ys, xs = np.nonzero(peaks)
        if len(xs) == 0:
            return []
        scores = resp[ys, xs]
        order = np.argsort(scores)[::-1][: self.p["max_candidates"]]
        return [Detection(float(xs[i]), float(ys[i]), score=float(scores[i])) for i in order]
