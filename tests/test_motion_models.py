import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.target_motion import (CircularMotion, Figure8Motion, RandomWalkMotion,
                                      SinusoidalMotion, StraightLineMotion, UserDefinedMotion,
                                      make_motion_model, parse_waypoints)


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
    # Starts exactly at the given (cx, cy) -- matching every other motion
    # model's convention that the constructor's cx/cy is the actual t=0
    # position, not an orbit centre offset by a full radius_px from it.
    assert abs(x0 - 1000) < 1e-6
    assert abs(y0 - 1000) < 1e-6
    # Still traces a real circle of the configured radius around whatever
    # centre was back-solved from the random phase.
    cx, cy = m.cx, m.cy
    assert abs(math.hypot(x0 - cx, y0 - cy) - 200) < 1e-6
    x1, y1 = m.position(2.5)
    assert abs(math.hypot(x1 - cx, y1 - cy) - 200) < 1e-6
    # A full period returns to the exact start position.
    x_full, y_full = m.position(10)
    assert abs(x_full - x0) < 1e-6
    assert abs(y_full - y0) < 1e-6


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


def test_make_motion_model_factory_optional_types():
    for kind in ("sinusoidal", "user_defined"):
        model = make_motion_model(kind, 1000, 1000, 2000, 2000, {})
        x, y = model.position(1.0)
        assert 0 <= x <= 2000 and 0 <= y <= 2000


def test_sinusoidal_weaves_around_heading():
    m = SinusoidalMotion(x0=500, y0=1000, width=2000, height=2000,
                         speed_px_s=10, angle_deg=0, amplitude_px=100, period_s=4)
    x, y = m.position(1.0)  # quarter period -> full sideways amplitude
    assert abs(x - 510) < 1e-6
    assert abs(y - 1100) < 1e-6


def test_user_defined_path_visits_waypoints_and_loops():
    m = UserDefinedMotion(x0=1000, y0=1000, width=2000, height=2000,
                          waypoints="100,0; 100,100", speed_px_s=100)
    assert m.position(0) == (1000, 1000)
    x, y = m.position(1.0)  # 100px along first leg
    assert abs(x - 1100) < 1e-6 and abs(y - 1000) < 1e-6
    loop = m._cum[-1] / 100
    x, y = m.position(loop)
    assert abs(x - 1000) < 1e-6 and abs(y - 1000) < 1e-6


def test_parse_waypoints_rejects_garbage():
    import pytest
    assert parse_waypoints("1,2; 3 4") == [(1.0, 2.0), (3.0, 4.0)]
    with pytest.raises(ValueError):
        parse_waypoints("1,2,3")


def test_platform_motion_drift_is_applied_from_config():
    from simulator.camera_model import CameraModel
    from simulator.disturbances import DisturbanceConfig
    from simulator.renderer import SimulatorEngine
    from simulator.scene import Scene
    cfg = {"disturbances": {"platform_motion": {"enabled": True, "mode": "linear", "max_px_frame": 16}}}
    dcfg = DisturbanceConfig.from_config(cfg)
    cam = CameraModel()
    engine = SimulatorEngine(Scene(), cam, dcfg)
    x0, y0 = cam.world_x, cam.world_y
    engine.step(1 / 30)
    moved_cam_px = math.hypot(cam.world_x - x0, cam.world_y - y0) / cam.world_px_per_deg * cam.px_per_deg_x
    assert abs(moved_cam_px - 16) < 1e-6


def test_every_platform_mode_produces_drift():
    from simulator.disturbances import PlatformMotionDrift
    for mode in ("linear", "circular", "random", "spiral", "figure8"):
        d = PlatformMotionDrift(mode=mode, max_px_frame=10)
        total = sum(abs(a) + abs(b) for a, b in (d.step(1 / 30) for _ in range(60)))
        assert total > 0, mode