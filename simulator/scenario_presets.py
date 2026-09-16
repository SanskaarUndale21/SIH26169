"""Named, physically-parametrized scenario presets: LEO-LEO crosslink,
LEO-ground downlink, GEO-ground. Each overlays the base config with
motion/link-budget parameters *derived* from simulator/orbital.py's real
orbital-mechanics formulas (altitude, orbital velocity, range) rather than
picked to look reasonable on screen -- so running "LEO-LEO crosslink"
actually means something, and a technical reviewer can trace every number
back to a formula.
"""
from __future__ import annotations

import copy
import math

from simulator.orbital import (geo_ground_residual_rate_deg_s,
                                leo_ground_peak_angular_rate_deg_s,
                                leo_leo_crosslink_angular_rate_deg_s)


def _apply_link_budget(cfg: dict, wavelength_nm: float, range_km: float,
                        beam_divergence_urad: float) -> None:
    cfg["link_budget"] = {
        "wavelength_nm": wavelength_nm,
        "range_km": range_km,
        "beam_divergence_urad": beam_divergence_urad,
        "fine_stage_capture_range_urad": cfg.get("link_budget", {}).get("fine_stage_capture_range_urad", 500.0),
    }


def leo_leo_crosslink(base_cfg: dict, altitude_km: float = 500.0, range_km: float = 500.0,
                       relative_inclination_deg: float = 30.0) -> dict:
    """Two LEO satellites in different orbital planes, crosslinked at
    range_km. Relative LOS motion is fast and roughly linear over the
    timescale of a single tracking pass -- modeled as straight-line
    motion whose speed is the actual LOS angular rate converted to world
    pixels."""
    cfg = copy.deepcopy(base_cfg)
    deg_s = leo_leo_crosslink_angular_rate_deg_s(altitude_km, range_km, relative_inclination_deg)
    world_px_per_deg = 50.0  # matches simulator.camera_model.CameraModel's default
    speed_px_s = deg_s * world_px_per_deg
    cfg["target"] = dict(cfg["target"])
    cfg["target"]["motion"] = "straight_line"
    cfg["target"]["motion_params"] = dict(cfg["target"].get("motion_params", {}))
    cfg["target"]["motion_params"]["straight_line"] = {"speed_px_s": speed_px_s, "angle_deg": 25}
    _apply_link_budget(cfg, wavelength_nm=1550.0, range_km=range_km, beam_divergence_urad=20.0)
    cfg["_scenario_name"] = "leo_leo_crosslink"
    cfg["_scenario_derivation"] = (
        f"altitude={altitude_km}km, range={range_km}km, rel_inclination={relative_inclination_deg}deg "
        f"-> LOS angular rate {deg_s:.4f} deg/s -> straight_line speed {speed_px_s:.1f} px/s "
        f"(world_px_per_deg={world_px_per_deg})"
    )
    return cfg


def leo_ground_downlink(base_cfg: dict, altitude_km: float = 500.0, pass_segment_s: float = 20.0) -> dict:
    """Ground station tracking a LEO satellite through an overhead pass
    segment. Modeled as circular motion whose peak tangential speed
    matches the real zenith-crossing peak angular rate for this
    altitude, with the radius chosen so a `pass_segment_s`-long arc fits
    on screen (a full LEO pass horizon-to-horizon lasts several minutes;
    this models the fast, near-zenith segment where tracking is hardest).
    Default pass_segment_s=20s keeps the resulting orbit radius small
    enough to stay within the default search's reliable acquisition
    range (see scene.py/README's documented spawn-radius discussion) --
    a longer, more representative pass segment can still be requested
    explicitly, it just needs a correspondingly wider search budget."""
    cfg = copy.deepcopy(base_cfg)
    deg_s = leo_ground_peak_angular_rate_deg_s(altitude_km)
    world_px_per_deg = 50.0
    peak_speed_px_s = deg_s * world_px_per_deg
    radius_px = peak_speed_px_s * pass_segment_s / (2 * math.pi)
    cfg["target"] = dict(cfg["target"])
    cfg["target"]["motion"] = "circular"
    cfg["target"]["motion_params"] = dict(cfg["target"].get("motion_params", {}))
    cfg["target"]["motion_params"]["circular"] = {"radius_px": radius_px, "period_s": pass_segment_s}
    _apply_link_budget(cfg, wavelength_nm=1550.0, range_km=altitude_km, beam_divergence_urad=20.0)
    cfg["_scenario_name"] = "leo_ground_downlink"
    cfg["_scenario_derivation"] = (
        f"altitude={altitude_km}km -> peak angular rate {deg_s:.4f} deg/s -> "
        f"circular radius {radius_px:.0f}px, period {pass_segment_s}s (world_px_per_deg={world_px_per_deg})"
    )
    return cfg


def geo_ground(base_cfg: dict, station_keeping_box_deg: float = 0.05) -> dict:
    """Ground station tracking a GEO satellite: nominally stationary,
    only slow station-keeping drift -- the tracking challenge here is
    almost entirely rejecting disturbance (jitter/atmosphere), not
    chasing motion, which is realistic for GEO."""
    cfg = copy.deepcopy(base_cfg)
    deg_s = geo_ground_residual_rate_deg_s(station_keeping_box_deg)
    world_px_per_deg = 50.0
    speed_px_s = deg_s * world_px_per_deg
    cfg["target"] = dict(cfg["target"])
    cfg["target"]["motion"] = "straight_line"
    cfg["target"]["motion_params"] = dict(cfg["target"].get("motion_params", {}))
    cfg["target"]["motion_params"]["straight_line"] = {"speed_px_s": max(speed_px_s, 0.01), "angle_deg": 0}
    _apply_link_budget(cfg, wavelength_nm=1550.0, range_km=35786.0, beam_divergence_urad=20.0)
    cfg["_scenario_name"] = "geo_ground"
    cfg["_scenario_derivation"] = (
        f"station-keeping box={station_keeping_box_deg}deg -> residual rate {deg_s:.2e} deg/s -> "
        f"speed {speed_px_s:.4f} px/s (effectively stationary; GEO range 35786km sets link budget)"
    )
    return cfg


PRESETS = {
    "leo_leo_crosslink": leo_leo_crosslink,
    "leo_ground_downlink": leo_ground_downlink,
    "geo_ground": geo_ground,
}


def apply_preset(name: str, base_cfg: dict, **kwargs) -> dict:
    if name not in PRESETS:
        raise ValueError(f"unknown scenario preset: {name} (available: {list(PRESETS)})")
    return PRESETS[name](base_cfg, **kwargs)


def resolve_scenario_preset(cfg: dict) -> dict:
    """If cfg["scenario_preset"] names one of PRESETS, returns the
    overlaid config; otherwise returns cfg unchanged. Called once at
    config-load time (main.py, gui/main_window.py's start_run) rather
    than inside Scene.from_config, so the resolved target motion/
    link-budget values are visible in the config actually passed
    around."""
    name = cfg.get("scenario_preset")
    if not name:
        return cfg
    return apply_preset(name, cfg)
