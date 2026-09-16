import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from perception.detector import DetectorConfig, detect, select_best_candidate, robust_background_stats


def make_blob_image(cx=320, cy=240, size=10, bg=0, fg=255, shape=(480, 640)):
    img = np.full(shape, bg, dtype=np.uint8)
    half = size // 2
    img[cy - half:cy + half, cx - half:cx + half] = fg
    return img


def test_detects_single_blob_at_correct_centroid():
    img = make_blob_image(cx=320, cy=240, size=10)
    cfg = DetectorConfig()
    candidates = detect(img, cfg)
    assert len(candidates) >= 1
    best = min(candidates, key=lambda c: (c.x - 320) ** 2 + (c.y - 240) ** 2)
    assert abs(best.x - 320) < 2
    assert abs(best.y - 240) < 2


def test_no_detection_on_blank_image():
    img = np.zeros((480, 640), dtype=np.uint8)
    cfg = DetectorConfig()
    candidates = detect(img, cfg)
    assert len(candidates) == 0


def test_rejects_oversized_blob_as_not_point_source():
    img = np.zeros((480, 640), dtype=np.uint8)
    img[100:300, 100:300] = 255  # 200x200 block, way bigger than max_blob_px
    cfg = DetectorConfig(max_blob_px=400)
    candidates = detect(img, cfg)
    assert len(candidates) == 0


def test_select_best_candidate_prefers_gated_prediction():
    from perception.detector import Candidate
    candidates = [Candidate(x=10, y=10, area=8, peak_intensity=200),
                  Candidate(x=300, y=300, area=8, peak_intensity=255)]
    best = select_best_candidate(candidates, predicted=(12, 12), gate_radius=30)
    assert best.x == 10


def test_robust_background_stats_on_uniform_image():
    img = np.full((480, 640), 50, dtype=np.uint8)
    med, sigma = robust_background_stats(img)
    assert med == 50
    assert sigma < 1.0
