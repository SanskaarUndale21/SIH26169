"""Shared per-frame pointing-command logic: PID while locked/acquiring,
hybrid spiral->raster search while searching, spiral while reacquiring.

Factored out of run_loop.py (headless) and gui/main_window.py (Qt) so both
call the exact same state machine instead of maintaining two copies that
can drift out of sync -- a real bug earlier in this project's history.
"""
from __future__ import annotations

from typing import Optional, Tuple

from algorithms import registry
from algorithms.api import AlgorithmError, check_point
from control.search_driver import CuedSearchDriver, RasterSweepDriver, SpiralSweepDriver


class PointingStepper:
    def __init__(self, config: dict, camera=None):
        """camera: simulator.camera_model.CameraModel, or None if this run
        has no PTZ to drive (video-file mode)."""
        self.camera = camera
        # Pointing controller comes from the algorithm registry (default:
        # the built-in PID), so a user plugin can replace it.
        w = camera.width_px if camera is not None else 640
        h = camera.height_px if camera is not None else 480
        fov = (camera.fov_x_deg, camera.fov_y_deg) if camera is not None else None
        self.controller = registry.create("controller", config,
                                          registry.context_from_config(config, w, h, fov))
        self._ctrl_name = self.controller.display_name()

        max_pan = config.get("ptz", {}).get("max_pan_speed_deg_s", 5.0)
        max_tilt = config.get("ptz", {}).get("max_tilt_speed_deg_s", 5.0)

        # Raster coverage sized to the full reachable screen (half the
        # screen extent, world-px -> degrees via the camera's
        # world_px_per_deg) so the guaranteed-coverage fallback search
        # actually guarantees coverage, not just a bigger fixed box.
        half_width_deg, half_height_deg = 20.0, 20.0
        if camera is not None:
            screen_cfg = config.get("screen", {})
            half_width_deg = (screen_cfg.get("width", 2000) / 2) / camera.world_px_per_deg
            half_height_deg = (screen_cfg.get("height", 2000) / 2) / camera.world_px_per_deg

        self.raster_search = RasterSweepDriver(max_pan, max_tilt,
                                                half_width_deg=half_width_deg,
                                                half_height_deg=half_height_deg)
        self.initial_search = SpiralSweepDriver(min(max_pan, max_tilt))
        self.spiral_search = SpiralSweepDriver(min(max_pan, max_tilt))

        # Hybrid initial-acquisition search: the spiral is fast for the
        # common case (target within a few degrees of the starting
        # boresight, see scene.py's bounded default spawn) but has no
        # guaranteed coverage bound, so a target that spawned further out
        # or has since drifted away (e.g. fast straight-line motion) could
        # be missed on every pass. After SEARCH_HANDOFF_S of continuous
        # searching with no detection at all, fall back to the raster
        # driver: slower to a first hit on average, but bounded worst case.
        self.SEARCH_HANDOFF_S = 3.0

        # Optional OBC pointing cue (simulator/obc_model.py): when set, the
        # initial search slews to the predicted direction and spirals out to
        # 3 sigma around it before any full-field raster.
        self.cue = None
        self.cued_search: Optional[CuedSearchDriver] = None
        self._ref_world_xy = None
        if camera is not None:
            scr = config.get("screen", {})
            self._ref_world_xy = (scr.get("width", 2000) / 2, scr.get("height", 2000) / 2)
        self._searching_since_t: Optional[float] = None
        self._prev_lock_state: Optional[str] = None

    def set_cue(self, cue):
        """cue: object with .at(t) -> (pan_deg, tilt_deg) and .sigma (deg)."""
        self.cue = cue
        if cue is None or self.camera is None:
            self.cued_search = None
            return
        fov_min = min(self.camera.fov_x_deg, self.camera.fov_y_deg)
        max_speed = min(self.raster_search.max_pan_speed, self.raster_search.max_tilt_speed)
        self.cued_search = CuedSearchDriver(max_speed=max_speed, ring_step_deg=0.8 * fov_min,
                                            extent_deg=max(3.0 * cue.sigma, fov_min))

    def boresight_deg(self) -> Tuple[float, float]:
        """Absolute gimbal pan/tilt (deg) relative to the boresight zero, as
        the gimbal's own encoders would report it."""
        c = self.camera
        return ((c.world_x - self._ref_world_xy[0]) / c.world_px_per_deg,
                (c.world_y - self._ref_world_xy[1]) / c.world_px_per_deg)

    def step(self, telemetry, frame_width: int, frame_height: int, dt_ctrl: float) -> Tuple[float, float]:
        if telemetry.lock_state in ("locked", "acquiring"):
            err_x_deg = (telemetry.predicted_px[0] - frame_width / 2) / self.camera.px_per_deg_x
            err_y_deg = (telemetry.predicted_px[1] - frame_height / 2) / self.camera.px_per_deg_y
            try:
                out = self.controller.compute(err_x_deg, err_y_deg, dt_ctrl)
            except AlgorithmError:
                raise
            except Exception as exc:
                raise AlgorithmError(f"Controller '{self._ctrl_name}' crashed: {exc}")
            if out is None:
                raise AlgorithmError(f"Controller '{self._ctrl_name}' must return (pan_rate, tilt_rate), got None")
            pan_rate, tilt_rate = check_point(out, self._ctrl_name, "Controller")
        elif telemetry.lock_state == "reacquiring":
            if self._prev_lock_state != "reacquiring":
                self.spiral_search.recenter()
            pan_rate, tilt_rate = self.spiral_search.next_rate(dt_ctrl)
            self.controller.reset()
        else:  # searching
            if self._searching_since_t is None:
                self._searching_since_t = telemetry.timestamp
                self.raster_search.reset()
                if self.cued_search is not None:
                    self.cued_search.reset()
            elapsed = telemetry.timestamp - self._searching_since_t
            if self.cued_search is not None and not self.cued_search.exhausted:
                pan_rate, tilt_rate = self.cued_search.next_rate(self.boresight_deg(),
                                                                 self.cue.at(telemetry.timestamp), dt_ctrl)
            elif elapsed < self.SEARCH_HANDOFF_S and self.cued_search is None:
                pan_rate, tilt_rate = self.initial_search.next_rate(dt_ctrl)
            else:
                pan_rate, tilt_rate = self.raster_search.next_rate(dt_ctrl)
            self.controller.reset()

        if telemetry.lock_state != "searching":
            self._searching_since_t = None
        self._prev_lock_state = telemetry.lock_state
        return pan_rate, tilt_rate
