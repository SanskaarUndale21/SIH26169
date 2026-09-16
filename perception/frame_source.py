"""FrameSource interface (Section 5.1). Two concrete implementations:
SimulatorFrameSource and VideoFileFrameSource, both producing identical
Frame objects so Perception+Tracking never needs to know which one is live.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

import cv2
import numpy as np


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float
    frame_id: int
    fov_deg: Optional[Tuple[float, float]] = None


class FrameSource(Protocol):
    def get_frame(self) -> Optional[Frame]: ...
    def get_fps(self) -> float: ...
    def is_live(self) -> bool: ...


class SimulatorFrameSource:
    """Wraps a SimulatorEngine; each get_frame() advances the sim by one
    tick and renders. Ground truth (for benchmark logging only) is exposed
    via last_ground_truth, never through the Frame itself."""

    def __init__(self, engine, fps: float = 30.0):
        from simulator.renderer import SimulatorEngine
        self.engine: SimulatorEngine = engine
        self._fps = fps
        self._dt = 1.0 / fps
        self._frame_id = 0
        self.last_ground_truth = []

    def get_frame(self) -> Optional[Frame]:
        self.engine.step(self._dt)
        img, gt = self.engine.render()
        self.last_ground_truth = gt
        frame = Frame(
            image=img,
            timestamp=self.engine.t,
            frame_id=self._frame_id,
            fov_deg=(self.engine.camera.fov_x_deg, self.engine.camera.fov_y_deg),
        )
        self._frame_id += 1
        return frame

    def get_fps(self) -> float:
        return self._fps

    def is_live(self) -> bool:
        return True


class VideoFileFrameSource:
    """Reads frames from a raw .mp4 file, bypassing the simulator/PTZ
    entirely, per Benchmark Performance-2. fov_deg is None since it is not
    meaningful for an externally captured video."""

    def __init__(self, path: str):
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise IOError(f"cannot open video file: {path}")
        self._fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._frame_id = 0
        self._t0 = None

    def get_frame(self) -> Optional[Frame]:
        ok, img = self.cap.read()
        if not ok:
            return None
        if img.ndim == 3 and img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ts = self._frame_id / self._fps
        frame = Frame(image=img, timestamp=ts, frame_id=self._frame_id, fov_deg=None)
        self._frame_id += 1
        return frame

    def get_fps(self) -> float:
        return self._fps

    def is_live(self) -> bool:
        return False

    def release(self):
        self.cap.release()
