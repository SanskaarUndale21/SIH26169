"""Plugin system: discovery, parameter handling, bad-plugin reporting,
seeded fairness of the benchmark, and that the default algorithms still
drive the loop to a lock."""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithms import registry  # noqa: E402
from algorithms.api import AlgorithmError  # noqa: E402
from algorithms.benchmark import build_config, run_single, validate_code  # noqa: E402


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "USER_DIR", tmp_path)
    registry._cache["stamp"] = None
    yield tmp_path
    registry._cache["stamp"] = None


def write(dirpath, name, code):
    (dirpath / name).write_text(textwrap.dedent(code), encoding="utf-8")


def test_builtins_listed_with_defaults():
    ids = {a["id"]: a for a in registry.list_algorithms()["algorithms"]}
    for aid in ("dog", "threshold", "imm", "kalman_cv", "hold_last", "pid", "p_only"):
        assert aid in ids
    assert ids["dog"]["default"] and ids["imm"]["default"] and ids["pid"]["default"]


def test_user_plugin_discovered_and_params_typed(plugin_dir):
    write(plugin_dir, "mine.py", """
        from algorithms.api import Tracker
        class Hold(Tracker):
            name = "Hold"
            params = {"gain": {"default": 2, "min": 0, "max": 5}}
            def update(self, dt, m):
                return m
    """)
    listing = registry.list_algorithms()
    a = next(x for x in listing["algorithms"] if x["id"] == "user:mine:Hold")
    assert a["slot"] == "tracker" and a["params"]["gain"]["kind"] == "int"
    cfg = {"algorithms": {"tracker": {"id": "user:mine:Hold", "params": {"gain": "4", "bogus": 1}}}}
    inst = registry.create("tracker", cfg, registry.context_from_config(cfg, 640, 480))
    assert inst.p == {"gain": 4}


def test_broken_plugin_reported_not_raised(plugin_dir):
    write(plugin_dir, "broken.py", "import does_not_exist\n")
    listing = registry.list_algorithms()
    assert "broken.py" in listing["errors"]
    assert "does_not_exist" in listing["errors"]["broken.py"]


def test_missing_algorithm_gives_clear_error():
    with pytest.raises(AlgorithmError, match="not found"):
        registry.get("user:nope:Nothing")


def test_bad_return_value_fails_run_with_message():
    report = validate_code(textwrap.dedent("""
        from algorithms.api import Detector
        class Bad(Detector):
            def detect(self, image):
                return 42
    """))
    assert not report["ok"]
    assert "must return a list" in report["algorithms"][0]["runs"][0]["error"]


def test_same_seed_same_result_different_algorithm_changes_it():
    base = {s: {"id": registry.DEFAULTS[s], "params": {}} for s in ("detector", "tracker", "controller")}
    cfg = build_config({"target/motion": "circular"}, base)
    a = run_single(cfg, 5, 4.0)["metrics"]
    b = run_single(cfg, 5, 4.0)["metrics"]
    assert a["avg_tracking_error_px"] == b["avg_tracking_error_px"]
    assert a["acquisition_time_sec"] is not None

    alt = dict(base, tracker={"id": "hold_last", "params": {}})
    c = run_single(build_config({"target/motion": "circular"}, alt), 5, 4.0)["metrics"]
    assert c["avg_tracking_error_px"] != a["avg_tracking_error_px"]


def test_example_plugins_lock_on():
    for slot, aid in (("detector", "user:example_matched_filter:MatchedFilterDetector"),
                      ("tracker", "user:example_alpha_beta:AlphaBetaTracker"),
                      ("controller", "user:example_pd_deadband:PDDeadbandController")):
        algos = {s: {"id": registry.DEFAULTS[s], "params": {}} for s in ("detector", "tracker", "controller")}
        algos[slot] = {"id": aid, "params": {}}
        res = run_single(build_config({}, algos), 3, 4.0)
        assert res["error"] is None, res["error"]
        assert res["metrics"]["acquisition_time_sec"] is not None


def test_check_kills_infinite_loop_and_exit():
    loop = "from algorithms.api import Detector\nclass A(Detector):\n    def detect(self, im):\n        while True: pass\n"
    r = validate_code(loop, timeout_s=8)
    assert not r["ok"] and "did not finish" in r["error"]
    r = validate_code("import sys\nfrom algorithms.api import Tracker\nclass A(Tracker):\n    def update(self, dt, m): sys.exit(1)\n")
    assert not r["ok"]


def test_controller_returning_none_is_reported():
    r = validate_code("from algorithms.api import Controller\nclass A(Controller):\n    def compute(self, ex, ey, dt): return None\n")
    assert not r["ok"]
    assert "(pan_rate, tilt_rate)" in r["algorithms"][0]["runs"][0]["error"]
