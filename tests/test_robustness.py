"""Robustness/stress tests: extreme-but-legal disturbance settings, target
motion the PTZ physically cannot keep up with, tiny/large camera and screen
sizes, many simultaneous targets, a long noisy run, and a target that is
never detectable at all -- all run through the real TrackingRunner, never a
mock. These don't check specific numeric accuracy (test_*.py already covers
formula correctness); they check the engine survives and reports sane
(finite, non-crashing) metrics under conditions well outside the "happy
path" a demo normally exercises. This is what stands between "works in the
rehearsed demo" and "breaks live in front of judges."
"""
import copy
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from control.run_loop import TrackingRunner
from perception.frame_source import FrameSource, Frame
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene

import numpy as np
import pytest


def _base_cfg():
    path = os.path.join(os.path.dirname(__file__), "..", "config", "default_config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def _build_sim(cfg, seed=1):
    scene = Scene.from_config(cfg)
    cam_cfg = cfg["camera"]
    camera = CameraModel(width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                          fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                          world_x=cfg["screen"]["width"] / 2, world_y=cfg["screen"]["height"] / 2)
    ptz = PTZActuator(camera, cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
    dcfg = DisturbanceConfig.from_config(cfg)
    engine = SimulatorEngine(scene, camera, dcfg, seed=seed)
    from perception.frame_source import SimulatorFrameSource
    fs = SimulatorFrameSource(engine, fps=cfg["camera"]["update_rate_hz"])
    return fs, camera, ptz


def _assert_finite_metrics(m: dict):
    numeric_keys = ("avg_tracking_error_px", "max_tracking_error_px", "rmse_px",
                     "avg_angular_error_urad", "max_angular_error_urad",
                     "avg_pointing_loss_db", "max_pointing_loss_db",
                     "fps", "processing_time_per_frame_ms", "lock_retention_rate",
                     "handoff_ready_rate")
    for k in numeric_keys:
        v = m.get(k)
        if v is None:
            continue
        assert math.isfinite(v), f"{k} is not finite: {v}"


def test_all_disturbances_at_max_legal_values():
    """Every disturbance stacked at once, at (or near) its schema-legal
    maximum, run for several hundred frames. Real demos will almost never
    combine max jitter + max turbulence + max noise + platform drift at
    once, but a judge poking every slider during Q&A might."""
    cfg = _base_cfg()
    cfg["disturbances"] = {
        "noise": {
            "salt_pepper": {"enabled": True, "amount": 0.30},
            "gaussian": {"enabled": True, "sigma": 40},
            "poisson": {"enabled": True},
        },
        "max_noise_std_px": 20,
        "jitter": {"enabled": True, "max_px": 30, "structured": True, "resonance_hz": 15.0},
        "atmosphere": {"mode": "fog"},
        "turbulence": {"enabled": True, "r0": 0.01, "physical": True,
                        "wavelength_nm": 1550.0, "altitude_m": 20000.0, "zenith_deg": 89.0},
        "platform_motion": {"enabled": True, "mode": "spiral", "max_px_frame": 20},
    }
    fs, camera, ptz = _build_sim(cfg)
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                             ground_truth_fn=lambda: fs.last_ground_truth)
    # Physical-turbulence rendering does a real FFT phase-screen per frame
    # (~90ms/frame per the technical report's own measurement) -- kept
    # short here since this test is about surviving the combination, not
    # about turbulence throughput (already covered by the benchmark
    # matrix).
    result = runner.run(max_frames=60)
    _assert_finite_metrics(result.metrics)
    assert result.metrics["fps"] >= 0


def test_target_faster_than_ptz_can_slew():
    """Target speed set far beyond what the configured PTZ max slew rate
    can follow. The tracker should degrade to searching/reacquiring
    instead of crashing or reporting a nonsensical lock."""
    cfg = _base_cfg()
    cfg["ptz"]["max_pan_speed_deg_s"] = 1.0
    cfg["ptz"]["max_tilt_speed_deg_s"] = 1.0
    cfg["target"]["motion"] = "straight_line"
    cfg["target"]["motion_params"] = dict(cfg["target"]["motion_params"])
    cfg["target"]["motion_params"]["straight_line"] = {"speed_px_s": 900, "angle_deg": 40}
    fs, camera, ptz = _build_sim(cfg)
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                             ground_truth_fn=lambda: fs.last_ground_truth)
    result = runner.run(max_frames=300)
    _assert_finite_metrics(result.metrics)
    states = {t.lock_state for t in result.telemetry_log}
    assert states <= {"searching", "acquiring", "locked", "reacquiring"}


def test_tiny_camera_resolution():
    cfg = _base_cfg()
    cfg["camera"]["resolution"] = [160, 120]
    cfg["target"]["size_px"] = [5, 5]
    fs, camera, ptz = _build_sim(cfg)
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                             ground_truth_fn=lambda: fs.last_ground_truth)
    result = runner.run(max_frames=200)
    _assert_finite_metrics(result.metrics)


def test_large_screen_many_targets():
    cfg = _base_cfg()
    cfg["screen"] = {"width": 5000, "height": 5000}
    cfg["target"]["num_targets"] = 5
    fs, camera, ptz = _build_sim(cfg)
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                             ground_truth_fn=lambda: fs.last_ground_truth)
    result = runner.run(max_frames=200)
    _assert_finite_metrics(result.metrics)


def test_long_noisy_run_stays_stable():
    """~2000 frames (well beyond a typical ~900-frame demo run) under moderate combined
    disturbances -- catches slow-accumulating bugs (covariance blow-up,
    unbounded state, timestamp drift) that a short run would miss.
    Deliberately excludes turbulence: that's a per-frame FFT phase-screen
    render (~90ms/frame per the technical report), so it's stress-tested
    for correctness in the smaller max-legal-values test above and for
    throughput in the benchmark matrix, not repeated 5000x here."""
    cfg = _base_cfg()
    cfg["disturbances"]["jitter"] = {"enabled": True, "max_px": 15, "structured": False}
    cfg["disturbances"]["noise"]["gaussian"] = {"enabled": True, "sigma": 15}
    fs, camera, ptz = _build_sim(cfg)
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                             ground_truth_fn=lambda: fs.last_ground_truth)
    result = runner.run(max_frames=2000)
    _assert_finite_metrics(result.metrics)
    assert len(result.telemetry_log) == 2000


class _NeverDetectableFrameSource(FrameSource):
    """A frame source that always yields a blank frame -- no target ever
    present. Models the worst case for judges: nothing to lock onto for
    the entire run. The pipeline must stay in 'searching' and finalize()
    must not divide by a zero denominator."""

    def __init__(self, n_frames=300, width=640, height=480, fov_deg=(4.0, 3.0)):
        self._n = n_frames
        self._i = 0
        self._width = width
        self._height = height
        self._fov_deg = fov_deg

    def get_frame(self):
        if self._i >= self._n:
            return None
        img = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        self._i += 1
        return Frame(image=img, timestamp=self._i / 30.0, frame_id=self._i, fov_deg=self._fov_deg)

    def get_fps(self):
        return 30.0

    def is_live(self):
        return False


def test_target_never_detected():
    cfg = _base_cfg()
    fs = _NeverDetectableFrameSource(n_frames=300)
    runner = TrackingRunner(cfg, fs, camera=None, ptz=None, ground_truth_fn=None)
    result = runner.run(max_frames=300)
    _assert_finite_metrics(result.metrics)
    assert all(t.lock_state == "searching" for t in result.telemetry_log)
    assert result.metrics["acquisition_time_sec"] is None
    assert result.metrics["lock_retention_rate"] == 0.0
