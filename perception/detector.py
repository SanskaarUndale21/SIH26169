"""Point-source detector: DoG / matched filter + adaptive threshold +
connected components + intensity-weighted centroiding (Section 7.1).

Deliberately a purpose-built small-blob detector, not a general object
detector -- the target is a 5-20 px bright point source, so a DoG matched
filter tuned to that scale beats a heavier general-purpose detector on both
speed and robustness to fog/haze illumination gradients.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Candidate:
    x: float
    y: float
    area: int
    peak_intensity: float


@dataclass
class DetectorConfig:
    dog_sigma1: float = 1.0
    dog_sigma2: float = 3.0
    threshold_k: float = 4.0
    min_blob_px: int = 4
    max_blob_px: int = 400

    @classmethod
    def from_config(cls, cfg: dict) -> "DetectorConfig":
        d = cfg.get("detector", {})
        # Default min/max blob area window is derived from the configured
        # target size (Section 3, param 10) rather than fixed generic
        # constants: the target's true pixel footprint is known ahead of
        # time (it's a config parameter, not something the detector has to
        # discover), so tying the size filter to it directly rejects noise
        # blobs of the wrong scale instead of accepting anything from 4 to
        # 400px. This matters most under salt & pepper / Gaussian noise,
        # where a loose generic window otherwise lets through enough
        # noise-sized candidates to occasionally satisfy the lock-state
        # machine's confirm-frames requirement on pure noise.
        target_size = cfg.get("target", {}).get("size_px", [10, 10])
        nominal_area = target_size[0] * target_size[1]
        default_min = max(4, int(nominal_area * 0.35))
        default_max = int(nominal_area * 3.0)
        return cls(
            dog_sigma1=d.get("dog_sigma1", 1.0),
            dog_sigma2=d.get("dog_sigma2", 3.0),
            threshold_k=d.get("threshold_k", 4.0),
            min_blob_px=d.get("min_blob_px", default_min),
            max_blob_px=d.get("max_blob_px", default_max),
        )


def robust_background_stats(img: np.ndarray) -> Tuple[float, float]:
    """Median + MAD-based robust estimate of background mean/std, so
    thresholding adapts to current noise/atmospheric conditions instead of
    assuming a fixed background level. Computed on a strided subsample
    (every 4th pixel in each axis) rather than the full frame -- background
    statistics don't need every pixel to be stable, and this cuts the
    dominant cost in the detector (two full-frame np.median calls) by ~16x,
    which is what keeps the pipeline above the 20 FPS processing-speed
    target (Section 10) at 640x480."""
    sample = img[::4, ::4]
    med = float(np.median(sample))
    mad = float(np.median(np.abs(sample.astype(np.float32) - med)))
    # MAD->std conversion for a Gaussian-like background, floored at 1 grey
    # level: when the background clips to 0 (low light), the MAD collapses
    # and a near-zero sigma would make every noise speck a detection.
    sigma = max(1.4826 * mad, 1.0)
    return med, sigma


def dog_response(img: np.ndarray, sigma1: float, sigma2: float) -> np.ndarray:
    img_f = img.astype(np.float32)
    g1 = cv2.GaussianBlur(img_f, (0, 0), sigma1)
    g2 = cv2.GaussianBlur(img_f, (0, 0), sigma2)
    return g1 - g2


def detect(img: np.ndarray, cfg: DetectorConfig) -> List[Candidate]:
    """Run the full detection pipeline and return all surviving candidate
    blobs (not yet gated against the tracker prediction -- that happens in
    select_best_candidate)."""
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # A light 3x3 median pre-filter is the standard defense against
    # impulsive salt & pepper noise: it kills isolated single/few-pixel
    # outliers while barely touching a real 5-20px target blob. Without
    # it, at the spec's ~10% salt & pepper density, thousands of isolated
    # bright noise pixels each produce a DoG response comparable to a real
    # point source (DoG's sigma1=1px is the same scale as a single noise
    # pixel), which both tanks accuracy and -- with thousands of surviving
    # candidates per frame -- tanks throughput well below the 20 FPS
    # target (Section 10). Cheap (~1-2ms at 640x480) and always applied
    # since it doesn't hurt the clean-image case.
    img = cv2.medianBlur(img, 3)
    _, sigma_local = robust_background_stats(img)
    dog = dog_response(img, cfg.dog_sigma1, cfg.dog_sigma2)
    thresh = cfg.threshold_k * sigma_local
    mask = (dog > thresh).astype(np.uint8)

    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n_labels <= 1:
        return []
    # Filter by blob area and bounding-box aspect ratio first (cheap, on the
    # stats table), then compute intensity-weighted centroids and peaks for
    # the survivors in one vectorised pass. The earlier per-blob Python loop
    # (mgrid + masked sums per blob) cost O(blobs) interpreter work, which
    # dropped processing below 20 FPS when noise produced ~1000 blobs/frame
    # (low light + Gaussian noise, where the clipped background shrinks the
    # noise estimate).
    area = stats[1:, cv2.CC_STAT_AREA]
    bw = stats[1:, cv2.CC_STAT_WIDTH]
    bh = stats[1:, cv2.CC_STAT_HEIGHT]
    aspect = np.maximum(bw, bh) / np.maximum(1, np.minimum(bw, bh))
    keep = (area >= cfg.min_blob_px) & (area <= cfg.max_blob_px) & (aspect <= 3.0)
    if not keep.any():
        return []
    # Work only on the thresholded pixels (a small fraction of the frame).
    lab_full = labels.ravel()
    idx = np.flatnonzero(lab_full)
    lab = lab_full[idx]
    w = img.ravel()[idx].astype(np.float64)
    ys, xs = np.divmod(idx, img.shape[1])
    sum_w = np.bincount(lab, weights=w, minlength=n_labels)
    sum_wx = np.bincount(lab, weights=w * xs, minlength=n_labels)
    sum_wy = np.bincount(lab, weights=w * ys, minlength=n_labels)
    peak_all = np.zeros(n_labels)
    np.maximum.at(peak_all, lab, w)
    ids = np.nonzero(keep)[0] + 1
    peaks = peak_all[ids]
    candidates: List[Candidate] = []
    for i, pk in zip(ids, np.atleast_1d(peaks)):
        if sum_w[i] <= 0:
            continue
        candidates.append(Candidate(x=float(sum_wx[i] / sum_w[i]), y=float(sum_wy[i] / sum_w[i]),
                                    area=int(stats[i, cv2.CC_STAT_AREA]), peak_intensity=float(pk)))
    return candidates


def select_best_candidate(candidates: List[Candidate],
                           predicted: Optional[Tuple[float, float]],
                           gate_radius: float = 60.0) -> Optional[Candidate]:
    """Prefer the candidate closest to the tracker's predicted position
    (gating), to avoid switching to noise or the wrong target in multi-
    target mode. Falls back to the brightest candidate if there is no
    prediction yet (e.g. first-ever detection during searching)."""
    if not candidates:
        return None
    if predicted is None:
        return max(candidates, key=lambda c: c.peak_intensity)
    px, py = predicted
    in_gate = [c for c in candidates if (c.x - px) ** 2 + (c.y - py) ** 2 <= gate_radius ** 2]
    pool = in_gate if in_gate else candidates
    return min(pool, key=lambda c: (c.x - px) ** 2 + (c.y - py) ** 2)
