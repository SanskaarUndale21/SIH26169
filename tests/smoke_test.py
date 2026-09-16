"""Quick headless smoke test: simulator -> perception -> control loop for a
few seconds on the clean straight-line scenario, printed metrics."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from control.run_loop import TrackingRunner
from perception.frame_source import SimulatorFrameSource
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene


def build_sim(cfg, motion="straight_line", disturbance_overrides=None):
    cfg = dict(cfg)
    cfg["target"] = dict(cfg["target"])
    cfg["target"]["motion"] = motion
    if disturbance_overrides:
        cfg["disturbances"] = disturbance_overrides
    scene = Scene.from_config(cfg)
    cam_cfg = cfg["camera"]
    camera = CameraModel(width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                          fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                          world_x=cfg["screen"]["width"] / 2, world_y=cfg["screen"]["height"] / 2)
    ptz = PTZActuator(camera, cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
    dcfg = DisturbanceConfig.from_config(cfg)
    engine = SimulatorEngine(scene, camera, dcfg, seed=1)
    fs = SimulatorFrameSource(engine, fps=cfg["camera"]["update_rate_hz"])
    return fs, camera, ptz, engine


def main():
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "default_config.yaml")) as f:
        cfg = yaml.safe_load(f)

    for motion in ["straight_line", "circular", "figure8", "random"]:
        fs, camera, ptz, engine = build_sim(cfg, motion)
        runner = TrackingRunner(cfg, fs, camera=camera, ptz=ptz,
                                 ground_truth_fn=lambda: fs.last_ground_truth)
        result = runner.run(max_frames=900)
        m = result.metrics
        print(f"[{motion}] acq={m['acquisition_time_sec']} avg_err={m['avg_tracking_error_px']} "
              f"max_err={m['max_tracking_error_px']} lock_retention={m['lock_retention_rate']} "
              f"fps={m['fps']} loss_events={len(m['target_loss_events'])}")


if __name__ == "__main__":
    main()
