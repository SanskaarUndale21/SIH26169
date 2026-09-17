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
        self.label = QLabel("No frame yet -- press Start")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumSize(480, 360)
        self.label.setStyleSheet(
            "background:#0b0d12; color:#5b6070; border: 1px solid #242833; border-radius: 8px; font-size: 13px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def show_frame(self, image: np.ndarray, telemetry):
        if image.ndim == 2:
            disp = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            disp = image.copy()

        color = LOCK_COLORS.get(telemetry.lock_state, (255, 255, 255))
        h, w = disp.shape[:2]
        cv2.rectangle(disp, (2, 2), (w - 3, h - 3), color, 3)

        # Boresight crosshair (frame centre, i.e. the camera's fixed
        # pointing reference): always drawn, since it's the one fixed
        # visual anchor the target's position is meaningful relative to
        # -- without it, a target near the edge just looks like "a dot
        # somewhere on screen" rather than "this far off-boresight".
        cx0, cy0 = w // 2, h // 2
        cv2.line(disp, (cx0 - 10, cy0), (cx0 + 10, cy0), (90, 90, 90), 1, cv2.LINE_AA)
        cv2.line(disp, (cx0, cy0 - 10), (cx0, cy0 + 10), (90, 90, 90), 1, cv2.LINE_AA)

        if telemetry.centroid_px is not None:
            cx, cy = int(telemetry.centroid_px[0]), int(telemetry.centroid_px[1])
            cv2.drawMarker(disp, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
        px, py = telemetry.predicted_px
        cv2.circle(disp, (int(px), int(py)), 10, color, 2)

        # Lock-state chip: a filled background box behind the text
        # instead of raw coloured text on black, for real legibility
        # against a bright frame (fog/low-light presets included).
        label_text = f" {telemetry.lock_state.upper()} "
        (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(disp, (6, 6), (10 + tw, 16 + th + baseline), (20, 20, 20), -1)
        cv2.rectangle(disp, (6, 6), (10 + tw, 16 + th + baseline), color, 1)
        cv2.putText(disp, label_text, (8, 12 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

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
