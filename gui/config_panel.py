"""Parameter configuration panel: dynamically built from
config/param_schema.py, so every tweakable simulation parameter (screen
size, camera, target motion of all four types, PTZ limits, every
disturbance's intensity, detector/tracker/PID gains, link budget,
scenario presets) gets a widget here automatically -- there is no
hand-maintained subset that can drift out of sync with what the engine
actually reads, and no parameter silently missing from the UI.

Also owns the input-source selector (Simulator vs. .mp4 file) required
for Benchmark-2 -- it's the literal switch that swaps the FrameSource
implementation in main_window.py.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                                QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                QPushButton, QScrollArea, QSlider, QSpinBox,
                                QTabWidget, QVBoxLayout, QWidget)

from config.param_schema import GROUP_ORDER, PARAM_SCHEMA, flatten_config_to_ui_values, get_path


class _NumericRow(QWidget):
    """A slider + spinbox pair kept in sync, with a unit label -- this is
    what makes every numeric parameter genuinely tweakable at a glance
    (drag the slider for a quick sweep, or type an exact value) rather
    than a bare spinbox with no sense of its own range."""

    def __init__(self, param, parent=None):
        super().__init__(parent)
        self.param = param
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.slider = QSlider(Qt.Horizontal)
        is_int = param.kind == "int"
        scale = 1 if is_int else max(1, int(round(1 / (param.step or 0.1))))
        self._scale = scale
        self.slider.setMinimum(int(round(param.min * scale)))
        self.slider.setMaximum(int(round(param.max * scale)))
        self.slider.setValue(int(round(param.default * scale)))

        if is_int:
            self.spin = QSpinBox()
            self.spin.setRange(int(param.min), int(param.max))
            self.spin.setSingleStep(int(param.step or 1))
            self.spin.setValue(int(param.default))
        else:
            self.spin = QDoubleSpinBox()
            self.spin.setRange(param.min, param.max)
            self.spin.setSingleStep(param.step or 0.1)
            self.spin.setDecimals(3 if (param.step or 0.1) < 0.1 else 2)
            self.spin.setValue(param.default)
        if param.unit:
            self.spin.setSuffix(f" {param.unit}")

        self.slider.valueChanged.connect(self._slider_to_spin)
        self.spin.valueChanged.connect(self._spin_to_slider)

        layout.addWidget(self.slider, stretch=3)
        layout.addWidget(self.spin, stretch=1)

        if param.help:
            self.setToolTip(param.help)
            self.slider.setToolTip(param.help)

    def _slider_to_spin(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v / self._scale)
        self.spin.blockSignals(False)

    def _spin_to_slider(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v * self._scale)))
        self.slider.blockSignals(False)

    def value(self):
        return self.spin.value()

    def set_value(self, v):
        self.spin.setValue(v)


class ConfigPanel(QWidget):
    def __init__(self, base_config: dict, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(base_config)
        self.video_path = None
        self._widgets: dict = {}  # "path/string" -> widget

        outer = QVBoxLayout(self)

        # --- input source (not schema-driven: this is a UI-mode switch,
        # not a simulation parameter) ---
        src_group = QGroupBox("Input source")
        src_layout = QVBoxLayout(src_group)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Simulator", "Load video file (.mp4)"])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        src_layout.addWidget(self.source_combo)
        file_row = QHBoxLayout()
        self.file_label = QLabel("(no file selected)")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_label)
        file_row.addWidget(browse_btn)
        src_layout.addLayout(file_row)
        outer.addWidget(src_group)

        # --- everything else: schema-driven tabs, one per group ---
        tabs = QTabWidget()
        outer.addWidget(tabs, stretch=1)

        by_group: dict = {}
        for p in PARAM_SCHEMA:
            by_group.setdefault(p.group, []).append(p)

        ui_values = flatten_config_to_ui_values(self.config)
        for group in GROUP_ORDER:
            params = by_group.get(group)
            if not params:
                continue
            tab = QWidget()
            form = QFormLayout(tab)
            for p in params:
                key = "/".join(str(k) for k in p.path)
                current = ui_values.get(key, p.default)
                widget = self._build_widget(p, current)
                self._widgets[key] = widget
                form.addRow(p.label, widget)
            scroll = QScrollArea()
            scroll.setWidget(tab)
            scroll.setWidgetResizable(True)
            tabs.addTab(scroll, group)

        self._on_source_changed(0)

    def _build_widget(self, param, current_value):
        if param.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(current_value))
            if param.help:
                w.setToolTip(param.help)
            return w
        if param.kind == "enum":
            w = QComboBox()
            for value, display in param.options:
                w.addItem(display, value)
            idx = next((i for i, (v, _) in enumerate(param.options) if v == current_value), 0)
            w.setCurrentIndex(idx)
            if param.help:
                w.setToolTip(param.help)
            return w
        # int / float -> slider + spinbox
        row = _NumericRow(param)
        row.set_value(current_value if current_value is not None else param.default)
        return row

    def _read_widget(self, param, widget):
        if param.kind == "bool":
            return widget.isChecked()
        if param.kind == "enum":
            return widget.currentData()
        return widget.value()

    def _on_source_changed(self, idx):
        is_video = idx == 1
        self.file_label.setEnabled(is_video)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select video file", "", "Video files (*.mp4)")
        if path:
            self.video_path = path
            self.file_label.setText(path)

    def is_video_mode(self) -> bool:
        return self.source_combo.currentIndex() == 1

    def collect_ui_values(self) -> dict:
        """Returns the flat {path_string: value} map straight from the
        widgets -- used both to build a run config (build_config) and to
        show/export the exact parameter set a run used."""
        values = {}
        for p in PARAM_SCHEMA:
            key = "/".join(str(k) for k in p.path)
            widget = self._widgets.get(key)
            if widget is not None:
                values[key] = self._read_widget(p, widget)
        return values

    def build_config(self) -> dict:
        from config.param_schema import apply_scenario_preset_if_set, resolve_ui_values
        ui_values = self.collect_ui_values()
        cfg = resolve_ui_values(self.config, ui_values)
        cfg = apply_scenario_preset_if_set(cfg)
        return cfg
