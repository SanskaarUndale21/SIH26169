"""Head-to-head algorithm benchmark and plugin validation.

run_single() runs one full closed-loop simulation headlessly (as fast as
the machine allows) with a fixed seed, so every algorithm variant sees
exactly the same beacon path, noise and disturbances. BenchJob runs a
scenarios x variants x seeds matrix in a background thread and scores
every run against the problem statement's performance targets.
validate_code() is what the Algorithms page's "Check" button runs.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import statistics
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
import yaml

from algorithms import registry
from algorithms.api import SLOTS, AlgorithmError
from config.param_schema import apply_scenario_preset_if_set, resolve_ui_values
from config.scenarios import BY_ID as SCENARIOS
from control.run_loop import TrackingRunner
from perception.frame_source import SimulatorFrameSource, VideoFileFrameSource
from simulator.camera_model import CameraModel, PTZActuator
from simulator.disturbances import DisturbanceConfig
from simulator.renderer import SimulatorEngine
from simulator.scene import Scene

REPO_ROOT = Path(__file__).resolve().parent.parent

# Problem statement performance targets
TARGETS = {
    "acquisition_time_sec": ("<=", 2.0),
    "avg_tracking_error_px": ("<=", 10.0),
    "target_loss_pct": ("<", 5.0),
    "worst_reacquisition_sec": ("<=", 1.0),
    "processing_fps": (">=", 20.0),
}


def load_base_config() -> dict:
    with open(REPO_ROOT / "config" / "default_config.yaml") as f:
        return yaml.safe_load(f)


def build_config(scenario_values: dict, algorithms: dict, base_ui_values: Optional[dict] = None) -> dict:
    values = dict(base_ui_values or {})
    values.update(scenario_values or {})
    cfg = resolve_ui_values(load_base_config(), values)
    cfg = apply_scenario_preset_if_set(cfg)
    cfg["algorithms"] = copy.copy(algorithms)
    return cfg


def derived(m: dict) -> dict:
    """Adds the spec-facing numbers the raw log doesn't carry directly."""
    out = dict(m)
    acquired = m.get("acquisition_time_sec") is not None
    out["target_loss_pct"] = round((1 - m.get("lock_retention_rate", 0.0)) * 100, 3) if acquired else None
    times = m.get("re_acquisition_times_sec") or []
    out["worst_reacquisition_sec"] = max(times) if times else (0.0 if acquired else None)
    # Algorithm-only throughput: frames per second the detection + tracking
    # + control stages could sustain, excluding the simulator's own cost of
    # rendering the scene and its noise (which the loop "fps" includes).
    proc = m.get("processing_time_per_frame_ms") or 0.0
    out["processing_fps"] = round(1000.0 / proc, 2) if proc > 0 else None
    return out


def judge(m: dict, has_truth: bool = True) -> dict:
    verdicts = {}
    for key, (op, target) in TARGETS.items():
        v = m.get(key)
        if key == "avg_tracking_error_px" and not has_truth:
            verdicts[key] = None
            continue
        if v is None:
            verdicts[key] = False
            continue
        verdicts[key] = v <= target if op == "<=" else v < target if op == "<" else v >= target
    return verdicts


