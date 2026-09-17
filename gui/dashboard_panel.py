"""Real-time performance dashboard: tracking-error/FPS/lock-state plots,
plus a proper metric-card readout (colour-coded against the Section 10
thresholds, with units) instead of a raw dict dump.
"""
from __future__ import annotations

import time
from collections import deque

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget)

LOCK_STATE_CODE = {"searching": 0, "acquiring": 1, "reacquiring": 2, "locked": 3}

# Section 10 hard performance targets: (comparison, threshold, unit).
# Only metrics with an actual pass/fail target from the spec belong here
# -- everything else (link-budget additions, RMSE, event counts) has no
# hard threshold to colour-code against, but still needs a unit shown so
# the card isn't a bare, context-free number. See UNITS below for those.
THRESHOLDS = {
    "acquisition_time_sec": ("<=", 2.0, "s"),
    "avg_tracking_error_px": ("<=", 10.0, "px"),
    "max_tracking_error_px": ("<=", 10.0, "px"),
    "fps": (">=", 20.0, "FPS"),
    "lock_retention_rate": (">=", 0.95, ""),
    "processing_time_per_frame_ms": ("<=", 50.0, "ms"),
}

# Units for metrics that don't have a hard Section 10 threshold (so they
# aren't colour-coded pass/fail) but still need a unit label rather than
# showing as a bare, unlabelled number -- this was the actual cause of
# cards like "Max pointing loss: 60.00" or "Handoff-ready rate: 0.950"
# rendering with no unit at all in an earlier screenshot.
UNITS = {
    "simulation_duration_sec": "s",
    "rmse_px": "px",
    "avg_angular_error_urad": "µrad",
    "max_angular_error_urad": "µrad",
    "avg_pointing_loss_db": "dB",
    "max_pointing_loss_db": "dB",
    "handoff_ready_rate": "%",
    "time_to_handoff_ready_sec": "s",
    "re_acquisition_count": "",
}
# handoff_ready_rate and lock_retention_rate are stored as 0-1 fractions;
# format them as a percentage rather than a bare decimal ("0.950" reads
# as a mysterious tiny number, "95.0%" reads immediately).
PERCENT_KEYS = {"handoff_ready_rate", "lock_retention_rate"}

METRIC_LABELS = {
    "simulation_duration_sec": "Sim duration",
    "fps": "FPS",
    "acquisition_time_sec": "Acquisition time",
    "avg_tracking_error_px": "Avg tracking error",
    "max_tracking_error_px": "Max tracking error",
    "lock_retention_rate": "Lock retention",
    "processing_time_per_frame_ms": "Proc. time/frame",
    "rmse_px": "RMSE",
    "re_acquisition_count": "Re-acquisitions",
    "avg_angular_error_urad": "Avg angular error",
    "max_angular_error_urad": "Max angular error",
    "avg_pointing_loss_db": "Avg pointing loss",
    "max_pointing_loss_db": "Max pointing loss",
    "handoff_ready_rate": "Coarse-to-fine handoff rate",
    "time_to_handoff_ready_sec": "Time to coarse-to-fine handoff",
}

CARD_STYLE_BASE = """
    QLabel#card {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; padding: 8px 10px; }}
"""


def _verdict(key: str, val) -> str:
    if key not in THRESHOLDS or val is None:
        return "na"
    op, threshold, _ = THRESHOLDS[key]
    ok = (val <= threshold) if op == "<=" else (val >= threshold)
    return "ok" if ok else "bad"


def _fmt(key: str, val, unit: str) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, list):
        return f"{len(val)} event(s)"
    if isinstance(val, bool):
        return "yes" if val else "no"
    if key in PERCENT_KEYS and isinstance(val, (int, float)):
        return f"{val * 100:.1f}%"
    if isinstance(val, (int, float)):
        s = f"{val:.3f}" if abs(val) < 10 else f"{val:.2f}"
        return f"{s} {unit}".strip()
    return str(val)


