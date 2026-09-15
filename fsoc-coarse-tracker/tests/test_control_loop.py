import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from control.pid_controller import PIDPointingController
from simulator.camera_model import CameraModel, PTZActuator


def test_pid_output_clamped_to_max_speed():
    cfg = {"control": {"pid": {"pan": {"kp": 100, "ki": 0, "kd": 0}, "tilt": {"kp": 100, "ki": 0, "kd": 0}}},
           "ptz": {"max_pan_speed_deg_s": 5.0, "max_tilt_speed_deg_s": 5.0}}
    controller = PIDPointingController(cfg)
    pan_rate, tilt_rate = controller.compute(error_x_deg=50, error_y_deg=-50, dt=0.05)
    assert abs(pan_rate) <= 5.0
    assert abs(tilt_rate) <= 5.0


def test_pid_reduces_error_over_iterations():
    cfg = {"control": {"pid": {"pan": {"kp": 2.0, "ki": 0.1, "kd": 0.1}, "tilt": {"kp": 2.0, "ki": 0.1, "kd": 0.1}}},
           "ptz": {"max_pan_speed_deg_s": 10.0, "max_tilt_speed_deg_s": 10.0}}
    controller = PIDPointingController(cfg)
    camera = CameraModel(world_x=1000, world_y=1000, world_px_per_deg=50)
    ptz = PTZActuator(camera, 10.0, 10.0)
    target_world = (1100, 1050)  # fixed target the camera must centre on
    dt = 1 / 30.0
    errors = []
    for _ in range(120):
        u, v = camera.world_to_camera_px(*target_world)
        err_x_deg = (u - camera.width_px / 2) / camera.px_per_deg_x
        err_y_deg = (v - camera.height_px / 2) / camera.px_per_deg_y
        errors.append(abs(err_x_deg) + abs(err_y_deg))
        pan_rate, tilt_rate = controller.compute(err_x_deg, err_y_deg, dt)
        ptz.step(pan_rate, tilt_rate, dt)
    assert errors[-1] < errors[0]
    assert errors[-1] < 1.0  # converged to within ~1 deg


def test_ptz_kinematics_respects_speed_clamp():
    camera = CameraModel(world_x=0, world_y=0, world_px_per_deg=50)
    ptz = PTZActuator(camera, max_pan_speed_deg_s=5.0, max_tilt_speed_deg_s=5.0)
    ptz.step(pan_rate_cmd_deg_s=1000, tilt_rate_cmd_deg_s=-1000, dt=1.0)
    # world_x should move by at most 5 deg * 50 px/deg = 250 px in 1s
    assert abs(camera.world_x) <= 250 + 1e-6
    assert abs(camera.world_y) <= 250 + 1e-6
