"""Optional learned false-positive filter (Section 8.4).

Additive, isolated, and toggleable on top of the classical detector
(detector.py) -- it is never a replacement for it, and detector.py works
identically whether or not this module or a trained model is present.
Import errors (torch missing) or a missing/failed-to-load model file are
caught and treated as "disabled", falling back to the classical-only path,
exactly as the spec requires (important for the unfamiliar Benchmark-2
videos, where a model trained only on simulator imagery may be out of its
depth and should not be trusted to gate real candidates).
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from perception.detector import Candidate

try:
    import torch
    import torch.nn as nn
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


if _TORCH_AVAILABLE:
    class BlobPatchCNN(nn.Module):
        """Tiny 3-conv-layer classifier over a fixed-size crop around a
        candidate blob -- deliberately small enough for real-time
        inference on many candidates per frame."""

        def __init__(self, patch_size: int = 24):
            super().__init__()
            self.patch_size = patch_size
            self.net = nn.Sequential(
                nn.Conv2d(1, 8, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(8, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 16, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
            )
            self.head = nn.Linear(16, 1)

        def forward(self, x):
            f = self.net(x).flatten(1)
            return torch.sigmoid(self.head(f))


class CNNFalsePositiveFilter:
    """Wraps an optional trained BlobPatchCNN. If unavailable, `enabled`
    stays False and `score()` is never called by the caller (see
    detector-gating usage in perception/pipeline.py's optional hook)."""

    def __init__(self, model_path: Optional[str] = None, patch_size: int = 24,
                 device: str = "cpu"):
        self.enabled = False
        self.patch_size = patch_size
        self.model = None
        if not _TORCH_AVAILABLE or not model_path:
            return
        try:
            self.model = BlobPatchCNN(patch_size)
            state = torch.load(model_path, map_location=device)
            self.model.load_state_dict(state)
            self.model.eval()
            self.enabled = True
        except Exception:
            # Missing file, corrupt checkpoint, architecture mismatch, etc:
            # fail safe to classical-only, never raise into the pipeline.
            self.model = None
            self.enabled = False

    def _extract_patch(self, image: np.ndarray, cx: float, cy: float) -> Optional[np.ndarray]:
        half = self.patch_size // 2
        h, w = image.shape[:2]
        x0, x1 = int(cx - half), int(cx + half)
        y0, y1 = int(cy - half), int(cy + half)
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
            return None
        patch = image[y0:y1, x0:x1]
        if patch.shape != (self.patch_size, self.patch_size):
            return None
        return patch.astype(np.float32) / 255.0

    def score(self, image: np.ndarray, candidate: Candidate) -> float:
        """Returns a confidence in [0, 1] that this candidate is the real
        target. Callers should treat a uniformly low score across all
        candidates in a frame as a possible domain-mismatch signal and fall
        back to the classical detector's own ranking rather than trusting
        the CNN gate (documented explicitly per Section 8.4)."""
        if not self.enabled or self.model is None:
            return 1.0  # neutral: don't gate anything out if disabled
        patch = self._extract_patch(image, candidate.x, candidate.y)
        if patch is None:
            return 1.0
        with torch.no_grad():
            t = torch.from_numpy(patch).unsqueeze(0).unsqueeze(0)
            return float(self.model(t).item())

    def filter_candidates(self, image: np.ndarray, candidates: List[Candidate],
                           min_score: float = 0.5) -> List[Candidate]:
        """Additional gate on top of detector.py's own candidates. Returns
        the input unmodified if this filter is disabled or every candidate
        scores near-uniformly low (domain mismatch fallback)."""
        if not self.enabled or not candidates:
            return candidates
        scores = [self.score(image, c) for c in candidates]
        if max(scores) < 0.05:
            return candidates  # likely domain mismatch: don't trust the gate
        return [c for c, s in zip(candidates, scores) if s >= min_score] or candidates


def generate_training_labels(candidates: List[Candidate], ground_truth_px, match_radius: float = 15.0):
    """Simulator-only helper (Section 8.4): labels each candidate blob as a
    true target (1) or false positive (0) by proximity to simulator ground
    truth. Never available at inference time on real/benchmark video."""
    labels = []
    for c in candidates:
        is_match = any(((c.x - gx) ** 2 + (c.y - gy) ** 2) ** 0.5 <= match_radius
                        for gx, gy in ground_truth_px)
        labels.append(1 if is_match else 0)
    return labels
