"""Renders a camera Frame from the current scene + camera state, applying
platform motion drift and disturbances. This is the Simulator module's
single output surface -- Perception+Tracking never touches anything here
directly, only the Frame objects that come out of it via frame_source.py.
"""
from __future__ import annotations

import numpy as np

from simulator.camera_model import CameraModel
from simulator.disturbances import DisturbanceConfig, PlatformMotionDrift, apply_disturbances
from simulator.scene import Scene


class SimulatorEngine:
    def __init__(self, scene: Scene, camera: CameraModel, disturbance_cfg: DisturbanceConfig,
                 platform_motion: PlatformMotionDrift | None = None, seed: int = 0):
        self.scene = scene
        self.camera = camera
        self.disturbance_cfg = disturbance_cfg
        self.platform_motion = platform_motion
        self.rng = np.random.default_rng(seed)
        self.t = 0.0

    def step(self, dt: float):
        self.t += dt
        if self.platform_motion is not None:
            dx, dy = self.platform_motion.step(dt)
            self.camera.world_x += dx
            self.camera.world_y += dy

    def render(self) -> tuple[np.ndarray, list[tuple[float, float]]]:
        """Returns (image, list of in-FOV ground-truth target centres in
        camera pixel coords) -- the ground truth is for the Simulator's own
        benchmark logging only, never fed to Perception+Tracking."""
        w, h = self.camera.width_px, self.camera.height_px
        img = np.zeros((h, w), dtype=np.uint8)
        gt_positions = []
        for target in self.scene.targets:
            xt, yt = target.position(self.t)
            u, v = self.camera.world_to_camera_px(xt, yt)
            if self.camera.is_in_fov(u, v):
                gt_positions.append((u, v))
                _draw_target(img, u, v, target.size_px, target.shape)
        img, _ = apply_disturbances(img, self.disturbance_cfg, self.rng)
        return img, gt_positions


def _draw_target(img: np.ndarray, u: float, v: float, size: int, shape: str):
    h, w = img.shape[:2]
    half = size // 2
    cu, cv = int(round(u)), int(round(v))
    if shape == "circle":
        import cv2
        cv2.circle(img, (cu, cv), max(1, half), 255, -1, lineType=cv2.LINE_AA)
    else:
        x0, x1 = max(0, cu - half), min(w, cu + half + 1)
        y0, y1 = max(0, cv - half), min(h, cv + half + 1)
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 255
