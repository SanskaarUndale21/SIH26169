import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.target_motion import (CircularMotion, Figure8Motion, RandomWalkMotion,
                                      StraightLineMotion, make_motion_model)


def test_straight_line_moves_linearly_before_bounds():
    m = StraightLineMotion(x0=100, y0=100, width=2000, height=2000, speed_px_s=10, angle_deg=0)
    x0, y0 = m.position(0)
    x1, y1 = m.position(1)
    assert abs((x1 - x0) - 10) < 1e-6
    assert abs(y1 - y0) < 1e-6


def test_straight_line_reflects_at_bounds():
    m = StraightLineMotion(x0=0, y0=0, width=100, height=100, speed_px_s=1000, angle_deg=0)
    x, y = m.position(1)
    assert 0 <= x <= 100


def test_circular_motion_traces_circle():
    m = CircularMotion(cx=1000, cy=1000, width=2000, height=2000, radius_px=200, period_s=10)
    x0, y0 = m.position(0)
    assert abs((x0 - 1000) ** 2 + (y0 - 1000) ** 2 - 200 ** 2) < 1
    x_q, y_q = m.position(2.5)  # quarter period
    assert abs(x_q - 1000) < 5  # near top/bottom of circle


def test_figure8_is_periodic():
    m = Figure8Motion(cx=1000, cy=1000, width=2000, height=2000, A_px=200, B_px=100, period_s=8)
    p0 = m.position(0)
    p1 = m.position(8)  # one full period
    assert abs(p0[0] - p1[0]) < 1e-6
    assert abs(p0[1] - p1[1]) < 1e-6


def test_random_walk_stays_in_bounds():
    m = RandomWalkMotion(x0=1000, y0=1000, width=2000, height=2000, speed_px_s=50)
    for t in [0.1 * i for i in range(1, 200)]:
        x, y = m.position(t)
        assert 0 <= x <= 2000
        assert 0 <= y <= 2000


def test_make_motion_model_factory():
    for kind in ("straight_line", "circular", "figure8", "random", "spiral"):
        model = make_motion_model(kind, 1000, 1000, 2000, 2000, {})
        pos = model.position(1.0)
        assert len(pos) == 2
