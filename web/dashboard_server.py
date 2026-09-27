"""Web console for the FSOC coarse-alignment tracker.

Pages (each its own screen, served from web/ui/):
    /            Overview: what the system does, latest results vs. spec
    /setup       New run: step-by-step scenario builder with live previews
    /live        Live: camera feed, lock state, whole-screen map, 3D gimbal
    /runs        Runs: every recorded run with pass/fail against the spec
    /runs/{name} Report: one run's scorecard, charts, replay, downloads
    /spec        Spec check: every problem-statement requirement and status

The live engine (web/live_engine.py) runs the same TrackingRunner the
desktop GUI drives, configured through the same config/param_schema.py,
so both front-ends produce identical runs for identical settings.

Run with:
    python web/dashboard_server.py
then open http://127.0.0.1:8420/
"""
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
# Deployment settings (all optional; defaults are for local use):
#   FSOC_DATA_DIR   where run logs, benchmarks and uploads are kept (point at a persistent disk)
#   FSOC_PUBLIC=1   public mode: writing, uploading, checking and deleting algorithm
#                   plugins is disabled, because a plugin is arbitrary Python run on the server
#   FSOC_PASSWORD   if set, every page and API asks for this password (any user name)
#   HOST / PORT     where to listen (default 127.0.0.1:8420)
DATA_DIR = Path(os.environ.get("FSOC_DATA_DIR", REPO_ROOT))
PUBLIC_MODE = os.environ.get("FSOC_PUBLIC", "").lower() in ("1", "true", "yes")
PASSWORD = os.environ.get("FSOC_PASSWORD", "")
MAX_VIDEO_MB = int(os.environ.get("FSOC_MAX_VIDEO_MB", "200"))
LOGS_DIR = DATA_DIR / "logs"
STATIC_DIR = APP_DIR / "static"
UI_DIR = APP_DIR / "ui"
UPLOAD_DIR = DATA_DIR / "data" / "uploaded_videos"

sys.path.insert(0, str(REPO_ROOT))  # so live_engine's `from control...` imports resolve
from web.live_engine import engine as live_engine  # noqa: E402
from config.param_schema import schema_as_json, resolve_ui_values, apply_scenario_preset_if_set  # noqa: E402
from algorithms import registry  # noqa: E402
from algorithms.api import AlgorithmError  # noqa: E402

app = FastAPI(title="FSOC Coarse Alignment Console")


