"""Per-frame telemetry recorder: the real-data backbone for both 3D
visualizations (gui/view3d_panel.py and web/dashboard_server.py's replay
view). RunMetrics (performance_logger.py) only keeps aggregates; this
keeps the actual frame-by-frame trace of a run so it can be replayed
later, exactly as it happened -- no interpolation, no synthesized frames,
no fabricated positions.

Every field here is either read directly off a real Telemetry record or
computed from the simulator's own CameraModel/target-motion state at that
frame. When a field has no real value for a given run (e.g. cam_pan_deg
in raw-video mode, which has no PTZ), it is written as null rather than a
placeholder number -- consumers must treat null as "not available", never
as zero.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple


@dataclass
class FrameRecord:
    frame_id: int
    timestamp: float
    detected: bool
    centroid_px: Optional[Tuple[float, float]]
    predicted_px: Tuple[float, float]
    lock_state: str
    confidence: float
    pointing_command_deg: Tuple[float, float]
    # --- Simulator-only fields (None in raw-video / Benchmark-2 mode,
    # since there is no PTZ or camera-model geometry to report there) ---
    fov_deg: Optional[Tuple[float, float]] = None
    cam_pan_deg: Optional[float] = None
    cam_tilt_deg: Optional[float] = None
    # Ground truth target position(s) in camera pixel space, only present
    # in simulator mode and only for the simulator's OWN diagnostic/
    # visualization use -- never fed back into the tracker (see
    # simulator/renderer.py's docstring on this same point).
    ground_truth_px: Optional[List[Tuple[float, float]]] = None


class FrameLogWriter:
    """Accumulates FrameRecords in memory during a run (cheap: a run of a
    few thousand frames is a few MB at most) and writes them as JSON
    Lines on save -- one real, immutable record per frame, append-only."""

    def __init__(self):
        self.records: List[FrameRecord] = []

    def add(self, record: FrameRecord):
        self.records.append(record)

    def write(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for r in self.records:
                f.write(json.dumps(asdict(r)) + "\n")


def read_frame_log(path: str) -> List[dict]:
    """Reads a JSONL frame log back into a list of dicts. Used by the web
    dashboard (which deliberately does not import from this package --
    see web/dashboard_server.py's own docstring on staying decoupled --
    so this function exists here for GUI/tooling reuse, and the web
    server re-implements the same trivial JSONL parse independently)."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def camera_pan_tilt_deg(cam_world_x: float, cam_world_y: float,
                         ref_world_x: float, ref_world_y: float,
                         world_px_per_deg: float) -> Tuple[float, float]:
    """Real pan/tilt angle (degrees) of the camera boresight relative to
    a fixed reference point (the configured initial boresight position,
    i.e. the PTZ gimbal's zero reference) -- derived directly from the
    CameraModel's own world_x/world_y state and world_px_per_deg scale,
    never fabricated. This is the same linear small-angle convention
    CameraModel.world_to_camera_px already uses for the target."""
    pan_deg = (cam_world_x - ref_world_x) / world_px_per_deg
    tilt_deg = (cam_world_y - ref_world_y) / world_px_per_deg
    return pan_deg, tilt_deg
