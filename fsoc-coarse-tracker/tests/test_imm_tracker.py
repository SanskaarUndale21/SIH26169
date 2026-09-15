import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math

from perception.imm_tracker import IMMConfig, IMMTracker


def test_tracker_converges_on_straight_line():
    cfg = IMMConfig()
    tracker = IMMTracker(cfg, (0, 0))
    x, y = 0.0, 0.0
    for i in range(60):
        x += 2.0
        tracker.step(1 / 30.0, (x, y))
    px, py = tracker.position
    assert abs(px - x) < 5
    assert abs(py - y) < 5


def test_tracker_predicts_through_missed_detections():
    cfg = IMMConfig()
    tracker = IMMTracker(cfg, (0, 0))
    x = 0.0
    for i in range(30):
        x += 2.0
        tracker.step(1 / 30.0, (x, 0))
    # simulate 5 missed frames
    for i in range(5):
        tracker.step(1 / 30.0, None)
    px, py = tracker.position
    # prediction should have kept advancing roughly along the established velocity
    assert px > x - 1  # not stuck at last measurement


def test_mode_probabilities_sum_to_one():
    cfg = IMMConfig()
    tracker = IMMTracker(cfg, (0, 0))
    for i in range(20):
        tracker.step(1 / 30.0, (i, i))
    assert abs(sum(tracker.mode_probs) - 1.0) < 1e-6


def test_tracker_handles_circular_motion_reasonably():
    cfg = IMMConfig()
    r, omega = 100.0, 0.5
    tracker = IMMTracker(cfg, (r, 0))
    dt = 1 / 30.0
    t = 0.0
    for i in range(200):
        t += dt
        x = r * math.cos(omega * t)
        y = r * math.sin(omega * t)
        tracker.step(dt, (x, y))
    px, py = tracker.position
    assert math.hypot(px - x, py - y) < 15
