"""Finds every available algorithm: the built-ins plus each Detector /
Tracker / Controller subclass defined in a .py file under
user_algorithms/. Files are re-imported whenever they change on disk, so
an edited plugin is picked up on the next run without restarting.

Algorithm ids:  built-ins by short name ("dog", "imm", "pid", ...),
                plugins as "user:<file stem>:<ClassName>".
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Dict, List, Optional

from algorithms.api import SLOTS, AlgoContext, AlgorithmError, normalize_params
from algorithms.builtin import BUILTINS, DEFAULTS

REPO_ROOT = Path(__file__).resolve().parent.parent
USER_DIR = Path(os.environ.get("FSOC_USER_ALGORITHMS", REPO_ROOT / "user_algorithms"))

_lock = threading.Lock()
_cache: dict = {"stamp": None, "classes": {}, "errors": {}, "files": {}}


def _dir_stamp():
    if not USER_DIR.exists():
        return ()
    return tuple(sorted((p.name, p.stat().st_mtime_ns, p.stat().st_size)
                        for p in USER_DIR.glob("*.py") if not p.name.startswith("_")))


def load_file(path: Path) -> tuple[dict, Optional[str]]:
    """Imports one plugin file in isolation. Returns ({id: cls}, error_text)."""
    stem = path.stem
    mod_name = f"_fsoc_user_{stem}_{abs(hash((str(path), path.stat().st_mtime_ns)))}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(mod_name, None)
        return {}, traceback.format_exc(limit=6)
    found = {}
    for _, cls in inspect.getmembers(mod, inspect.isclass):
        if cls.__module__ != mod_name:
            continue
        for base in SLOTS.values():
            if issubclass(cls, base) and cls is not base:
                found[f"user:{stem}:{cls.__name__}"] = cls
    if not found:
        return {}, ("No algorithm found. Define a class that subclasses Detector, Tracker "
                    "or Controller from algorithms.api.")
    return found, None


def _refresh():
    stamp = _dir_stamp()
    if stamp == _cache["stamp"]:
        return
    classes, errors, files = {}, {}, {}
    for name, _, _ in stamp:
        path = USER_DIR / name
        found, err = load_file(path)
        if err:
            errors[name] = err
        for aid, cls in found.items():
            classes[aid] = cls
            files[aid] = name
    _cache.update(stamp=stamp, classes=classes, errors=errors, files=files)


def _all() -> Dict[str, type]:
    with _lock:
        _refresh()
        out = {}
        for slot, items in BUILTINS.items():
            out.update(items)
        out.update(_cache["classes"])
        return out


def slot_of(cls) -> str:
    for slot, base in SLOTS.items():
        if issubclass(cls, base):
            return slot
    return ""


def get(algo_id: str):
    cls = _all().get(algo_id)
    if cls is None:
        raise AlgorithmError(f"Algorithm '{algo_id}' not found. It may have been renamed or deleted, "
                             f"or its file failed to load (see the Algorithms page).")
    return cls


def list_algorithms() -> dict:
    items = []
    for aid, cls in _all().items():
        slot = slot_of(cls)
        doc = inspect.getdoc(cls) or ""
        items.append({
            "id": aid,
            "slot": slot,
            "name": cls.display_name(),
            "description": cls.description or (doc.splitlines()[0] if doc else ""),
            "params": normalize_params(cls.params),
            "source": "user" if aid.startswith("user:") else "builtin",
            "file": _cache["files"].get(aid),
            "default": DEFAULTS.get(slot) == aid,
        })
    order = {"builtin": 0, "user": 1}
    items.sort(key=lambda a: (list(SLOTS).index(a["slot"]), order[a["source"]], not a["default"], a["name"]))
    return {"algorithms": items, "errors": dict(_cache["errors"]), "user_dir": str(USER_DIR)}


def selection(config: dict, slot: str) -> tuple[str, dict]:
    sel = (config.get("algorithms") or {}).get(slot) or {}
    return sel.get("id") or DEFAULTS[slot], sel.get("params") or {}


def create(slot: str, config: dict, ctx: AlgoContext):
    algo_id, params = selection(config, slot)
    # "_cls" lets the validator run a not-yet-saved class directly
    cls = ((config.get("algorithms") or {}).get(slot) or {}).get("_cls") or get(algo_id)
    if slot_of(cls) != slot:
        raise AlgorithmError(f"'{algo_id}' is a {slot_of(cls)}, not a {slot}")
    try:
        inst = cls(ctx, **params)
    except AlgorithmError:
        raise
    except Exception as exc:
        raise AlgorithmError(f"{cls.display_name()} failed to start: {exc}\n{traceback.format_exc(limit=4)}")
    inst.algo_id = algo_id
    return inst


def context_from_config(config: dict, frame_width: int, frame_height: int, fov_deg=None) -> AlgoContext:
    ptz = config.get("ptz", {})
    size = config.get("target", {}).get("size_px", [10, 10])
    return AlgoContext(
        frame_width=frame_width, frame_height=frame_height,
        fov_deg=tuple(fov_deg) if fov_deg else None,
        target_size_px=(int(size[0]), int(size[1] if len(size) > 1 else size[0])),
        max_pan_deg_s=ptz.get("max_pan_speed_deg_s", 5.0),
        max_tilt_deg_s=ptz.get("max_tilt_speed_deg_s", 5.0),
        frame_rate_hz=config.get("camera", {}).get("update_rate_hz", 30),
        config=config,
    )


def describe_selection(config: dict) -> dict:
    """{slot: {"id", "name", "params"}} for logs and reports."""
    out = {}
    for slot in SLOTS:
        aid, params = selection(config, slot)
        try:
            name = get(aid).display_name()
        except AlgorithmError:
            name = aid
        out[slot] = {"id": aid, "name": name, "params": params}
    return out
