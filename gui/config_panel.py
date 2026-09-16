"""Parameter configuration panel exposing every Section 3 control, plus the
input-source selector (Simulator vs. .mp4 file) required to satisfy
Benchmark-2 -- it's the literal switch that swaps the FrameSource
implementation in main_window.py."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                                QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                                QPushButton, QSpinBox, QVBoxLayout, QWidget)


class ConfigPanel(QWidget):
    def __init__(self, base_config: dict, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(base_config)
        self.video_path = None
        layout = QVBoxLayout(self)

        # --- input source ---
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
        layout.addWidget(src_group)

        # --- scenario preset ---
        scenario_group = QGroupBox("Scenario preset (optional)")
        f = QFormLayout(scenario_group)
        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(["(none -- use generic target/motion below)",
                                       "leo_leo_crosslink", "leo_ground_downlink", "geo_ground"])
        f.addRow("Preset", self.scenario_combo)
        note = QLabel("Overrides target motion + link budget with values\nderived from real orbital mechanics.")
        note.setStyleSheet("color: #888; font-size: 10px;")
        f.addRow(note)
        layout.addWidget(scenario_group)

        # --- target ---
        target_group = QGroupBox("Target")
        f = QFormLayout(target_group)
        self.motion_combo = QComboBox()
        self.motion_combo.addItems(["straight_line", "circular", "figure8", "random", "spiral"])
        self.motion_combo.setCurrentText(self.config["target"]["motion"])
        f.addRow("Motion", self.motion_combo)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["square", "circle"])
        self.shape_combo.setCurrentText(self.config["target"]["shape"])
        f.addRow("Shape", self.shape_combo)
        self.size_spin = QSpinBox(); self.size_spin.setRange(5, 20)
        self.size_spin.setValue(self.config["target"]["size_px"][0])
        f.addRow("Size (px)", self.size_spin)
        layout.addWidget(target_group)

        # --- camera ---
        cam_group = QGroupBox("Camera")
        f = QFormLayout(cam_group)
        self.fov_x_spin = QDoubleSpinBox(); self.fov_x_spin.setRange(0.5, 30)
        self.fov_x_spin.setValue(self.config["camera"]["fov_deg"][0])
        self.fov_y_spin = QDoubleSpinBox(); self.fov_y_spin.setRange(0.5, 30)
        self.fov_y_spin.setValue(self.config["camera"]["fov_deg"][1])
        f.addRow("FOV X (deg)", self.fov_x_spin)
        f.addRow("FOV Y (deg)", self.fov_y_spin)
        layout.addWidget(cam_group)

        # --- PTZ ---
        ptz_group = QGroupBox("PTZ speed limits")
        f = QFormLayout(ptz_group)
        self.pan_speed_spin = QDoubleSpinBox(); self.pan_speed_spin.setRange(1, 30)
        self.pan_speed_spin.setValue(self.config["ptz"]["max_pan_speed_deg_s"])
        self.tilt_speed_spin = QDoubleSpinBox(); self.tilt_speed_spin.setRange(1, 30)
        self.tilt_speed_spin.setValue(self.config["ptz"]["max_tilt_speed_deg_s"])
        f.addRow("Max pan speed (deg/s)", self.pan_speed_spin)
        f.addRow("Max tilt speed (deg/s)", self.tilt_speed_spin)
        layout.addWidget(ptz_group)

        # --- disturbances ---
        dist_group = QGroupBox("Disturbances")
        f = QFormLayout(dist_group)
        self.sp_check = QCheckBox("Salt & pepper noise")
        self.gauss_check = QCheckBox("Gaussian noise")
        self.poisson_check = QCheckBox("Poisson noise")
        self.jitter_check = QCheckBox("Camera jitter")
        self.jitter_structured_check = QCheckBox("Structured (resonant) jitter")
        self.turbulence_check = QCheckBox("Atmospheric turbulence (slow, ~10 FPS alone)")
        self.atmo_combo = QComboBox()
        self.atmo_combo.addItems(["clear", "haze", "fog", "rain", "low_light"])
        f.addRow(self.sp_check)
        f.addRow(self.gauss_check)
        f.addRow(self.poisson_check)
        f.addRow(self.jitter_check)
        f.addRow(self.jitter_structured_check)
        f.addRow(self.turbulence_check)
        f.addRow("Atmosphere", self.atmo_combo)
        layout.addWidget(dist_group)

        layout.addStretch(1)
        self._on_source_changed(0)

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

    def build_config(self) -> dict:
        cfg = copy.deepcopy(self.config)
        cfg["target"]["motion"] = self.motion_combo.currentText()
        cfg["target"]["shape"] = self.shape_combo.currentText()
        cfg["target"]["size_px"] = [self.size_spin.value(), self.size_spin.value()]
        cfg["camera"]["fov_deg"] = [self.fov_x_spin.value(), self.fov_y_spin.value()]
        cfg["ptz"]["max_pan_speed_deg_s"] = self.pan_speed_spin.value()
        cfg["ptz"]["max_tilt_speed_deg_s"] = self.tilt_speed_spin.value()
        cfg["disturbances"]["noise"]["salt_pepper"]["enabled"] = self.sp_check.isChecked()
        cfg["disturbances"]["noise"]["gaussian"]["enabled"] = self.gauss_check.isChecked()
        cfg["disturbances"]["noise"]["poisson"]["enabled"] = self.poisson_check.isChecked()
        cfg["disturbances"]["jitter"]["enabled"] = self.jitter_check.isChecked()
        cfg["disturbances"]["jitter"]["structured"] = self.jitter_structured_check.isChecked()
        cfg["disturbances"]["turbulence"]["enabled"] = self.turbulence_check.isChecked()
        cfg["disturbances"]["atmosphere"]["mode"] = self.atmo_combo.currentText()

        preset_idx = self.scenario_combo.currentIndex()
        if preset_idx > 0:
            from simulator.scenario_presets import apply_preset
            cfg = apply_preset(self.scenario_combo.currentText(), cfg)
        return cfg
