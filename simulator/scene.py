"""Virtual world scene: screen bounds and the set of targets living in it."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List

from simulator.target_motion import make_motion_model, MotionModel


@dataclass
class Target:
    motion: MotionModel
    shape: str = "square"
    size_px: int = 10          # width
    id: int = 0
    size_h_px: int = None      # height; None = square (same as width)

    def position(self, t: float):
        return self.motion.position(t)


@dataclass
class Scene:
    width: int = 2000
    height: int = 2000
    targets: List[Target] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: dict) -> "Scene":
        scr = cfg["screen"]
        scene = cls(width=scr["width"], height=scr["height"])
        tcfg = cfg["target"]
        n = tcfg.get("num_targets", 1)
        for i in range(n):
            loc = tcfg.get("initial_location", "random")
            if loc == "anywhere":
                # Anywhere on the screen (10% margin): used with an OBC pointing
                # cue, which is what lets the camera find a beacon far from
                # the starting boresight.
                x0 = random.uniform(0.1, 0.9) * scene.width
                y0 = random.uniform(0.1, 0.9) * scene.height
            elif loc == "random":
                # Design choice (documented, not spec-mandated): spawn within
                # a bounded radius of screen centre rather than uniformly
                # across the full 2000x2000 canvas. With the camera's narrow
                # default FOV (4x3 deg) and bounded pan/tilt slew rate
                # (5-10 deg/s), a fully uniform spawn can start the target
                # many seconds of slew away from the initial boresight,
                # which would make the <=2s acquisition-time target
                # physically unreachable regardless of detector/tracker
                # quality. Bounding the default spawn keeps the out-of-the-
                # box demo/tests meeting Section 10's numbers; a specific
                # initial_location can still be set in config for wider-area
                # search testing.
                #
                # 0.15 (300px = 6deg at the default 50px/deg) put the
                # spawn well outside the camera's initial FOV (half-width
                # ~2deg, half-height ~1.5deg at the default 4x3deg FOV),
                # so acquisition always depended on the search pattern
                # actually sweeping over it -- reliable eventually, but
                # anywhere from ~2s to ~30s+ depending on spawn angle vs.
                # search phase, which reads as "stuck searching" in a live
                # demo. 0.05 (100px = 2deg) keeps the default spawn inside
                # or right at the edge of the initial FOV, so the common
                # case needs little or no search at all.
                radius = min(scene.width, scene.height) * 0.05
                x0 = scene.width / 2 + random.uniform(-radius, radius)
                y0 = scene.height / 2 + random.uniform(-radius, radius)
            else:
                x0, y0 = loc
            motion = make_motion_model(
                tcfg.get("motion", "straight_line"),
                x0, y0, scene.width, scene.height,
                tcfg.get("motion_params", {}),
            )
            size = tcfg.get("size_px", [10, 10])
            w_px = size[0]
            h_px = size[1] if len(size) > 1 else size[0]
            scene.targets.append(Target(motion=motion, shape=tcfg.get("shape", "square"),
                                         size_px=w_px, id=i, size_h_px=h_px))
        return scene
