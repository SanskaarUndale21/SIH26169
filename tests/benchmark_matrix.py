"""Section 12 test matrix: crosses every mandatory motion type against
every disturbance condition, runs each for a fixed duration, and reports
pass/fail against Section 10's thresholds. Run with:
    python tests/benchmark_matrix.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random

import yaml

from control.run_loop import TrackingRunner
from perception.frame_source import SimulatorFrameSource
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene

MOTIONS = ["straight_line", "circular", "figure8", "random"]

DISTURBANCE_CONDITIONS = {
    "clean": {},
    "salt_pepper": {"noise": {"salt_pepper": {"enabled": True, "amount": 0.10}}},
    "gaussian": {"noise": {"gaussian": {"enabled": True, "sigma": 10}}},
    "poisson": {"noise": {"poisson": {"enabled": True}}},
    "jitter": {"jitter": {"enabled": True, "max_px": 20}},
    "haze": {"atmosphere": {"mode": "haze"}},
    "fog": {"atmosphere": {"mode": "fog"}},
    "rain": {"atmosphere": {"mode": "rain"}},
    "low_light": {"atmosphere": {"mode": "low_light"}},
    "platform_motion": {"platform_motion": {"enabled": True, "mode": "linear", "max_px_frame": 20}},
    "all_combined": {
        "noise": {"gaussian": {"enabled": True, "sigma": 8}, "salt_pepper": {"enabled": True, "amount": 0.05}},
        "jitter": {"enabled": True, "max_px": 10},
        "atmosphere": {"mode": "fog"},
        "platform_motion": {"enabled": True, "mode": "linear", "max_px_frame": 10},
    },
}

THRESHOLDS = {
    "acquisition_time_sec": ("<=", 2.0),
    "avg_tracking_error_px": ("<=", 10.0),
    "fps": (">=", 20.0),
}


def build_run(cfg: dict, motion: str, disturbance_overrides: dict, seed: int):
    cfg = dict(cfg)
    cfg["target"] = dict(cfg["target"])
    cfg["target"]["motion"] = motion
    base_dist = {"noise": {"salt_pepper": {"enabled": False}, "gaussian": {"enabled": False},
                            "poisson": {"enabled": False}},
                 "jitter": {"enabled": False}, "atmosphere": {"mode": "clear"},
                 "platform_motion": {"enabled": False}}
    for k, v in disturbance_overrides.items():
        if isinstance(v, dict) and k in base_dist and isinstance(base_dist[k], dict):
            base_dist[k].update(v)
        else:
            base_dist[k] = v
    cfg["disturbances"] = base_dist

    random.seed(seed)
    scene = Scene.from_config(cfg)
    cam_cfg = cfg["camera"]
    camera = CameraModel(width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                          fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                          world_x=cfg["screen"]["width"] / 2, world_y=cfg["screen"]["height"] / 2)
    ptz = PTZActuator(camera, cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
    dcfg = DisturbanceConfig.from_config(cfg)
    from simulator.disturbances import PlatformMotionDrift
    platform_motion = None
    pm = cfg["disturbances"].get("platform_motion", {})
    if pm.get("enabled"):
        platform_motion = PlatformMotionDrift(mode=pm.get("mode", "linear"),
                                               max_px_frame=pm.get("max_px_frame", 20))
    engine = SimulatorEngine(scene, camera, dcfg, platform_motion=platform_motion, seed=seed)
    fs = SimulatorFrameSource(engine, fps=cam_cfg["update_rate_hz"])
    runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz, ground_truth_fn=lambda: fs.last_ground_truth)
    return runner


def evaluate(metrics: dict) -> dict:
    results = {}
    for field, (op, threshold) in THRESHOLDS.items():
        val = metrics.get(field)
        if val is None:
            results[field] = "N/A"
            continue
        ok = (val <= threshold) if op == "<=" else (val >= threshold)
        results[field] = "PASS" if ok else "FAIL"
    return results


def run_matrix(duration_frames: int = 300, seed: int = 42):
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "default_config.yaml")
    with open(cfg_path) as f:
        base_cfg = yaml.safe_load(f)

    rows = []
    for motion in MOTIONS:
        for cond_name, overrides in DISTURBANCE_CONDITIONS.items():
            runner = build_run(base_cfg, motion, overrides, seed)
            result = runner.run(max_frames=duration_frames)
            m = result.metrics
            verdict = evaluate(m)
            rows.append({"motion": motion, "condition": cond_name, "metrics": m, "verdict": verdict})
    return rows


def print_summary(rows):
    header = f"{'motion':<14}{'condition':<16}{'acq_s':>8}{'avg_err':>9}{'max_err':>9}{'lock_ret':>9}{'fps':>7}  verdict"
    print(header)
    print("-" * len(header))
    for r in rows:
        m = r["metrics"]
        v = r["verdict"]
        overall = "PASS" if all(x in ("PASS", "N/A") for x in v.values()) else "FAIL"
        print(f"{r['motion']:<14}{r['condition']:<16}"
              f"{str(m.get('acquisition_time_sec')):>8}"
              f"{str(m.get('avg_tracking_error_px')):>9}"
              f"{str(m.get('max_tracking_error_px')):>9}"
              f"{str(m.get('lock_retention_rate')):>9}"
              f"{str(m.get('fps')):>7}  {overall}")


if __name__ == "__main__":
    rows = run_matrix()
    print_summary(rows)