if PASSWORD:
    import secrets

    @app.middleware("http")
    async def _require_password(request, call_next):
        auth = request.headers.get("authorization", "")
        ok = False
        if auth.lower().startswith("basic "):
            try:
                _, _, given = base64.b64decode(auth[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(given, PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Password required", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="FSOC console"'})
        return await call_next(request)


def _plugins_writable():
    if PUBLIC_MODE:
        raise HTTPException(status_code=403, detail="Adding or changing algorithms is turned off on this public "
                                                    "deployment. Run the console locally to test your own code.")


@app.get("/api/features")
def api_features() -> JSONResponse:
    return JSONResponse({"plugins_writable": not PUBLIC_MODE})
# Three.js and fonts fallbacks are local, so every page works offline at a demo.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _load_default_config() -> dict:
    import yaml
    with open(REPO_ROOT / "config" / "default_config.yaml") as f:
        return yaml.safe_load(f)


def _build_config(ui_values: dict) -> dict:
    cfg = resolve_ui_values(_load_default_config(), ui_values or {})
    return apply_scenario_preset_if_set(cfg)


def _safe_run_name(run_name: str) -> str:
    if not run_name or ".." in run_name or "/" in run_name or "\\" in run_name:
        raise HTTPException(status_code=404, detail="run not found")
    return run_name


def _is_summary_log(path: Path) -> bool:
    return not path.stem.endswith("_config")


def _run_meta(name: str) -> dict | None:
    p = LOGS_DIR / f"{name}_config.json"
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _list_runs() -> list[dict]:
    if not LOGS_DIR.exists():
        return []
    runs = []
    for json_path in sorted(LOGS_DIR.glob("run_*.json"), reverse=True):
        if not _is_summary_log(json_path):
            continue
        try:
            with open(json_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        meta = _run_meta(json_path.stem)
        runs.append({
            "name": json_path.stem,
            "metrics": data,
            "info": meta["info"] if meta else None,
            "has_frames": (LOGS_DIR / f"{json_path.stem}_frames.jsonl").exists(),
        })
    return runs


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

NAV = [
    ("/", "overview", "Overview"),
    ("/setup", "setup", "New run"),
    ("/live", "live", "Live"),
    ("/runs", "runs", "Runs"),
    ("/algorithms", "algorithms", "Algorithms"),
    ("/compare", "compare", "Compare"),
    ("/spec", "spec", "Spec check"),
]


def _page(file: str, active: str, replacements: dict | None = None) -> HTMLResponse:
    html = (UI_DIR / file).read_text(encoding="utf-8")
    links = "".join(
        f'<a href="{href}" class="nav-link{" is-active" if key == active else ""}"'
        f'{" aria-current=\"page\"" if key == active else ""} data-nav="{key}">'
        f'<span class="nav-ico" data-ico="{key}"></span><span>{label}</span></a>'
        for href, key, label in NAV
    )
    sidebar = (
        '<aside class="sidebar">'
        '<a class="brand" href="/"><span data-brand></span>'
        '<span><span class="brand-name" style="display:block">Coarse Alignment</span>'
        '<span class="brand-sub">FSOC pointing console</span></span></a>'
        f'<nav class="nav" aria-label="Main">{links}</nav>'
        '<a class="engine-pill" id="engine-pill" href="/setup">'
        '<span class="row"><span class="dot"></span><span class="label">Checking engine</span></span>'
        '<span class="sub" style="display:block">One moment</span></a>'
        '</aside>'
    )
    html = html.replace("<!--SIDEBAR-->", sidebar)
    for k, v in (replacements or {}).items():
        html = html.replace(k, v)
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def page_overview():
    return _page("overview.html", "overview")


@app.get("/setup", response_class=HTMLResponse)
def page_setup():
    return _page("setup.html", "setup")


@app.get("/live", response_class=HTMLResponse)
def page_live():
    return _page("live.html", "live")


@app.get("/runs", response_class=HTMLResponse)
def page_runs():
    return _page("runs.html", "runs")


@app.get("/runs/{run_name}", response_class=HTMLResponse)
def page_report(run_name: str):
    run_name = _safe_run_name(run_name)
    return _page("report.html", "runs", {"__RUN_NAME__": run_name})


@app.get("/spec", response_class=HTMLResponse)
def page_spec():
    return _page("spec.html", "spec")


@app.get("/algorithms", response_class=HTMLResponse)
def page_algorithms():
    return _page("algorithms.html", "algorithms")


@app.get("/compare", response_class=HTMLResponse)
def page_compare():
    return _page("compare.html", "compare")


# old URLs keep working
@app.get("/control")
def old_control():
    return RedirectResponse("/setup")


@app.get("/view/{run_name}")
def old_view(run_name: str):
    return RedirectResponse(f"/runs/{_safe_run_name(run_name)}")


# ---------------------------------------------------------------------------
# Run logs (read-only)
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def api_runs() -> JSONResponse:
    return JSONResponse(_list_runs())


@app.get("/api/runs/{run_name}")
def api_run_detail(run_name: str) -> JSONResponse:
    run_name = _safe_run_name(run_name)
    json_path = LOGS_DIR / f"{run_name}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    with open(json_path) as f:
        data = json.load(f)
    meta = _run_meta(run_name)
    return JSONResponse({
        "name": run_name,
        "metrics": data,
        "info": meta["info"] if meta else None,
        "config": meta["config"] if meta else None,
        "has_frames": (LOGS_DIR / f"{run_name}_frames.jsonl").exists(),
    })


def _read_frames(run_name: str) -> list[dict]:
    frames_path = LOGS_DIR / f"{run_name}_frames.jsonl"
    if not frames_path.exists():
        raise HTTPException(status_code=404, detail="this run has no per-frame log")
    records = []
    with open(frames_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


@app.get("/api/runs/{run_name}/frames")
def api_run_frames(run_name: str) -> JSONResponse:
    return JSONResponse(_read_frames(_safe_run_name(run_name)))


@app.get("/api/runs/{run_name}/centroids.csv")
def api_run_centroids(run_name: str) -> Response:
    """Per-frame centroiding log (Benchmark 1 and 2 ask for this): the
    detected centroid, the tracker estimate, ground truth when the run had
    one, and the centroiding error against it."""
    run_name = _safe_run_name(run_name)
    frames = _read_frames(run_name)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["frame_id", "timestamp_s", "lock_state", "detected", "centroid_x", "centroid_y",
                "estimate_x", "estimate_y", "truth_x", "truth_y", "centroid_error_px", "estimate_error_px"])
    for r in frames:
        c = r.get("centroid_px") or [None, None]
        p = r.get("predicted_px") or [None, None]
        gts = r.get("ground_truth_px") or []
        g = [None, None]
        c_err = p_err = None
        if gts:
            ref = c if c[0] is not None else p
            g = min(gts, key=lambda t: (t[0] - ref[0]) ** 2 + (t[1] - ref[1]) ** 2) if ref[0] is not None else gts[0]
            if c[0] is not None:
                c_err = round(((c[0] - g[0]) ** 2 + (c[1] - g[1]) ** 2) ** 0.5, 3)
            if p[0] is not None:
                p_err = round(((p[0] - g[0]) ** 2 + (p[1] - g[1]) ** 2) ** 0.5, 3)
        w.writerow([r["frame_id"], round(r["timestamp"], 4), r["lock_state"], int(bool(r["detected"])),
                    *(round(v, 3) if v is not None else "" for v in (c[0], c[1], p[0], p[1], g[0], g[1])),
                    "" if c_err is None else c_err, "" if p_err is None else p_err])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{run_name}_centroids.csv"'})


@app.get("/api/runs/{run_name}/download/{kind}")
def api_run_download(run_name: str, kind: str):
    run_name = _safe_run_name(run_name)
    files = {"json": f"{run_name}.json", "csv": f"{run_name}.csv", "frames": f"{run_name}_frames.jsonl"}
    if kind not in files:
        raise HTTPException(status_code=404, detail="unknown download")
    path = LOGS_DIR / files[kind]
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found for this run")
    return FileResponse(path, filename=files[kind])


# ---------------------------------------------------------------------------
# Config + preview
# ---------------------------------------------------------------------------

@app.get("/api/config/schema")
def api_config_schema() -> JSONResponse:
    return JSONResponse(schema_as_json())


@app.get("/api/config/default")
def api_config_default() -> JSONResponse:
    return JSONResponse(_load_default_config())


@app.post("/api/preview")
def api_preview(payload: dict) -> JSONResponse:
    """Renders one real camera frame for the given settings, with the
    camera pointed at the first target, so the setup page can show what
    the chosen noise/atmosphere/jitter actually does to the image before
    a run starts. Uses the real SimulatorEngine, not a mock."""
    import cv2
    from simulator.camera_model import CameraModel
    from simulator.disturbances import DisturbanceConfig
    from simulator.renderer import SimulatorEngine
    from simulator.scene import Scene
    try:
        cfg = _build_config(payload.get("ui_values", {}))
        scene = Scene.from_config(cfg)
        cam_cfg = cfg["camera"]
        tx, ty = scene.targets[0].position(0.0) if scene.targets else (cfg["screen"]["width"] / 2,) * 2
        camera = CameraModel(width_px=cam_cfg["resolution"][0], height_px=cam_cfg["resolution"][1],
                             fov_x_deg=cam_cfg["fov_deg"][0], fov_y_deg=cam_cfg["fov_deg"][1],
                             world_x=tx, world_y=ty)
        dcfg = DisturbanceConfig.from_config(cfg)
        dcfg.platform_motion = False
        engine = SimulatorEngine(scene, camera, dcfg, seed=7)
        img, _ = engine.render()
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        paths = []
        for t in scene.targets:
            pts = [t.position(i * 0.25) for i in range(0, 241)]
            paths.append([[round(x, 1), round(y, 1)] for x, y in pts])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({
        "image": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(),
        "screen": [cfg["screen"]["width"], cfg["screen"]["height"]],
        "fov_world": [cam_cfg["fov_deg"][0] * camera.world_px_per_deg, cam_cfg["fov_deg"][1] * camera.world_px_per_deg],
        "paths": paths,
    })


# ---------------------------------------------------------------------------
# Algorithms: list, view source, write, check, upload, delete
# ---------------------------------------------------------------------------

_FILENAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,60}\.py$")


def _user_file(filename: str) -> Path:
    if not _FILENAME_RE.match(filename or ""):
        raise HTTPException(status_code=400, detail="File name must be lowercase letters, digits and underscores, ending in .py")
    return registry.USER_DIR / filename


@app.get("/api/algorithms")
def api_algorithms() -> JSONResponse:
    return JSONResponse(registry.list_algorithms())


@app.get("/api/algorithms/source")
def api_algorithm_source(id: str = "", file: str = "") -> JSONResponse:
    import inspect
    if file:
        path = _user_file(file)
        if not path.exists():
            raise HTTPException(status_code=404, detail="file not found")
        return JSONResponse({"file": file, "code": path.read_text(encoding="utf-8"), "editable": True})
    try:
        cls = registry.get(id)
    except AlgorithmError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if id.startswith("user:"):
        fname = id.split(":")[1] + ".py"
        return JSONResponse({"file": fname, "code": (registry.USER_DIR / fname).read_text(encoding="utf-8"), "editable": True})
    return JSONResponse({"file": None, "code": inspect.getsource(cls), "editable": False})


@app.get("/api/algorithms/template")
def api_algorithm_template(slot: str, title: str = "My algorithm") -> JSONResponse:
    from algorithms.templates import TEMPLATES, render
    if slot not in TEMPLATES:
        raise HTTPException(status_code=400, detail="slot must be detector, tracker or controller")
    words = re.findall(r"[A-Za-z0-9]+", title) or ["My"]
    cls = "".join(w[:1].upper() + w[1:] for w in words)
    if cls[0].isdigit():
        cls = "Algo" + cls
    fname = "_".join(w.lower() for w in words)[:50]
    if fname[0].isdigit():
        fname = "algo_" + fname
    return JSONResponse({"file": f"{fname}.py", "code": render(slot, title.replace('"', "'"), cls)})


@app.post("/api/algorithms/check")
def api_algorithm_check(payload: dict) -> JSONResponse:
    _plugins_writable()
    from algorithms.benchmark import validate_code
    code = payload.get("code") or ""
    if not code.strip():
        raise HTTPException(status_code=400, detail="Nothing to check: the editor is empty")
    return JSONResponse(validate_code(code))


@app.post("/api/algorithms/save")
def api_algorithm_save(payload: dict) -> JSONResponse:
    _plugins_writable()
    path = _user_file(payload.get("file", ""))
    code = payload.get("code") or ""
    if path.exists() and not payload.get("overwrite"):
        raise HTTPException(status_code=409, detail=f"{path.name} already exists")
    try:
        compile(code, path.name, "exec")
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"Syntax error on line {exc.lineno}: {exc.msg}")
    registry.USER_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    listing = registry.list_algorithms()
    return JSONResponse({"file": path.name, "error": listing["errors"].get(path.name), **listing})


@app.post("/api/algorithms/upload")
async def api_algorithm_upload(file: UploadFile, overwrite: bool = False) -> JSONResponse:
    _plugins_writable()
    name = Path(file.filename or "").name.lower().replace("-", "_").replace(" ", "_")
    code = (await file.read()).decode("utf-8", errors="replace")
    return api_algorithm_save({"file": name, "code": code, "overwrite": overwrite})


@app.delete("/api/algorithms/file/{filename}")
def api_algorithm_delete(filename: str) -> JSONResponse:
    _plugins_writable()
    path = _user_file(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    path.unlink()
    return JSONResponse(registry.list_algorithms())


@app.get("/api/scenarios")
def api_scenarios() -> JSONResponse:
    from config.scenarios import SCENARIOS
    return JSONResponse(SCENARIOS)


# ---------------------------------------------------------------------------
# Benchmark: compare algorithm variants on the same scenarios and seeds
# ---------------------------------------------------------------------------

_bench = {"job": None}


@app.post("/api/bench/start")
def api_bench_start(payload: dict) -> JSONResponse:
    from algorithms.benchmark import BenchJob
    job = _bench["job"]
    if job is not None and not job.done:
        raise HTTPException(status_code=409, detail="A comparison is already running")
    if live_engine.is_running():
        raise HTTPException(status_code=409, detail="A live run is in progress. Stop it first so timings are fair")
    variants = payload.get("variants") or []
    scenarios = payload.get("scenarios") or []
    if len(variants) < 1 or not scenarios:
        raise HTTPException(status_code=400, detail="Pick at least one scenario and one algorithm set")
    for v in variants:
        for slot in ("detector", "tracker", "controller"):
            try:
                registry.get(v["algorithms"][slot]["id"])
            except (KeyError, AlgorithmError) as exc:
                raise HTTPException(status_code=400, detail=f"{v.get('name', 'Variant')}: {exc}")
    if "video" in scenarios and not payload.get("video_path"):
        raise HTTPException(status_code=400, detail="Upload a video to include it")
    job = BenchJob(scenarios, variants, int(payload.get("seeds", 1)), float(payload.get("duration_s", 10)),
                   str(LOGS_DIR), base_ui_values=payload.get("base_ui_values"),
                   video_path=payload.get("video_path"))
    _bench["job"] = job.start()
    return JSONResponse({"id": job.id, "total": job.total})


@app.get("/api/bench/status")
def api_bench_status() -> JSONResponse:
    job = _bench["job"]
    return JSONResponse(job.result() if job is not None else None)


@app.post("/api/bench/cancel")
def api_bench_cancel() -> JSONResponse:
    job = _bench["job"]
    if job is None or job.done:
        raise HTTPException(status_code=409, detail="No comparison is running")
    job.cancel()
    return JSONResponse({"cancelled": True})


@app.get("/api/bench")
def api_bench_list() -> JSONResponse:
    out = []
    for p in sorted(LOGS_DIR.glob("bench_*.json"), reverse=True):
        try:
            with open(p) as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        out.append({"id": d["id"], "variants": [v["name"] for v in d["variants"]],
                    "scenarios": len(d["scenarios"]), "runs": d["progress"], "total": d["total"],
                    "cancelled": d.get("cancelled"), "pass_rates": [s["pass_rate"] for s in d["summary"]]})
    return JSONResponse(out)


@app.get("/api/bench/{bench_id}")
def api_bench_get(bench_id: str) -> JSONResponse:
    if not re.match(r"^bench_\d{8}_\d{6}$", bench_id):
        raise HTTPException(status_code=404, detail="not found")
    p = LOGS_DIR / f"{bench_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    with open(p) as f:
        return JSONResponse(json.load(f))

# ---------------------------------------------------------------------------
# Live control
# ---------------------------------------------------------------------------

@app.post("/api/control/upload_video")
async def api_upload_video(file: UploadFile) -> JSONResponse:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.mp4").name  # strip any path components
    if not safe_name.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Only .mp4 files are accepted")
    dest = UPLOAD_DIR / safe_name
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_VIDEO_MB * 1024 * 1024:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Video is larger than {MAX_VIDEO_MB} MB")
            f.write(chunk)
    return JSONResponse({"path": str(dest), "name": safe_name})


@app.post("/api/control/start")
def api_control_start(payload: dict) -> JSONResponse:
    """payload: {"ui_values": {path: value}, "video_path": str|None, "realtime": bool}.
    ui_values resolve through the same config/param_schema.py the desktop
    GUI uses."""
    try:
        cfg = _build_config(payload.get("ui_values", {}))
        result = live_engine.start(cfg, str(LOGS_DIR), video_path=payload.get("video_path"),
                                   realtime=bool(payload.get("realtime", True)))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not start run: {exc}")
    return JSONResponse(result)


@app.post("/api/control/stop")
def api_control_stop() -> JSONResponse:
    try:
        result = live_engine.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse(result)


@app.get("/api/control/status")
def api_control_status() -> JSONResponse:
    return JSONResponse(live_engine.status())


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Streams per-frame telemetry (same FrameRecord schema as the replay
    files), the latest camera image as JPEG (~12 per second) with its
    matching record and world state, and a status message. Receive-only;
    start/stop go through the POST endpoints."""
    import cv2
    await websocket.accept()
    last_seq = -1
    tick = 0
    try:
        while True:
            await asyncio.sleep(0.04)
            tick += 1
            frames = live_engine.pop_new_frames()
            if frames:
                await websocket.send_json({"type": "frames", "frames": frames})
            if tick % 2 == 0:
                snap = live_engine.snapshot()
                if snap is not None and snap[0] != last_seq:
                    seq, img, record, world = snap
                    last_seq = seq
                    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        await websocket.send_json({
                            "type": "snapshot",
                            "image": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(),
                            "size": [int(img.shape[1]), int(img.shape[0])],
                            "record": record, "world": world,
                        })
            if tick % 5 == 0:
                await websocket.send_json({"type": "status", "status": live_engine.status()})
    except (WebSocketDisconnect, RuntimeError):
        pass


if __name__ == "__main__":
    import uvicorn
    print(f"Reading run logs from: {LOGS_DIR}")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8420"))
    print(f"Open http://{host}:{port}/" + ("  (public mode: plugin editing off)" if PUBLIC_MODE else ""))
    uvicorn.run(app, host=host, port=port, log_level="warning")
