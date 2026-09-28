"""Single source of truth for every tweakable simulation parameter.

Both the desktop GUI (gui/config_panel.py) and the web control UI
(web/dashboard_server.py) build their forms by walking PARAM_SCHEMA, so
the two UIs cannot silently drift out of sync with each other or with
config/default_config.yaml -- every knob that exists is tweakable in
both places, with the same range/default/units, because there is only
one list of knobs.

Each entry:
  path      : tuple of keys/indices into the config dict, e.g.
              ("camera", "fov_deg", 0) means cfg["camera"]["fov_deg"][0]
  label     : human-readable name shown in both UIs
  group     : which section/tab this belongs to
  kind      : "int" | "float" | "bool" | "enum" | "text"
  min/max/step : for int/float (defines the slider + spinbox range)
  options   : for enum, list of (value, display_label) pairs
  unit      : optional unit string shown next to the value
  help      : optional one-line explanation shown as a tooltip
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


@dataclass
class Param:
    path: Tuple
    label: str
    group: str
    kind: str  # int | float | bool | enum | text
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[List[Tuple[Any, str]]] = None
    unit: str = ""
    help: str = ""

    def to_dict(self) -> dict:
        return {
            "path": list(self.path), "label": self.label, "group": self.group,
            "kind": self.kind, "default": self.default, "min": self.min, "max": self.max,
            "step": self.step, "options": self.options, "unit": self.unit, "help": self.help,
        }


def _algo_options(slot: str) -> List[Tuple[Any, str]]:
    """Every available algorithm for a slot, built-ins first, including
    user plugins found in user_algorithms/ at the time of the call."""
    try:
        from algorithms.registry import list_algorithms
        return [(a["id"], a["name"] + (" (yours)" if a["source"] == "user" else ""))
                for a in list_algorithms()["algorithms"] if a["slot"] == slot]
    except Exception:
        return [({"detector": "dog", "tracker": "imm", "controller": "pid"}[slot], "Default")]


PARAM_SCHEMA: List[Param] = [
    # --- Algorithms (which implementation runs each stage) ---
    Param(("algorithms", "detector", "id"), "Detector", "Algorithms", "enum", "dog",
          options=_algo_options("detector"), help="Finds beacon candidates in each frame"),
    Param(("algorithms", "tracker", "id"), "Tracker", "Algorithms", "enum", "imm",
          options=_algo_options("tracker"), help="Estimates the beacon position from detections"),
    Param(("algorithms", "controller", "id"), "Pointing controller", "Algorithms", "enum", "pid",
          options=_algo_options("controller"), help="Turns pointing error into pan/tilt rates"),

    # --- Scene ---
    Param(("screen", "width"), "Screen width", "Scene", "int", 2000, 500, 5000, 50, unit="px"),
    Param(("screen", "height"), "Screen height", "Scene", "int", 2000, 500, 5000, 50, unit="px"),

    # --- Camera ---
    Param(("camera", "resolution", 0), "Camera width", "Camera", "int", 640, 160, 1920, 16, unit="px"),
    Param(("camera", "resolution", 1), "Camera height", "Camera", "int", 480, 120, 1080, 16, unit="px"),
    Param(("camera", "fov_deg", 0), "FOV horizontal", "Camera", "float", 4.0, 0.5, 30.0, 0.1, unit="deg"),
    Param(("camera", "fov_deg", 1), "FOV vertical", "Camera", "float", 3.0, 0.5, 30.0, 0.1, unit="deg"),
    Param(("camera", "update_rate_hz"), "Update rate", "Camera", "int", 30, 10, 120, 1, unit="Hz",
          help="Spec minimum: 30 Hz"),

    # --- Target ---
    Param(("target", "num_targets"), "Number of targets", "Target", "int", 1, 1, 5, 1,
          help="Multiple targets are optional per spec; the tracker follows whichever is nearest its prediction"),
    Param(("target", "shape"), "Shape", "Target", "enum", "square",
          options=[("square", "Square"), ("circle", "Circle")]),
    Param(("target", "size_px", 0), "Width", "Target", "int", 10, 5, 20, 1, unit="px"),
    Param(("target", "size_px", 1), "Height", "Target", "int", 10, 5, 20, 1, unit="px"),
    Param(("target", "initial_location"), "Initial location", "Target", "enum", "random",
          options=[("random", "Random, near the centre"), ("anywhere", "Anywhere on screen (use with a pointing cue)"),
                   ("fixed_center", "Fixed (screen centre)")]),
    Param(("target", "motion"), "Motion type", "Target", "enum", "straight_line",
          options=[("straight_line", "Straight line"), ("circular", "Circular"),
                    ("figure8", "Figure-8"), ("random", "Random walk"), ("spiral", "Spiral"),
                    ("sinusoidal", "Sinusoidal"), ("user_defined", "User-defined path")]),

    # --- Target motion parameters (all four kept live; only the active
    # motion type's set is actually used, per Scene.from_config) ---
    Param(("target", "motion_params", "straight_line", "speed_px_s"), "Speed", "Motion: Straight Line",
          "float", 60.0, 0.0, 300.0, 1.0, unit="px/s"),
    Param(("target", "motion_params", "straight_line", "angle_deg"), "Heading angle", "Motion: Straight Line",
          "float", 30.0, 0.0, 360.0, 1.0, unit="deg"),

    Param(("target", "motion_params", "circular", "radius_px"), "Radius", "Motion: Circular",
          "float", 300.0, 10.0, 900.0, 5.0, unit="px"),
    Param(("target", "motion_params", "circular", "period_s"), "Period", "Motion: Circular",
          "float", 20.0, 1.0, 120.0, 1.0, unit="s"),

    Param(("target", "motion_params", "figure8", "A_px"), "Amplitude A", "Motion: Figure-8",
          "float", 300.0, 10.0, 900.0, 5.0, unit="px"),
    Param(("target", "motion_params", "figure8", "B_px"), "Amplitude B", "Motion: Figure-8",
          "float", 200.0, 10.0, 900.0, 5.0, unit="px"),
    Param(("target", "motion_params", "figure8", "period_s"), "Period", "Motion: Figure-8",
          "float", 24.0, 1.0, 120.0, 1.0, unit="s"),

    Param(("target", "motion_params", "random", "speed_px_s"), "Speed", "Motion: Random Walk",
          "float", 30.0, 0.0, 300.0, 1.0, unit="px/s"),
    Param(("target", "motion_params", "random", "theta_std_deg"), "Heading std. dev.", "Motion: Random Walk",
          "float", 25.0, 0.0, 90.0, 1.0, unit="deg"),

    Param(("target", "motion_params", "spiral", "r0_px"), "Start radius", "Motion: Spiral",
          "float", 20.0, 0.0, 400.0, 5.0, unit="px"),
    Param(("target", "motion_params", "spiral", "k_px_s"), "Radius growth", "Motion: Spiral",
          "float", 15.0, 0.0, 100.0, 1.0, unit="px/s"),
    Param(("target", "motion_params", "spiral", "period_s"), "Period", "Motion: Spiral",
          "float", 6.0, 1.0, 60.0, 0.5, unit="s"),

    Param(("target", "motion_params", "sinusoidal", "speed_px_s"), "Forward speed", "Motion: Sinusoidal",
          "float", 50.0, 0.0, 300.0, 1.0, unit="px/s"),
    Param(("target", "motion_params", "sinusoidal", "angle_deg"), "Heading angle", "Motion: Sinusoidal",
          "float", 0.0, 0.0, 360.0, 1.0, unit="deg"),
    Param(("target", "motion_params", "sinusoidal", "amplitude_px"), "Side amplitude", "Motion: Sinusoidal",
          "float", 120.0, 0.0, 600.0, 5.0, unit="px"),
    Param(("target", "motion_params", "sinusoidal", "period_s"), "Period", "Motion: Sinusoidal",
          "float", 8.0, 1.0, 60.0, 0.5, unit="s"),

    Param(("target", "motion_params", "user_defined", "waypoints"), "Waypoints (dx,dy; ...)",
          "Motion: User-defined", "text", "0,0; 150,0; 150,150; 0,150",
          help="Offsets from the spawn point in world px, visited in order then looped"),
    Param(("target", "motion_params", "user_defined", "speed_px_s"), "Speed", "Motion: User-defined",
          "float", 60.0, 0.0, 300.0, 1.0, unit="px/s"),

    # --- PTZ ---
    Param(("ptz", "max_pan_speed_deg_s"), "Max pan speed", "PTZ", "float", 5.0, 1.0, 30.0, 0.5, unit="deg/s",
          help="Spec range: 5-10 deg/s"),
    Param(("ptz", "max_tilt_speed_deg_s"), "Max tilt speed", "PTZ", "float", 5.0, 1.0, 30.0, 0.5, unit="deg/s"),
    Param(("ptz", "update_interval_hz"), "Update interval", "PTZ", "int", 20, 5, 100, 1, unit="Hz",
          help="Spec minimum: 20 Hz"),

    # --- Noise ---
    Param(("disturbances", "noise", "salt_pepper", "enabled"), "Salt & pepper noise", "Noise", "bool", False),
    Param(("disturbances", "noise", "salt_pepper", "amount"), "Salt & pepper amount", "Noise",
          "float", 0.10, 0.0, 0.5, 0.01, help="Fraction of pixels affected"),
    Param(("disturbances", "noise", "gaussian", "enabled"), "Gaussian noise", "Noise", "bool", False),
    Param(("disturbances", "noise", "gaussian", "sigma"), "Gaussian sigma", "Noise",
          "float", 10.0, 0.0, 30.0, 1.0, unit="px", help="Spec max: 20"),
    Param(("disturbances", "noise", "poisson", "enabled"), "Poisson (shot) noise", "Noise", "bool", False),

    # --- Jitter ---
    Param(("disturbances", "jitter", "enabled"), "Camera jitter", "Jitter", "bool", False),
    Param(("disturbances", "jitter", "max_px"), "Max jitter", "Jitter", "int", 20, 0, 30, 1, unit="px",
          help="Spec max: +-20 px/frame"),
    Param(("disturbances", "jitter", "structured"), "Structured (resonant) jitter", "Jitter", "bool", False,
          help="Reaction-wheel-like narrow-band vibration instead of flat noise"),
    Param(("disturbances", "jitter", "resonance_hz"), "Resonance frequency", "Jitter",
          "float", 8.0, 0.5, 30.0, 0.5, unit="Hz"),

    # --- Atmosphere ---
    Param(("disturbances", "atmosphere", "mode"), "Atmosphere", "Atmosphere", "enum", "clear",
          options=[("clear", "Clear"), ("haze", "Haze"), ("fog", "Fog"),
                    ("rain", "Rain"), ("low_light", "Low light")]),
    Param(("disturbances", "atmosphere", "strength"), "Severity", "Atmosphere", "float", 1.0, 0.0, 2.0, 0.05,
          help="Scales the contrast and brightness reduction: 0 = none, 1 = preset, 2 = double"),

    # --- Turbulence ---
    Param(("disturbances", "turbulence", "enabled"), "Atmospheric turbulence", "Turbulence", "bool", False,
          help="Kolmogorov phase-screen model; costly (~10 FPS alone)"),
    Param(("disturbances", "turbulence", "physical"), "Derive r0 from real physics", "Turbulence", "bool", False,
          help="Hufnagel-Valley Cn2 integration instead of the manual r0 below"),
    Param(("disturbances", "turbulence", "r0"), "Fried parameter r0 (manual)", "Turbulence",
          "float", 0.05, 0.01, 1.0, 0.01, help="Used unless 'derive from physics' is on"),
    Param(("disturbances", "turbulence", "wavelength_nm"), "Wavelength", "Turbulence",
          "float", 1550.0, 400.0, 2000.0, 10.0, unit="nm"),
    Param(("disturbances", "turbulence", "altitude_m"), "Path altitude", "Turbulence",
          "float", 20000.0, 0.0, 40000.0, 500.0, unit="m"),
    Param(("disturbances", "turbulence", "zenith_deg"), "Zenith angle", "Turbulence",
          "float", 0.0, 0.0, 89.0, 1.0, unit="deg"),

    # --- Platform motion ---
    Param(("disturbances", "platform_motion", "enabled"), "Platform motion (uncommanded drift)",
          "Platform Motion", "bool", False),
    Param(("disturbances", "platform_motion", "mode"), "Mode", "Platform Motion", "enum", "linear",
          options=[("linear", "Linear"), ("circular", "Circular"), ("random", "Random"),
                    ("spiral", "Spiral"), ("figure8", "Figure-8")]),
    Param(("disturbances", "platform_motion", "max_px_frame"), "Max drift", "Platform Motion",
          "float", 5.0, 0.0, 20.0, 0.5, unit="px/frame", help="Camera px per frame. Spec max: +-20 px/frame"),

    # --- Link budget ---
    Param(("link_budget", "beam_divergence_urad"), "Beam divergence", "Link Budget",
          "float", 100.0, 1.0, 500.0, 1.0, unit="urad"),
    Param(("link_budget", "fine_stage_capture_range_urad"), "Fine-stage capture range", "Link Budget",
          "float", 500.0, 10.0, 2000.0, 10.0, unit="urad"),
    Param(("link_budget", "wavelength_nm"), "Wavelength", "Link Budget",
          "float", 1550.0, 400.0, 2000.0, 10.0, unit="nm"),
    Param(("link_budget", "range_km"), "Link range", "Link Budget",
          "float", 1000.0, 1.0, 50000.0, 10.0, unit="km"),

    # --- OBC pointing cue (simulator/obc_model.py) ---
    Param(("cue", "enabled"), "Use the on-board computer's pointing cue", "Pointing Cue", "bool", False,
          help="The satellite computer predicts where the other terminal is; the camera slews there, then scans"),
    Param(("cue", "sigma_deg"), "Cue uncertainty (1 sigma)", "Pointing Cue", "float", 0.5, 0.0, 5.0, 0.05,
          unit="deg", help="Random error of each pass. About 0.2 for satellite-to-ground, 1.5 for inter-satellite"),
    Param(("cue", "bias_deg"), "Systematic cue error", "Pointing Cue", "float", 0.0, 0.0, 5.0, 0.05, unit="deg",
          help="Same on every pass of a link (ephemeris or mounting error). Multi-pass learning can remove it"),
    Param(("cue", "link_seed"), "Link id", "Pointing Cue", "int", 1, 1, 999, 1,
          help="Which link: sets the direction of the systematic error, shared by all its passes"),

    # --- Scenario preset ---
    Param(("scenario_preset",), "Scenario preset", "Scenario Preset", "enum", "none",
          options=[("none", "None (use generic Target settings)"),
                    ("leo_leo_crosslink", "LEO-LEO Crosslink"),
                    ("leo_ground_downlink", "LEO-Ground Downlink"),
                    ("geo_ground", "GEO-Ground")],
          help="Overrides Target motion + Link Budget with orbital-mechanics-derived values"),

    # --- Detector ---
    Param(("detector", "dog_sigma1"), "DoG sigma 1 (inner)", "Detector", "float", 1.0, 0.1, 5.0, 0.1),
    Param(("detector", "dog_sigma2"), "DoG sigma 2 (outer)", "Detector", "float", 3.0, 0.5, 10.0, 0.1),
    Param(("detector", "threshold_k"), "Threshold k", "Detector", "float", 4.0, 1.0, 10.0, 0.1,
          help="Detection threshold = k * local noise sigma"),

    # --- IMM tracker ---
    Param(("tracker", "process_noise_cv"), "Process noise: CV model", "IMM Tracker",
          "float", 4.0, 0.1, 100.0, 0.5),
    Param(("tracker", "process_noise_ct"), "Process noise: CT model", "IMM Tracker",
          "float", 4.0, 0.1, 100.0, 0.5),
    Param(("tracker", "process_noise_rw"), "Process noise: Random-walk model", "IMM Tracker",
          "float", 50.0, 0.1, 500.0, 1.0),
    Param(("tracker", "measurement_noise"), "Measurement noise", "IMM Tracker",
          "float", 1.0, 0.1, 50.0, 0.1),
    Param(("tracker", "acquiring_confirm_frames"), "Confirm frames (acquiring->locked)", "IMM Tracker",
          "int", 6, 1, 30, 1, unit="frames"),
    Param(("tracker", "reacquire_timeout_frames"), "Re-acquire timeout", "IMM Tracker",
          "int", 30, 1, 200, 1, unit="frames"),

    # --- PID control ---
    Param(("control", "pid", "pan", "kp"), "Pan Kp", "PID Control", "float", 2.5, 0.0, 20.0, 0.05),
    Param(("control", "pid", "pan", "ki"), "Pan Ki", "PID Control", "float", 0.15, 0.0, 5.0, 0.01),
    Param(("control", "pid", "pan", "kd"), "Pan Kd", "PID Control", "float", 0.35, 0.0, 5.0, 0.01),
    Param(("control", "pid", "tilt", "kp"), "Tilt Kp", "PID Control", "float", 2.5, 0.0, 20.0, 0.05),
    Param(("control", "pid", "tilt", "ki"), "Tilt Ki", "PID Control", "float", 0.15, 0.0, 5.0, 0.01),
    Param(("control", "pid", "tilt", "kd"), "Tilt Kd", "PID Control", "float", 0.35, 0.0, 5.0, 0.01),
]

GROUP_ORDER = [
    "Algorithms", "Scene", "Camera", "Target",
    "Motion: Straight Line", "Motion: Circular", "Motion: Figure-8", "Motion: Random Walk",
    "Motion: Spiral", "Motion: Sinusoidal", "Motion: User-defined",
    "PTZ", "Noise", "Jitter", "Atmosphere", "Turbulence", "Platform Motion",
    "Link Budget", "Pointing Cue", "Scenario Preset", "Detector", "IMM Tracker", "PID Control",
]


def get_path(cfg: dict, path: Tuple):
    node = cfg
    for key in path:
        node = node[key]
    return node


def set_path(cfg: dict, path: Tuple, value):
    node = cfg
    for key in path[:-1]:
        # create missing dict levels (e.g. a motion type an older YAML
        # never listed) instead of raising KeyError
        if isinstance(node, dict) and key not in node:
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


def schema_as_json() -> dict:
    # refresh algorithm choices so newly added plugins show up without a restart
    for p in PARAM_SCHEMA:
        if p.path[0] == "algorithms":
            p.options = _algo_options(p.path[1])
    return {"groups": GROUP_ORDER, "params": [p.to_dict() for p in PARAM_SCHEMA]}


def resolve_ui_values(base_cfg: dict, ui_values: dict) -> dict:
    """Applies a flat {path_string: value} map (as produced by either UI)
    onto a deep copy of base_cfg, resolving the schema's UI-only
    conveniences (initial_location's "fixed_center" token, scenario_preset's
    "none" -> actual null) into the real config shape Scene.from_config /
    scenario_presets.apply_preset expect. path_string is "/".join(str(k)
    for k in path).
    """
    cfg = copy.deepcopy(base_cfg)
    for p in PARAM_SCHEMA:
        key = "/".join(str(k) for k in p.path)
        if key not in ui_values:
            continue
        value = ui_values[key]
        if p.kind == "int":
            value = int(round(float(value)))
        elif p.kind == "float":
            value = float(value)
        elif p.kind == "bool":
            value = bool(value)
        elif p.kind == "text":
            value = str(value)
        set_path(cfg, p.path, value)

    # Per-algorithm parameters are not in the static schema (they depend on
    # which plugin is chosen): "algorithms/<slot>/params/<name>" keys are
    # copied through as-is, and the algorithm itself validates their types.
    for key, value in ui_values.items():
        parts = key.split("/")
        if len(parts) == 4 and parts[0] == "algorithms" and parts[2] == "params":
            set_path(cfg, tuple(parts), value)

    # initial_location UI convenience -> real config value
    if get_path(cfg, ("target", "initial_location")) == "fixed_center":
        w = get_path(cfg, ("screen", "width"))
        h = get_path(cfg, ("screen", "height"))
        set_path(cfg, ("target", "initial_location"), [w / 2, h / 2])

    # scenario_preset UI convenience -> real null when "none"
    if get_path(cfg, ("scenario_preset",)) == "none":
        set_path(cfg, ("scenario_preset",), None)

    return cfg


def apply_scenario_preset_if_set(cfg: dict) -> dict:
    """If cfg['scenario_preset'] names a real preset, overlays it (see
    simulator/scenario_presets.py) -- this is what actually derives
    target motion + link budget from orbital mechanics. Call this after
    resolve_ui_values(); kept separate so config resolution never
    silently imports simulator/ unless a preset is actually requested."""
    preset_name = cfg.get("scenario_preset")
    if not preset_name:
        return cfg
    from simulator.scenario_presets import apply_preset
    return apply_preset(preset_name, cfg)


def flatten_config_to_ui_values(cfg: dict) -> dict:
    """Inverse-ish of resolve_ui_values: reads current values out of a
    config dict into the flat {path_string: value} map the UI widgets
    are initialized from. Used to populate the web form and the desktop
    panel from the same starting config."""
    values = {}
    for p in PARAM_SCHEMA:
        key = "/".join(str(k) for k in p.path)
        try:
            values[key] = get_path(cfg, p.path)
        except (KeyError, IndexError, TypeError):
            values[key] = p.default
    return values
