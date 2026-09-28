"""OBC pointing cue, cued scanning, multi-pass learning, and the learned
detector's torch-free runtime."""
import math
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithms import registry  # noqa: E402
from algorithms.benchmark import build_config, run_single  # noqa: E402
from algorithms.pass_learner import PassLearner  # noqa: E402
from config.scenarios import BY_ID  # noqa: E402
from simulator.obc_model import link_bias  # noqa: E402

ALGOS = {s: {"id": i, "params": {}} for s, i in registry.DEFAULTS.items()}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_link_bias_is_fixed_per_link():
    assert link_bias(3, 1.0) == link_bias(3, 1.0)
    assert link_bias(3, 1.0) != link_bias(4, 1.0)
    assert abs(math.hypot(*link_bias(3, 1.0)) - 1.0) < 1e-9
    assert link_bias(1, [0.5, -0.2]) == (0.5, -0.2)


def test_cue_finds_a_far_beacon_that_the_uncued_search_does_not():
    cued, uncued = [], []
    for seed in (201, 202, 203):
        v = dict(BY_ID["sat_ground"]["values"])
        cued.append(run_single(build_config(v, ALGOS), seed, 15, stop_on_lock=True)["metrics"]["acquisition_time_sec"])
        v["cue/enabled"] = False
        uncued.append(run_single(build_config(v, ALGOS), seed, 15, stop_on_lock=True)["metrics"]["acquisition_time_sec"])
    assert all(t is not None and t < 8 for t in cued), cued
    mean = lambda xs: sum(15 if x is None else x for x in xs) / len(xs)
    assert mean(cued) < mean(uncued), (cued, uncued)


def test_learner_converges_on_the_link_bias():
    class FakeCue:
        sigma_deg = 0.3
        def raw(self, t):
            return (0.0, 0.0)
    L = PassLearner(prior_sigma_deg=2.0)
    import random
    rng = random.Random(0)
    for _ in range(15):
        # the beacon is really at (1.2, -0.8) while the cue says (0, 0):
        # the cue's systematic error is (-1.2, +0.8)
        L.observe(FakeCue(), (1.2 + rng.gauss(0, 0.3), -0.8 + rng.gauss(0, 0.3)), 0.0)
    assert abs(L.bias[0] + 1.2) < 0.25 and abs(L.bias[1] - 0.8) < 0.25
    assert L.P ** 0.5 < 0.2


def test_learning_shrinks_cue_error_over_passes():
    L = PassLearner(prior_sigma_deg=2.0)
    errs = []
    for p in range(6):
        m = run_single(build_config(BY_ID["inter_sat"]["values"], ALGOS), 700 + p, 30, learner=L,
                       stop_on_lock=True)["metrics"]
        errs.append(m["cue_error_deg"])
    assert L.passes >= 4
    assert sum(errs[-3:]) / 3 < sum(errs[:2]) / 2, errs


def test_learned_detector_runs_without_torch():
    code = textwrap.dedent(f"""
        import sys
        sys.modules["torch"] = None          # any torch import now fails
        sys.path.insert(0, {ROOT!r})
        from algorithms import registry
        from algorithms.benchmark import build_config, run_single
        A = {{s: {{"id": i, "params": {{}}}} for s, i in registry.DEFAULTS.items()}}
        A["detector"] = {{"id": "cnn", "params": {{}}}}
        r = run_single(build_config({{}}, A), 5, 3.0)
        assert r["error"] is None, r["error"]
        assert r["metrics"]["acquisition_time_sec"] is not None
        print("ok")
    """)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr[-2000:]