class MetricCard(QLabel):
    COLORS = {
        "ok": ("#0f2a1a", "#22c55e", "#4ade80"),
        "bad": ("#2a1414", "#ef4444", "#f87171"),
        "na": ("#171922", "#23262f", "#9ca3af"),
    }

    def __init__(self, key: str):
        super().__init__()
        self.key = key
        self.setObjectName("card")
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setMinimumWidth(160)
        self.setMinimumHeight(52)
        self.set_value(None)

    def set_value(self, val):
        unit = THRESHOLDS.get(self.key, (None, None, None))[2]
        if unit is None:
            unit = UNITS.get(self.key, "")
        verdict = _verdict(self.key, val)
        bg, border, text_color = self.COLORS[verdict]
        label = METRIC_LABELS.get(self.key, self.key.replace("_", " "))
        value_str = _fmt(self.key, val, unit)
        self.setStyleSheet(
            f"QLabel {{ background: {bg}; border: 1px solid {border}; border-radius: 8px; "
            f"padding: 8px 12px; }}"
        )
        self.setText(
            f"<div style='font-size:10px; color:#9ca3af; text-transform:uppercase;'>{label}</div>"
            f"<div style='font-size:18px; font-weight:600; color:{text_color};'>{value_str}</div>"
        )


class DashboardPanel(QWidget):
    def __init__(self, parent=None, max_points: int = 300):
        super().__init__(parent)
        self.max_points = max_points
        self.t_hist = deque(maxlen=max_points)
        self.err_hist = deque(maxlen=max_points)
        self.fps_hist = deque(maxlen=max_points)
        self.state_hist = deque(maxlen=max_points)
        self._last_frame_wall_t = None

        outer = QVBoxLayout(self)

        # Real-time pyqtgraph performance recipe (antialiasing + per-frame
        # auto-ranging are the two classic costs that don't show up in an
        # offscreen/headless benchmark but dominate real windowed
        # rendering -- this is what was actually behind the GUI's FPS
        # reading staying under 20 despite the tracking engine itself
        # running well above it): antialiasing off, mouse interaction off
        # (skips its hit-testing overhead), and each plot's Y range fixed
        # once to its known meaningful range instead of recomputed via
        # auto-range on every single setData() call.
        pg.setConfigOptions(antialias=False)

        self.err_plot = self._make_plot("Tracking error (px)", "#e05252", y_range=(0, 15), threshold=10)
        self.err_curve = self.err_plot.plot(pen=pg.mkPen("#e05252", width=2))
        self.err_plot.addLine(y=10, pen=pg.mkPen("#888", style=Qt.DashLine))

        self.fps_plot = self._make_plot("FPS", "#4a90d9", y_range=(0, 60), threshold=20)
        self.fps_curve = self.fps_plot.plot(pen=pg.mkPen("#4a90d9", width=2))
        self.fps_plot.addLine(y=20, pen=pg.mkPen("#888", style=Qt.DashLine))

        self.state_plot = self._make_plot(
            "Lock state (0=searching 1=acquiring 2=reacquiring 3=locked)", "#5cb85c", y_range=(0, 3))
        self.state_curve = self.state_plot.plot(pen=pg.mkPen("#5cb85c", width=2))

        outer.addWidget(self.err_plot, stretch=2)
        outer.addWidget(self.fps_plot, stretch=2)
        outer.addWidget(self.state_plot, stretch=2)

        cards_label = QLabel("Live performance metrics (Section 10 thresholds colour-coded)")
        cards_label.setStyleSheet("color:#9ca3af; font-size: 11px; margin-top: 6px;")
        outer.addWidget(cards_label)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(8)
        self._cards: dict = {}
        cards_container = QWidget()
        cards_container.setLayout(self.cards_grid)
        scroll = QScrollArea()
        scroll.setWidget(cards_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(220)
        outer.addWidget(scroll, stretch=1)

    def _make_plot(self, title: str, color: str, y_range: tuple, threshold: float = None) -> pg.PlotWidget:
        plot = pg.PlotWidget(title=title)
        plot.setMouseEnabled(x=False, y=False)  # skip interaction hit-testing every frame
        plot.hideButtons()
        plot.setYRange(*y_range, padding=0)
        plot.enableAutoRange(axis='y', enable=False)
        plot.enableAutoRange(axis='x', enable=True)  # X (time) still needs to scroll with the run
        plot.setDownsampling(mode='peak')
        plot.setClipToView(True)
        return plot

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
        for key, val in metrics.items():
            if key not in self._cards:
                card = MetricCard(key)
                idx = len(self._cards)
                self.cards_grid.addWidget(card, idx // 2, idx % 2)
                self._cards[key] = card
            self._cards[key].set_value(val)
