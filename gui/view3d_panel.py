"""Live 3D visualization of the pan/tilt PAT geometry (pyqtgraph.opengl).

This is a genuine geometric rendering of real simulation state, not a
decorative animation:

- The camera's PTZ pointing direction (a cone/frustum) is placed using
  cam_pan_deg/cam_tilt_deg, which are the CameraModel's own world_x/world_y
  state converted to degrees (perf_logging/frame_log.py's
  camera_pan_tilt_deg) -- i.e. exactly where the simulated gimbal is
  physically aimed at this frame.
- The target marker is placed using the simulator's own ground-truth
  target position (converted to the same angular convention), never the
  detector's estimate -- so you can see tracking lag/error as the visual
  gap between the tracker's cone and the true target dot.
- The tracker's *belief* (predicted_px, converted from camera-pixel space
  back to an absolute angle by adding the camera's own pan/tilt) is drawn
  as a second, dimmer marker, so the ground truth vs. tracker-estimate
  gap is directly visible in 3D, not just in the 2D error plot.

A fixed nominal "range" places these angular quantities at a 3D point
(range * tan(pan), range * tan(tilt), range) purely so pan/tilt has
somewhere to be drawn -- the simulator does not model true 3D range (it
is a 2D coarse-alignment sim per the spec), so this range is a display
convention, not a claimed physical distance. It is labeled as such in
the panel and never presented as a measured value.

In raw-video (Benchmark-2) mode there is no PTZ/camera-model geometry at
all, so this panel shows a clear "3D view unavailable in raw-video mode"
placeholder instead of fabricating a scene.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PySide6.QtWidgets import QLabel, QStackedLayout, QVBoxLayout, QWidget

LOCK_COLORS = {
    "searching": (0.85, 0.25, 0.25, 1.0),
    "acquiring": (0.9, 0.75, 0.15, 1.0),
    "reacquiring": (0.9, 0.75, 0.15, 1.0),
    "locked": (0.25, 0.85, 0.35, 1.0),
}

# Display-only nominal range (world units) at which angular quantities
# are drawn -- see module docstring. Not a measured or configured value.
DISPLAY_RANGE = 400.0
TRAIL_MAX_POINTS = 400


def _angles_to_point(pan_deg: float, tilt_deg: float, range_units: float = DISPLAY_RANGE):
    pan = math.radians(pan_deg)
    tilt = math.radians(tilt_deg)
    x = range_units * math.tan(pan)
    y = range_units * math.tan(tilt)
    z = range_units
    return x, y, z


class View3DPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedLayout(self)

        self._unavailable_label = QLabel(
            "3D view unavailable: this run has no PTZ/camera-model geometry\n"
            "(raw-video / Benchmark-2 mode bypasses the simulator's camera entirely,\n"
            "so there is no real pan/tilt or ground-truth position to plot)."
        )
        self._unavailable_label.setStyleSheet("color:#888; padding: 40px; font-size: 13px;")
        self._unavailable_label.setWordWrap(True)

        self._view_container = QWidget()
        vlayout = QVBoxLayout(self._view_container)
        note = QLabel(f"Angular geometry drawn at a fixed display range ({DISPLAY_RANGE:.0f} world units) "
                       "-- a visualization convention, not a measured distance (this simulator is 2D).")
        note.setStyleSheet("color:#888; font-size: 10px; padding: 4px 8px;")
        note.setWordWrap(True)
        vlayout.addWidget(note)

        self.gl_view = gl.GLViewWidget()
        self.gl_view.setCameraPosition(distance=900, elevation=25, azimuth=-60)
        grid = gl.GLGridItem()
        grid.setSize(x=800, y=800)
        grid.setSpacing(x=50, y=50)
        self.gl_view.addItem(grid)
        axis = gl.GLAxisItem()
        axis.setSize(x=150, y=150, z=150)
        self.gl_view.addItem(axis)
        vlayout.addWidget(self.gl_view)

        self._view_container.setLayout(vlayout)
        self._stack.addWidget(self._unavailable_label)
        self._stack.addWidget(self._view_container)

        # Camera pointing cone (real gimbal direction)
        cone_mesh = gl.MeshData.cylinder(rows=4, cols=16, radius=[0.001, 40.0], length=DISPLAY_RANGE * 0.9)
        self.cone_item = gl.GLMeshItem(meshdata=cone_mesh, smooth=False, shader="shaded",
                                        color=(0.3, 0.5, 0.9, 0.35), drawEdges=True)
        self.gl_view.addItem(self.cone_item)

        # Ground-truth target marker (real simulator position)
        self.target_scatter = gl.GLScatterPlotItem(pos=np.zeros((1, 3)), size=14,
                                                     color=(0.2, 0.9, 0.3, 1.0))
        self.gl_view.addItem(self.target_scatter)

        # Tracker's belief (predicted_px projected back to absolute angle)
        self.belief_scatter = gl.GLScatterPlotItem(pos=np.zeros((1, 3)), size=10,
                                                     color=(0.9, 0.9, 0.3, 0.85))
        self.gl_view.addItem(self.belief_scatter)

        # Trails: real target path and real camera-boresight path
        self.target_trail = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(0.2, 0.9, 0.3, 0.5), width=2)
        self.gl_view.addItem(self.target_trail)
        self.cam_trail = gl.GLLinePlotItem(pos=np.zeros((2, 3)), color=(0.3, 0.5, 0.9, 0.5), width=2)
        self.gl_view.addItem(self.cam_trail)

        self._target_history: deque = deque(maxlen=TRAIL_MAX_POINTS)
        self._cam_history: deque = deque(maxlen=TRAIL_MAX_POINTS)
        self._live_mode = False

        self.reset()

    def set_live_mode(self, has_camera: bool):
        """Called once at run start: has_camera=False (raw-video mode)
        shows the honest 'unavailable' placeholder instead of an empty or
        fabricated 3D scene."""
        self._live_mode = has_camera
        self._stack.setCurrentIndex(1 if has_camera else 0)

    def reset(self):
        self._target_history.clear()
        self._cam_history.clear()
        self._stack.setCurrentIndex(0)

    def update_frame(self, record):
        """record: a perf_logging.frame_log.FrameRecord (or an object/dict
        with the same fields) for the frame just processed. Every number
        drawn here comes from that record -- nothing is synthesized."""
        if record.cam_pan_deg is None or record.cam_tilt_deg is None:
            return  # no real geometry for this frame (shouldn't happen once set_live_mode(True))

        cam_pt = _angles_to_point(record.cam_pan_deg, record.cam_tilt_deg)
        self._cam_history.append(cam_pt)

        color = LOCK_COLORS.get(record.lock_state, (0.6, 0.6, 0.6, 1.0))
        self.cone_item.setColor((color[0], color[1], color[2], 0.35))
        self._point_cone_at(cam_pt)

        if record.ground_truth_px:
            fov = record.fov_deg or (4.0, 3.0)
            # Ground-truth centroid is in this frame's camera-pixel space;
            # convert back to an absolute world angle by adding the
            # camera's own current pan/tilt to the pixel-space angular
            # offset from image centre -- the same linear model
            # CameraModel uses, run in reverse.
            gx, gy = record.ground_truth_px[0]
            px_per_deg_x = 640 / fov[0]
            px_per_deg_y = 480 / fov[1]
            target_pan = record.cam_pan_deg + (gx - 320) / px_per_deg_x
            target_tilt = record.cam_tilt_deg + (gy - 240) / px_per_deg_y
            target_pt = _angles_to_point(target_pan, target_tilt)
            self._target_history.append(target_pt)
            self.target_scatter.setData(pos=np.array([target_pt]))

        px, py = record.predicted_px
        fov = record.fov_deg or (4.0, 3.0)
        px_per_deg_x = 640 / fov[0]
        px_per_deg_y = 480 / fov[1]
        belief_pan = record.cam_pan_deg + (px - 320) / px_per_deg_x
        belief_tilt = record.cam_tilt_deg + (py - 240) / px_per_deg_y
        belief_pt = _angles_to_point(belief_pan, belief_tilt)
        self.belief_scatter.setData(pos=np.array([belief_pt]))

        if len(self._target_history) >= 2:
            self.target_trail.setData(pos=np.array(self._target_history))
        if len(self._cam_history) >= 2:
            self.cam_trail.setData(pos=np.array(self._cam_history))

    def _point_cone_at(self, tip_point):
        """Repositions the cone mesh so its axis points from the origin
        (camera position) toward tip_point -- a real rotation derived
        from the actual pan/tilt angles, not a cosmetic wobble."""
        self.cone_item.resetTransform()
        length = math.sqrt(sum(c * c for c in tip_point))
        if length < 1e-6:
            return
        # Cylinder mesh's own axis is +Z; rotate it to point at tip_point.
        dx, dy, dz = tip_point
        # Rotation axis = Z x target_dir (cross product), angle = arccos(dot)
        target_dir = (dx / length, dy / length, dz / length)
        z_axis = (0, 0, 1)
        cross = (z_axis[1] * target_dir[2] - z_axis[2] * target_dir[1],
                 z_axis[2] * target_dir[0] - z_axis[0] * target_dir[2],
                 z_axis[0] * target_dir[1] - z_axis[1] * target_dir[0])
        cross_len = math.sqrt(sum(c * c for c in cross))
        dot = z_axis[0] * target_dir[0] + z_axis[1] * target_dir[1] + z_axis[2] * target_dir[2]
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        if cross_len > 1e-6:
            axis = (cross[0] / cross_len, cross[1] / cross_len, cross[2] / cross_len)
            self.cone_item.rotate(angle_deg, axis[0], axis[1], axis[2])