def run_single(cfg: dict, seed: int, duration_s: float, video_path: Optional[str] = None) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    camera = ptz = None
    try:
        if video_path:
            source = VideoFileFrameSource(video_path)
            fps = source.get_fps()
        else:
            scene = Scene.from_config(cfg)
            cam_cfg = cfg["camera"]
            camera = CameraModel(width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                                 fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                                 world_x=cfg["screen"]["width"] / 2, world_y=cfg["screen"]["height"] / 2)
            ptz = PTZActuator(camera, cfg["ptz"]["max_pan_speed_deg_s"], cfg["ptz"]["max_tilt_speed_deg_s"])
            engine = SimulatorEngine(scene, camera, DisturbanceConfig.from_config(cfg), seed=seed)
            fps = cam_cfg["update_rate_hz"]
            source = SimulatorFrameSource(engine, fps=fps)
        gt = (lambda: source.last_ground_truth) if camera is not None else None
        runner = TrackingRunner(cfg, source, camera=camera, ptz=ptz, ground_truth_fn=gt)
        result = runner.run(max_frames=int(duration_s * fps))
        m = derived(result.metrics)
        log = result.telemetry_log
        m["detection_rate"] = round(sum(t.detected for t in log) / len(log), 4) if log else 0.0
        return {"metrics": m, "verdicts": judge(m, has_truth=camera is not None), "error": None}
    except AlgorithmError as exc:
        return {"metrics": None, "verdicts": None, "error": str(exc)}
    except Exception as exc:
        return {"metrics": None, "verdicts": None, "error": f"{exc}\n{traceback.format_exc(limit=5)}"}
    finally:
        if video_path and "source" in locals():
            try:
                source.release()
            except Exception:
                pass


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def summarize(cells: List[dict]) -> dict:
    ok = [c for c in cells if c["error"] is None]
    passes = [c for c in ok if all(v is not False for v in c["verdicts"].values())]
    ms = [c["metrics"] for c in ok]
    worst = [m["worst_reacquisition_sec"] for m in ms if m["worst_reacquisition_sec"] is not None]
    return {
        "runs": len(cells),
        "errors": len(cells) - len(ok),
        "passes": len(passes),
        "pass_rate": round(len(passes) / len(cells), 4) if cells else 0.0,
        "acquired": sum(1 for m in ms if m["acquisition_time_sec"] is not None),
        "acquisition_time_sec": _mean(m["acquisition_time_sec"] for m in ms),
        "avg_tracking_error_px": _mean(m["avg_tracking_error_px"] for m in ms),
        "max_tracking_error_px": max((m["max_tracking_error_px"] for m in ms if m["max_tracking_error_px"] is not None), default=None),
        "target_loss_pct": _mean(m["target_loss_pct"] for m in ms),
        "worst_reacquisition_sec": max(worst) if worst else None,
        "fps": _mean(m["fps"] for m in ms),
        "processing_fps": _mean(m["processing_fps"] for m in ms),
        "processing_time_per_frame_ms": _mean(m["processing_time_per_frame_ms"] for m in ms),
        "avg_centroid_error_px": _mean(m.get("avg_centroid_error_px") for m in ms),
        "detection_rate": _mean(m["detection_rate"] for m in ms),
    }


class BenchJob:
    """One benchmark matrix running in a background thread."""

    def __init__(self, scenarios: List[str], variants: List[dict], seeds: int, duration_s: float,
                 out_dir: str, base_ui_values: Optional[dict] = None, video_path: Optional[str] = None):
        self.id = time.strftime("bench_%Y%m%d_%H%M%S")
        self.scenarios = [s for s in scenarios if s in SCENARIOS or s == "video"]
        self.variants = variants
        self.seeds = max(1, int(seeds))
        self.duration_s = float(duration_s)
        self.base_ui_values = base_ui_values or {}
        self.video_path = video_path
        self.out_dir = out_dir
        self.cells: List[dict] = []
        self.total = len(self.scenarios) * len(variants) * self.seeds
        self.cancelled = False
        self.done = False
        self.error: Optional[str] = None
        self.started = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def cancel(self):
        self.cancelled = True

    def _run(self):
        try:
            for sid in self.scenarios:
                for seed in range(self.seeds):
                    for vi, var in enumerate(self.variants):
                        if self.cancelled:
                            return
                        algos = {slot: {"id": var["algorithms"][slot]["id"],
                                        "params": var["algorithms"][slot].get("params", {})}
                                 for slot in SLOTS}
                        if sid == "video":
                            cfg = build_config({}, algos, self.base_ui_values)
                            res = run_single(cfg, 1000 + seed, self.duration_s, video_path=self.video_path)
                        else:
                            cfg = build_config(SCENARIOS[sid]["values"], algos, self.base_ui_values)
                            res = run_single(cfg, 1000 + seed, self.duration_s)
                        self.cells.append({"scenario": sid, "variant": vi, "seed": 1000 + seed, **res})
        except Exception as exc:
            self.error = f"{exc}\n{traceback.format_exc(limit=5)}"
        finally:
            self.done = True
            try:
                self.save()
            except Exception as exc:
                self.error = self.error or f"could not save results: {exc}"

    def result(self) -> dict:
        per_variant = [summarize([c for c in self.cells if c["variant"] == i]) for i in range(len(self.variants))]
        per_cell = {}
        for sid in self.scenarios:
            for i in range(len(self.variants)):
                cs = [c for c in self.cells if c["variant"] == i and c["scenario"] == sid]
                if cs:
                    per_cell[f"{sid}|{i}"] = summarize(cs)
        return {
            "id": self.id,
            "created": self.started,
            "done": self.done,
            "cancelled": self.cancelled,
            "error": self.error,
            "progress": len(self.cells),
            "total": self.total,
            "duration_s": self.duration_s,
            "seeds": self.seeds,
            "scenarios": [{"id": s, "title": "Your video" if s == "video" else SCENARIOS[s]["title"]} for s in self.scenarios],
            "variants": [{"name": v.get("name") or f"Variant {i + 1}",
                          "algorithms": {slot: {**v["algorithms"][slot],
                                                "name": _algo_name(v["algorithms"][slot]["id"])} for slot in SLOTS}}
                         for i, v in enumerate(self.variants)],
            "summary": per_variant,
            "matrix": per_cell,
            "cells": [{k: c[k] for k in ("scenario", "variant", "seed", "error")} | {"metrics": c["metrics"], "verdicts": c["verdicts"]}
                      for c in self.cells],
            "targets": {k: list(v) for k, v in TARGETS.items()},
        }

    def save(self):
        os.makedirs(self.out_dir, exist_ok=True)
        with open(os.path.join(self.out_dir, f"{self.id}.json"), "w") as f:
            json.dump(self.result(), f, indent=1, default=str)


