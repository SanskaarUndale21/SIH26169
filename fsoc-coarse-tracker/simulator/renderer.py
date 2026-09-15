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
                 platform_motion: PlatformMotionDrift | None = None, seed: int = 0,
                 background_level: int = 20):
        """background_level: dark-current/bias floor the rendered image
        starts from before disturbances are injected, instead of pure 0.
        Every real focal-plane-array sensor has a nonzero black level;
        without it, additive Gaussian noise on a 0 background is a
        half-Gaussian (clipped at 0 for the ~50% of samples that would go
        negative), which biases a median/MAD-based robust background
        estimator (perception/detector.py) toward reading near-zero noise
        even when real injected sigma is large -- that mismatch let
        thousands of noise pixels look like valid detections and both
        tanked accuracy and FPS under the Gaussian-noise disturbance.
        A modest nonzero floor keeps the noise distribution symmetric
        (until it saturates near 255) so the robust estimator reads the
        true noise level."""
        self.scene = scene
        self.camera = camera
        self.disturbance_cfg = disturbance_cfg
        self.platform_motion = platform_motion
        self.rng = np.random.default_rng(seed)
        self.t = 0.0
        self.background_level = background_level

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
        img = np.full((h, w), self.background_level, dtype=np.uint8)
        gt_positions = []
        for target in self.scene.targets:
            xt, yt = target.position(self.t)
            u, v = self.camera.world_to_camera_px(xt, yt)
            if self.camera.is_in_fov(u, v):
                gt_positions.append((u, v))
                _draw_target(img, u, v, target.size_px, target.shape)
        img, info = apply_disturbances(img, self.disturbance_cfg, self.rng)
        # Jitter shifts the rendered image content itself (sensor-level
        # shake), so the target's *reported* ground-truth position must
        # shift with it too, or every jittered frame would show a spurious
        # ~jitter-magnitude "tracking error" even though the detector
        # correctly found the target exactly where it was actually drawn.
        if "jitter_dx" in info:
            gt_positions = [(u + info["jitter_dx"], v + info["jitter_dy"]) for u, v in gt_positions]
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
