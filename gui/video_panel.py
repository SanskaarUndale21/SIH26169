"""Live video panel: renders the current camera frame with a detection/
prediction overlay marker and a lock-state colour-coded indicator."""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

LOCK_COLORS = {
    "searching": (0, 0, 255),      # red (BGR)
    "acquiring": (0, 255, 255),    # yellow
    "reacquiring": (0, 255, 255),  # yellow
    "locked": (0, 200, 0),         # green
}


class VideoPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("No frame yet")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumSize(480, 360)
        self.label.setStyleSheet("background:#111; color:#888;")
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)

    def show_frame(self, image: np.ndarray, telemetry):
        if image.ndim == 2:
            disp = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            disp = image.copy()

        color = LOCK_COLORS.get(telemetry.lock_state, (255, 255, 255))
        h, w = disp.shape[:2]
        cv2.rectangle(disp, (2, 2), (w - 3, h - 3), color, 3)

        if telemetry.centroid_px is not None:
            cx, cy = int(telemetry.centroid_px[0]), int(telemetry.centroid_px[1])
            cv2.drawMarker(disp, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
        px, py = telemetry.predicted_px
        cv2.circle(disp, (int(px), int(py)), 10, color, 2)
        cv2.putText(disp, telemetry.lock_state.upper(), (8, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
        # FastTransformation (nearest-neighbour) instead of
        # SmoothTransformation (bilinear): real, measurable per-frame cost
        # with no meaningful visual difference at the panel's typical
        # display size, and one of the classic Qt real-time-rendering
        # costs that only shows up with real window compositing, not in
        # an offscreen benchmark.
        pix = QPixmap.fromImage(qimg).scaled(self.label.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        self.label.setPixmap(pix)
