"""Real-time performance plots: tracking error, FPS, lock-state timeline,
plus a live readout of the auto-computed performance metrics."""
from __future__ import annotations

import time
from collections import deque

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

LOCK_STATE_CODE = {"searching": 0, "acquiring": 1, "reacquiring": 2, "locked": 3}


class DashboardPanel(QWidget):
    def __init__(self, parent=None, max_points: int = 300):
        super().__init__(parent)
        self.max_points = max_points
        self.t_hist = deque(maxlen=max_points)
        self.err_hist = deque(maxlen=max_points)
        self.fps_hist = deque(maxlen=max_points)
        self.state_hist = deque(maxlen=max_points)
        self._last_frame_wall_t = None

        layout = QGridLayout(self)

        pg.setConfigOptions(antialias=True)
        self.err_plot = pg.PlotWidget(title="Tracking error (px)")
        self.err_curve = self.err_plot.plot(pen=pg.mkPen("#e05252", width=2))
        self.err_plot.addLine(y=10, pen=pg.mkPen("#888", style=Qt.DashLine))

        self.fps_plot = pg.PlotWidget(title="FPS")
        self.fps_curve = self.fps_plot.plot(pen=pg.mkPen("#4a90d9", width=2))
        self.fps_plot.addLine(y=20, pen=pg.mkPen("#888", style=Qt.DashLine))

        self.state_plot = pg.PlotWidget(title="Lock state (0=searching 1=acquiring 2=reacquiring 3=locked)")
        self.state_curve = self.state_plot.plot(pen=pg.mkPen("#5cb85c", width=2))

        layout.addWidget(self.err_plot, 0, 0)
        layout.addWidget(self.fps_plot, 1, 0)
        layout.addWidget(self.state_plot, 2, 0)

        self.metrics_label = QLabel("")
        self.metrics_label.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.metrics_label, 3, 0)

    def update_from_telemetry(self, telemetry, tracking_error):
        now = time.perf_counter()
        fps = 1.0 / max(now - self._last_frame_wall_t, 1e-6) if self._last_frame_wall_t else 0.0
        self._last_frame_wall_t = now

        self.t_hist.append(telemetry.timestamp)
        self.err_hist.append(tracking_error if tracking_error is not None else float("nan"))
        self.fps_hist.append(fps)
        self.state_hist.append(LOCK_STATE_CODE.get(telemetry.lock_state, 0))

        t = list(self.t_hist)
        self.err_curve.setData(t, list(self.err_hist))
        self.fps_curve.setData(t, list(self.fps_hist))
        self.state_curve.setData(t, list(self.state_hist))

    def update_metrics_readout(self, metrics: dict):
        lines = [f"{k}: {v}" for k, v in metrics.items()]
        self.metrics_label.setText("\n".join(lines))
