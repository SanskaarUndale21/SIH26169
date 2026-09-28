"""Changes made after the ISRO mentors' reply and the stress audit."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithms import registry  # noqa: E402
from algorithms.benchmark import build_config, run_single  # noqa: E402
from simulator.disturbances import apply_atmosphere  # noqa: E402
from simulator.link_budget import LinkBudgetConfig  # noqa: E402

DEFAULT_ALGOS = {s: {"id": i, "params": {}} for s, i in registry.DEFAULTS.items()}


def test_beam_divergence_defaults_to_mentor_value():
    assert LinkBudgetConfig.from_config({}).beam_divergence_urad == 100.0
    assert build_config({}, DEFAULT_ALGOS)["link_budget"]["beam_divergence_urad"] == 100.0


def test_max_severity_never_erases_the_beacon():
    img = np.full((4, 4), 20, np.uint8)
    img[1, 1] = 255
    for mode in ("low_light", "fog", "haze", "rain"):
        for strength in (1.0, 1.5, 2.0):
            out = apply_atmosphere(img, mode, strength=strength)
            assert out[1, 1] >= 40, (mode, strength)
    # severity 1 is still exactly the preset
    assert apply_atmosphere(img, "low_light", strength=1.0)[1, 1] == 105


def test_centroid_accuracy_is_sub_pixel_on_default_scenario():
    m = run_single(build_config({}, DEFAULT_ALGOS), 4, 4.0)["metrics"]
    assert m["avg_centroid_error_px"] is not None
    assert m["avg_centroid_error_px"] < 1.0


def test_low_light_noise_keeps_processing_above_20_fps():
    cfg = build_config({"disturbances/atmosphere/mode": "low_light", "target/motion": "random",
                        "disturbances/noise/gaussian/enabled": True,
                        "disturbances/noise/gaussian/sigma": 10}, DEFAULT_ALGOS)
    m = run_single(cfg, 11, 4.0)["metrics"]
    assert m["acquisition_time_sec"] is not None
    assert m["processing_fps"] >= 20
