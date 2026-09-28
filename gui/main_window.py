"""Main GUI window: wires config panel -> frame source -> perception
pipeline -> control loop -> video/dashboard panels -> performance logger.
Uses a QTimer-driven step loop (rather than TrackingRunner.run()'s blocking
loop) so the UI stays responsive; the per-frame logic mirrors run_loop.py.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
                                QSplitter, QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from control.actuator_interface import NullActuator, SimulatorActuator
from control.stepper import PointingStepper
from gui.config_panel import ConfigPanel
from gui.dashboard_panel import DashboardPanel
from gui.video_panel import VideoPanel
from gui.view3d_panel import View3DPanel
from perception.frame_source import SimulatorFrameSource, VideoFileFrameSource
from perception.pipeline import PerceptionTrackingPipeline
from perf_logging.frame_log import FrameLogWriter, FrameRecord, camera_pan_tilt_deg
from perf_logging.performance_logger import RunMetrics, write_run_log
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.link_budget import (LinkBudgetConfig, is_handoff_ready, pointing_loss_db,
                                    px_error_to_angular_error)
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene


class MainWindow(QMainWindow):
    def __init__(self, base_config: dict):
        super().__init__()
        self.setWindowTitle("FSOC Coarse-Alignment Tracker")
        self.base_config = base_config

        self.config_panel = ConfigPanel(base_config)
        self.video_panel = VideoPanel()
        self.dashboard_panel = DashboardPanel()
        self.view3d_panel = View3DPanel()

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.dashboard_panel, "2D Dashboard")
        self.right_tabs.addTab(self.view3d_panel, "3D View")
        self.right_tabs.currentChanged.connect(self._on_right_tab_changed)

        # --- Header: product identity + the lock-state badge that also
        # appears colour-coded in the video overlay, kept in sync here so
        # the current run state is visible even with the window narrow. ---
        header = QWidget()
        header.setObjectName("headerBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        title_label = QLabel("FSOC Coarse-Alignment Tracker")
        title_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        subtitle_label = QLabel("AI-based virtual PAT system for FSOC coarse alignment")
        subtitle_label.setStyleSheet("font-size: 11px; color: #8b90a0;")
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(title_label)
        title_col.addWidget(subtitle_label)
        self.status_badge = QLabel("IDLE")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignCenter)
        self.status_badge.setFixedWidth(110)
        self._set_status_badge("idle")
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_badge)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 8, 0, 0)
        controls_layout.setSpacing(10)
        self.start_btn = QPushButton("▶  Start")
        self.start_btn.setObjectName("startBtn")
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.reset_btn = QPushButton("↻  Reset")
        self.stop_btn.setEnabled(False)
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.reset_btn)
        controls_layout.addStretch(1)
        self.start_btn.clicked.connect(self.start_run)
        self.stop_btn.clicked.connect(self.stop_run)
        self.reset_btn.clicked.connect(self.reset_run)

        left = QWidget()
        left.setObjectName("centerPane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        video_title = QLabel("LIVE FEED")
        video_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #8b90a0; letter-spacing: 1px;")
        left_layout.addWidget(video_title)
        left_layout.addWidget(self.video_panel, stretch=1)
        left_layout.addWidget(controls)

        splitter = QSplitter()
        splitter.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(self.config_panel)
        splitter.addWidget(left)
        splitter.addWidget(self.right_tabs)
        splitter.setSizes([300, 660, 460])
        splitter.setHandleWidth(2)

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(header)
        central_layout.addWidget(splitter, stretch=1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)

        self._reset_runtime_state()

    def _set_status_badge(self, state: str):
        # Copper = engaged/locked (the one accent, reserved for a
        # genuinely good state), pewter = processing/searching/acquiring
        # (busy, not bad), muted red-brown = idle-but-was-an-error. Same
        # two-hue-plus-neutral convention as gui/theme.py's palette --
        # state is read from colour intensity, not a different colour
        # per state.
        colors = {
            "idle": ("#1e1a15", "#6b6e75"),
            "running": ("rgba(217, 138, 79, 0.16)", "#ffb066"),
            "locked": ("rgba(217, 138, 79, 0.16)", "#ffb066"),
            "searching": ("rgba(147, 161, 176, 0.14)", "#c3ccd6"),
            "acquiring": ("rgba(147, 161, 176, 0.14)", "#c3ccd6"),
            "reacquiring": ("rgba(147, 161, 176, 0.14)", "#c3ccd6"),
        }
        bg, fg = colors.get(state, colors["idle"])
        self.status_badge.setText(state.upper())
        self.status_badge.setFixedHeight(26)
        self.status_badge.setStyleSheet(
            f"background: {bg}; color: {fg}; border: 1px solid {fg}; "
            f"border-radius: 13px; padding: 0 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px;"
        )

    def _reset_runtime_state(self):
        self.frame_source = None
        self.pipeline = None
        self.stepper = None
        self.actuator = None
        self.camera = None
        self.metrics = RunMetrics()
        self.frame_log = FrameLogWriter()
        self._ref_world_xy = None
        self._current_run_name = None
        self._last_frame = None
        self._last_telemetry = None
        self._last_tracking_error = None
        self._last_record = None
        self.view3d_panel.reset()

    def _on_right_tab_changed(self, index: int):
        """Catches the panel that just became visible up to the latest
        real data immediately, rather than leaving it stale until the
        next timer tick (which step()'s visibility gating would
        otherwise skip rendering for while a different tab was active)."""
        if self._last_telemetry is None:
            return
        if index == 0:
            self.dashboard_panel.update_from_telemetry(self._last_telemetry, self._last_tracking_error)
            self.dashboard_panel.update_metrics_readout(self.metrics.finalize())
        elif index == 1 and self._last_record is not None:
            self.view3d_panel.update_frame(self._last_record)

    def start_run(self):
        cfg = self.config_panel.build_config()
        try:
            if self.config_panel.is_video_mode():
                if not self.config_panel.video_path:
                    QMessageBox.warning(self, "No file", "Select a .mp4 file first.")
                    return
                self.frame_source = VideoFileFrameSource(self.config_panel.video_path)
                self.camera = None
                self.actuator = NullActuator()
            else:
                scene = Scene.from_config(cfg)
                cam_cfg = cfg["camera"]
                self.camera = CameraModel(
                    width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                    fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                    world_x=cfg["screen"]["width"] / 2, world_y=cfg["screen"]["height"] / 2,
                )
                ptz = PTZActuator(self.camera, cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
                dcfg = DisturbanceConfig.from_config(cfg)
                engine = SimulatorEngine(scene, self.camera, dcfg)
                self.frame_source = SimulatorFrameSource(engine, fps=cam_cfg["update_rate_hz"])
                self.actuator = SimulatorActuator(ptz)
                self._ref_world_xy = (cfg["screen"]["width"] / 2, cfg["screen"]["height"] / 2)
        except Exception as exc:
            QMessageBox.critical(self, "Error starting run", str(exc))
            return

        self.pipeline = None
        self.stepper = PointingStepper(cfg, self.camera) if self.camera is not None else None
        self.link_cfg = LinkBudgetConfig.from_config(cfg)
        self.metrics = RunMetrics()
        self.frame_log = FrameLogWriter()
        self.view3d_panel.reset()
        self.view3d_panel.set_live_mode(self.camera is not None)
        self.config = cfg
        import time as _time
        self._current_run_name = _time.strftime("run_%Y%m%d_%H%M%S")

        self.timer.start(int(1000 / max(cfg["camera"]["update_rate_hz"], 1)))
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_status_badge("running")
        self.statusBar().showMessage("Running...")

    def step(self):
        frame = self.frame_source.get_frame()
        if frame is None:
            self.stop_run()
            return
        if self.pipeline is None:
            self.pipeline = PerceptionTrackingPipeline(self.config, frame.image.shape[1], frame.image.shape[0])

        telemetry = self.pipeline.process(frame)

        if self.stepper is not None and frame.fov_deg is not None:
            dt_ctrl = 1.0 / max(self.frame_source.get_fps(), 1.0)
            pan_rate, tilt_rate = self.stepper.step(telemetry, frame.image.shape[1],
                                                      frame.image.shape[0], dt_ctrl)
            self.actuator.command(pan_rate, tilt_rate, dt_ctrl)
            telemetry.pointing_command_deg = (pan_rate, tilt_rate)

        tracking_error = centroid_error = None
        if self.frame_source.is_live():
            gts = getattr(self.frame_source, "last_ground_truth", [])
            if gts:
                px, py = telemetry.predicted_px
                tracking_error = min(((px - gx) ** 2 + (py - gy) ** 2) ** 0.5 for gx, gy in gts)
                if telemetry.centroid_px is not None:
                    cx, cy = telemetry.centroid_px
                    centroid_error = min(((cx - gx) ** 2 + (cy - gy) ** 2) ** 0.5 for gx, gy in gts)

        angular_error = link_loss = None
        handoff_ready = None
        if tracking_error is not None and frame.fov_deg is not None:
            angular_error = px_error_to_angular_error(tracking_error, frame.fov_deg[0], frame.image.shape[1])
            link_loss = pointing_loss_db(angular_error, self.link_cfg.beam_divergence_urad)
            handoff_ready = is_handoff_ready(angular_error, self.link_cfg.fine_stage_capture_range_urad)
        self.metrics.record_frame(telemetry.timestamp, telemetry.lock_state, tracking_error, 0.0,
                                   angular_error_urad=angular_error, link_loss_db=link_loss,
                                   handoff_ready=handoff_ready, centroid_error_px=centroid_error)

        cam_pan_deg = cam_tilt_deg = None
        if self.camera is not None and self._ref_world_xy is not None:
            cam_pan_deg, cam_tilt_deg = camera_pan_tilt_deg(
                self.camera.world_x, self.camera.world_y,
                self._ref_world_xy[0], self._ref_world_xy[1], self.camera.world_px_per_deg)
        ground_truth_px = None
        if self.frame_source.is_live():
            gts = getattr(self.frame_source, "last_ground_truth", [])
            ground_truth_px = [(float(x), float(y)) for x, y in gts] if gts else []
        record = FrameRecord(
            frame_id=telemetry.frame_id, timestamp=telemetry.timestamp, detected=telemetry.detected,
            centroid_px=telemetry.centroid_px, predicted_px=telemetry.predicted_px,
            lock_state=telemetry.lock_state, confidence=telemetry.confidence,
            pointing_command_deg=telemetry.pointing_command_deg, fov_deg=frame.fov_deg,
            cam_pan_deg=cam_pan_deg, cam_tilt_deg=cam_tilt_deg, ground_truth_px=ground_truth_px,
        )
        self.frame_log.add(record)

        # Cache the latest frame/telemetry/record so a tab switch can
        # catch the now-visible panel up immediately (see
        # _on_right_tab_changed) without waiting for the next tick.
        self._last_frame = frame
        self._last_telemetry = telemetry
        self._last_tracking_error = tracking_error
        self._last_record = record

        # Only pay for real Qt/OpenGL repaint work on panels the user can
        # actually see right now. The video feed sits in its own always-
        # visible pane, but the 2D dashboard and 3D view share one tab
        # widget -- only one of them is ever on screen. Rendering the
        # hidden one every frame was pure waste, and on a machine without
        # a proper GPU driver the 3D view's OpenGL repaint can silently
        # fall back to slow software rendering and drag the whole step()
        # loop with it even while the user is looking at the 2D tab. The
        # real telemetry/metrics/frame data is still recorded above
        # every frame regardless -- only the expensive repaint is skipped.
        current_tab = self.right_tabs.currentIndex()
        if self.video_panel.isVisible():
            self.video_panel.show_frame(frame.image, telemetry)
        if current_tab == 0:
            self.dashboard_panel.update_from_telemetry(telemetry, tracking_error)
            self.dashboard_panel.update_metrics_readout(self.metrics.finalize())
        elif current_tab == 1:
            self.view3d_panel.update_frame(record)
        self._set_status_badge(telemetry.lock_state)
        self.statusBar().showMessage(f"frame {frame.frame_id}  lock={telemetry.lock_state}")

    def stop_run(self):
        self.timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._set_status_badge("idle")
        if self._current_run_name is None:
            self.statusBar().showMessage("Nothing to stop -- no run was started.")
            return
        self.statusBar().showMessage("Stopped. Writing performance log...")
        out_dir = self.base_config.get("logging", {}).get("output_dir", "logs")
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", out_dir)
        out_dir = os.path.normpath(out_dir)
        try:
            m = self.metrics.finalize()
            run_name = self._current_run_name
            json_path, csv_path = write_run_log(m, out_dir, run_name)
            msg = f"Log written: {json_path}"
            if self.frame_log.records:
                frames_path = os.path.join(out_dir, f"{run_name}_frames.jsonl")
                self.frame_log.write(frames_path)
                msg += f"  |  3D replay: {frames_path}"
            self.statusBar().showMessage(msg)
        except Exception as exc:
            self.statusBar().showMessage(f"Log write failed: {exc}")

    def reset_run(self):
        self.stop_run()
        self.video_panel.label.setText("No frame yet")
        self._reset_runtime_state()