def _algo_name(aid: str) -> str:
    try:
        return registry.get(aid).display_name()
    except AlgorithmError:
        return aid


# --------------------------------------------------------------- validation

def _validate_in_process(code: str) -> dict:
    """The actual check; runs inside a child process (see validate_code)."""
    tmpdir = tempfile.mkdtemp(prefix="fsoc_check_")
    path = Path(tmpdir) / "candidate.py"
    path.write_text(code, encoding="utf-8")
    found, err = registry.load_file(path)
    if err:
        return {"ok": False, "error": err, "algorithms": []}
    report = {"ok": True, "error": None, "algorithms": []}
    for aid, cls in found.items():
        slot = registry.slot_of(cls)
        entry = {"class": cls.__name__, "name": cls.display_name(), "slot": slot, "runs": []}
        for sid in ("default", "noise"):
            algos = {s: {"id": registry.DEFAULTS[s], "params": {}} for s in SLOTS}
            algos[slot] = {"id": aid, "params": {}, "_cls": cls}
            res = run_single(build_config(SCENARIOS[sid]["values"], algos), 7, 6.0)
            entry["runs"].append({"scenario": SCENARIOS[sid]["title"], **res})
            if res["error"]:
                report["ok"] = False
                break
        report["algorithms"].append(entry)
    return report


def _validate_worker(code, conn):
    try:
        conn.send(_validate_in_process(code))
    except Exception as exc:
        conn.send({"ok": False, "error": f"{exc}\n{traceback.format_exc(limit=5)}", "algorithms": []})
    finally:
        conn.close()


def validate_code(code: str, timeout_s: float = 90.0) -> dict:
    """Loads unsaved plugin code and runs each algorithm it defines through
    two short closed-loop scenarios (spec defaults and heavy noise), with the
    other two stages at their defaults. Runs in a separate process that is
    killed on timeout, so an infinite loop or crash in the user's code can't
    leave a stuck thread burning CPU inside the server."""
    try:
        compile(code, "your file", "exec")
    except SyntaxError as exc:
        return {"ok": False, "error": f"Syntax error on line {exc.lineno}: {exc.msg}", "algorithms": []}
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_validate_worker, args=(code, child), daemon=True)
    proc.start()
    child.close()
    try:
        if parent.poll(timeout_s):
            return parent.recv()
        return {"ok": False, "algorithms": [],
                "error": f"Check did not finish within {timeout_s:.0f} s. Look for an infinite loop or very slow code."}
    except EOFError:
        return {"ok": False, "algorithms": [],
                "error": "Your code stopped the checker process (for example by calling exit() or crashing Python)."}
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(5)
        parent.close()