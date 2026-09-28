"""Shared pieces of the learned (CNN) beacon detector, used identically by
the training script (tools/train_detector.py) and the runtime detector
(algorithms/builtin.py LearnedDetector). No torch here: inference runs
through OpenCV's DNN module on the exported ONNX model, so the desktop
exe and the Docker image do not need torch.

Pipeline per frame:
  1. propose()  cheap candidate points: local maxima of a 3x3 median +
                box-filtered image above a deliberately LOW threshold, so a
                faint beacon is almost never missed at this stage.
  2. patches()  a 24x24 crop around each proposal, normalised by its own
                median and spread, so the network sees shape, not absolute
                brightness (fog, low light and gain changes look alike).
  3. the CNN    scores each crop (is it the beacon?) and regresses the
                sub-pixel offset from the proposal to the beacon centre.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

PATCH = 24
HALF = PATCH // 2
MODEL_PATH = Path(__file__).resolve().parent / "models" / "beacon_cnn.onnx"


def noise_stats(img: np.ndarray):
    sample = img[::4, ::4].astype(np.float32)
    med = float(np.median(sample))
    sigma = max(1.4826 * float(np.median(np.abs(sample - med))), 1.0)
    return med, sigma


def propose(image: np.ndarray, max_n: int = 48, k: float = 2.5):
    """Up to max_n (x, y) integer candidate points, strongest first."""
    img = cv2.medianBlur(image, 3)
    resp = cv2.boxFilter(img.astype(np.float32), -1, (3, 3))
    med, sigma = noise_stats(img)
    peaks = (resp == cv2.dilate(resp, np.ones((7, 7), np.uint8))) & (resp > med + k * sigma)
    # A bright beacon has a flat top where many pixels tie for the maximum;
    # merge each connected group of peak pixels into one point at its centre.
    n, _, stats, cents = cv2.connectedComponentsWithStats(peaks.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros((0, 2), np.int32)
    pts = np.rint(cents[1:]).astype(np.int32)
    pts[:, 0] = np.clip(pts[:, 0], 0, image.shape[1] - 1)
    pts[:, 1] = np.clip(pts[:, 1], 0, image.shape[0] - 1)
    order = np.argsort(resp[pts[:, 1], pts[:, 0]])[::-1][:max_n]
    return pts[order]


def patches(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    """N x 1 x 24 x 24 float32 crops, each normalised on its own."""
    if len(points) == 0:
        return np.zeros((0, 1, PATCH, PATCH), np.float32)
    padded = cv2.copyMakeBorder(image, HALF, HALF, HALF, HALF, cv2.BORDER_REFLECT)
    out = np.empty((len(points), 1, PATCH, PATCH), np.float32)
    for i, (x, y) in enumerate(points):
        p = padded[y:y + PATCH, x:x + PATCH].astype(np.float32)
        med = np.median(p)
        spread = max(float(p.max() - med), 8.0)
        out[i, 0] = (p - med) / spread
    return out


class OnnxBeaconNet:
    """Thin wrapper over cv2.dnn for the exported model: in -> N x 1 x 24 x 24,
    out -> N x 3 (logit, dx, dy)."""

    def __init__(self, path: Path = MODEL_PATH):
        if not Path(path).exists():
            raise FileNotFoundError(f"learned detector model not found at {path}")
        self.net = cv2.dnn.readNetFromONNX(str(path))

    def __call__(self, batch: np.ndarray, pad_to: int = 48) -> np.ndarray:
        """OpenCV rebuilds the network whenever the input batch size changes
        (~0.5 s), so batches are always padded to a fixed size."""
        n = len(batch)
        if n == 0:
            return np.zeros((0, 3), np.float32)
        size = max(pad_to, n)
        if n < size:
            batch = np.concatenate([batch, np.zeros((size - n, 1, PATCH, PATCH), np.float32)])
        self.net.setInput(batch)
        return self.net.forward().reshape(size, 3)[:n]
