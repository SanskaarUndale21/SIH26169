"""Main GUI window: wires config panel -> frame source -> perception
pipeline -> control loop -> video/dashboard panels -> performance logger.
Uses a QTimer-driven step loop (rather than TrackingRunner.run()'s blocking
loop) so the UI stays responsive; the per-frame logic mirrors run_loop.py.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QMainWindow, QMessageBox, QPushButton,
                                QSplitter, QStatusBar, QVBoxLayout, QWidget)

from control.actuator_interface import NullActuator, SimulatorActuator
from control.pid_controller import PIDPointingController
from control.search_driver import RasterSweepDriver, SpiralSweepDriver
from gui.config_panel import ConfigPanel
from gui.dashboard_panel import DashboardPanel
from gui.video_panel import VideoPanel
from perception.frame_source import SimulatorFrameSource, VideoFileFrameSource
from perception.pipeline import PerceptionTrackingPipeline
from perf_logging.performance_logger import RunMetrics, write_run_log
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
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

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.reset_btn = QPushButton("Reset")
        self.stop_btn.setEnabled(False)
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.reset_btn)
        self.start_btn.clicked.connect(self.start_run)
        self.stop_btn.clicked.connect(self.stop_run)
        self.reset_btn.clicked.connect(self.reset_run)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.video_panel)
        left_layout.addWidget(controls)

        splitter = QSplitter()
        splitter.addWidget(self.config_panel)
        splitter.addWidget(left)
        splitter.addWidget(self.dashboard_panel)
        splitter.setSizes([260, 640, 420])
        self.setCentralWidget(splitter)

        self.setStatusBar(QStatusBar())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)

        self._reset_runtime_state()

    def _reset_runtime_state(self):
        self.frame_source = None
        self.pipeline = None
        self.controller = None
        self.actuator = None
        self.camera = None
        self.raster_search = RasterSweepDriver(5.0, 5.0)
        self.initial_search = SpiralSweepDriver(5.0)
        self.spiral_search = SpiralSweepDriver(5.0)
        self.metrics = RunMetrics()
        self.prev_lock_state = None

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
                self.raster_search = RasterSweepDriver(cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
                self.initial_search = SpiralSweepDriver(min(cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"]))
                self.spiral_search = SpiralSweepDriver(min(cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"]))
        except Exception as exc:
            QMessageBox.critical(self, "Error starting run", str(exc))
            return

        self.pipeline = None
        self.controller = PIDPointingController(cfg)
        self.metrics = RunMetrics()
        self.prev_lock_state = None
        self.config = cfg

        self.timer.start(int(1000 / max(cfg["camera"]["update_rate_hz"], 1)))
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.statusBar().showMessage("Running...")

    def step(self):
        frame = self.frame_source.get_frame()
        if frame is None:
            self.stop_run()
            return
        if self.pipeline is None:
            self.pipeline = PerceptionTrackingPipeline(self.config, frame.image.shape[1], frame.image.shape[0])

        telemetry = self.pipeline.process(frame)

        if self.camera is not None and frame.fov_deg is not None:
            dt_ctrl = 1.0 / max(self.frame_source.get_fps(), 1.0)
            if telemetry.lock_state in ("locked", "acquiring"):
                err_x_deg = (telemetry.predicted_px[0] - frame.image.shape[1] / 2) / self.camera.px_per_deg_x
                err_y_deg = (telemetry.predicted_px[1] - frame.image.shape[0] / 2) / self.camera.px_per_deg_y
                pan_rate, tilt_rate = self.controller.compute(err_x_deg, err_y_deg, dt_ctrl)
            elif telemetry.lock_state == "reacquiring":
                if self.prev_lock_state != "reacquiring":
                    self.spiral_search.recenter()
                pan_rate, tilt_rate = self.spiral_search.next_rate(dt_ctrl)
                self.controller.reset()
            else:
                pan_rate, tilt_rate = self.initial_search.next_rate(dt_ctrl)
                self.controller.reset()
            self.actuator.command(pan_rate, tilt_rate, dt_ctrl)
            telemetry.pointing_command_deg = (pan_rate, tilt_rate)
            self.prev_lock_state = telemetry.lock_state

        tracking_error = None
        if self.frame_source.is_live():
            gts = getattr(self.frame_source, "last_ground_truth", [])
            if gts:
                px, py = telemetry.predicted_px
                tracking_error = min(((px - gx) ** 2 + (py - gy) ** 2) ** 0.5 for gx, gy in gts)

        self.metrics.record_frame(telemetry.timestamp, telemetry.lock_state, tracking_error, 0.0)
        self.video_panel.show_frame(frame.image, telemetry)
        self.dashboard_panel.update_from_telemetry(telemetry, tracking_error)
        self.dashboard_panel.update_metrics_readout(self.metrics.finalize())
        self.statusBar().showMessage(f"frame {frame.frame_id}  lock={telemetry.lock_state}")

    def stop_run(self):
        self.timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.statusBar().showMessage("Stopped. Writing performance log...")
        out_dir = self.base_config.get("logging", {}).get("output_dir", "logs")
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), out_dir)
        try:
            m = self.metrics.finalize()
            json_path, csv_path = write_run_log(m, out_dir)
            self.statusBar().showMessage(f"Log written: {json_path}")
        except Exception as exc:
            self.statusBar().showMessage(f"Log write failed: {exc}")

    def reset_run(self):
        self.stop_run()
        self.video_panel.label.setText("No frame yet")
        self._reset_runtime_state()
