"""Web dashboard: browse past run logs/3D replays, AND drive a real live
simulation run from the browser (web/live_engine.py) -- the desktop GUI
and this page are two independent front-ends over the same real engine
code (control/run_loop.TrackingRunner, config/param_schema.py), not two
different implementations that could drift apart or disagree.

This does import simulator/perception/control now (via live_engine.py),
a deliberate trade made when the product's scope grew to "the web UI is
also a full control surface" -- earlier revisions of this file kept it
strictly read-only/decoupled for demo-day reliability; that guarantee no
longer holds for the /control page specifically. The /view/{name} replay
and /api/runs browsing endpoints remain pure log readers regardless.

Run with:
    python web/dashboard_server.py
then open http://127.0.0.1:8420/
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
LOGS_DIR = REPO_ROOT / "logs"
STATIC_DIR = APP_DIR / "static"
UPLOAD_DIR = REPO_ROOT / "data" / "uploaded_videos"

sys.path.insert(0, str(REPO_ROOT))  # so live_engine's `from control...` imports resolve
from web.live_engine import engine as live_engine  # noqa: E402
from config.param_schema import schema_as_json, resolve_ui_values, apply_scenario_preset_if_set  # noqa: E402

app = FastAPI(title="FSOC Tracker -- Dashboard & Live Control")
# Three.js is served from a local file (web/static/), not a CDN, so both
# the replay and live-control 3D views work with no internet connection
# during a demo.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _load_default_config() -> dict:
    import yaml
    with open(REPO_ROOT / "config" / "default_config.yaml") as f:
        return yaml.safe_load(f)


def _safe_run_name(run_name: str) -> str:
    if not run_name or ".." in run_name or "/" in run_name or "\\" in run_name:
        raise HTTPException(status_code=404, detail="run not found")
    return run_name


def _list_runs() -> list[dict]:
    if not LOGS_DIR.exists():
        return []
    runs = []
    for json_path in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        try:
            with open(json_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        runs.append({"name": json_path.stem, "metrics": data})
    return runs


@app.get("/api/runs")
def api_runs() -> JSONResponse:
    """Lists every run log found in logs/, newest first. Read-only --
    this endpoint cannot trigger a new run or modify anything."""
    return JSONResponse(_list_runs())


@app.get("/api/runs/{run_name}")
def api_run_detail(run_name: str) -> JSONResponse:
    run_name = _safe_run_name(run_name)
    json_path = LOGS_DIR / f"{run_name}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="run not found")
    with open(json_path) as f:
        data = json.load(f)
    data["_has_3d_frames"] = (LOGS_DIR / f"{run_name}_frames.jsonl").exists()
    return JSONResponse(data)


@app.get("/api/runs/{run_name}/frames")
def api_run_frames(run_name: str) -> JSONResponse:
    """Returns the real per-frame trace of a run (perf_logging/frame_log.py's
    FrameRecord, one per line), exactly as recorded during that run --
    no interpolation or synthesis. 404 if this run predates frame-level
    logging or was a raw-video run with no camera geometry to record."""
    run_name = _safe_run_name(run_name)
    frames_path = LOGS_DIR / f"{run_name}_frames.jsonl"
    if not frames_path.exists():
        raise HTTPException(status_code=404,
                             detail="no per-frame log for this run (predates frame logging, "
                                    "or was recorded in raw-video mode with no camera geometry)")
    records = []
    with open(frames_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return JSONResponse(records)


# ---------------------------------------------------------------------------
# Live control: real simulation runs started/stopped/configured from the
# browser, via web/live_engine.py's LiveEngine (the same real engine code
# gui/main_window.py drives, not a reimplementation).
# ---------------------------------------------------------------------------

@app.get("/api/config/schema")
def api_config_schema() -> JSONResponse:
    """The single parameter schema both this page and the desktop GUI
    build their forms from (config/param_schema.py) -- so the two UIs
    can't silently expose different knobs."""
    return JSONResponse(schema_as_json())


@app.get("/api/config/default")
def api_config_default() -> JSONResponse:
    return JSONResponse(_load_default_config())


@app.post("/api/control/upload_video")
async def api_upload_video(file: UploadFile) -> JSONResponse:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.mp4").name  # strip any path components
    dest = UPLOAD_DIR / safe_name
    with open(dest, "wb") as f:
        f.write(await file.read())
    return JSONResponse({"path": str(dest)})


@app.post("/api/control/start")
async def api_control_start(payload: dict) -> JSONResponse:
    """payload: {"ui_values": {<path/string>: value, ...}, "video_path": optional str}.
    ui_values is resolved against config/default_config.yaml through the
    exact same config/param_schema.py machinery the desktop GUI uses, so
    a web-started run and a GUI-started run with the same slider values
    produce the same config dict, not two independently-guessed ones."""
    base_cfg = _load_default_config()
    ui_values = payload.get("ui_values", {})
    cfg = resolve_ui_values(base_cfg, ui_values)
    cfg = apply_scenario_preset_if_set(cfg)
    try:
        result = live_engine.start(cfg, video_path=payload.get("video_path"))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"could not start run: {exc}")
    return JSONResponse(result)


@app.post("/api/control/stop")
def api_control_stop() -> JSONResponse:
    try:
        result = live_engine.stop(str(LOGS_DIR))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse(result)


@app.get("/api/control/status")
def api_control_status() -> JSONResponse:
    return JSONResponse(live_engine.status())


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    """Streams real per-frame telemetry (identical FrameRecord schema to
    the .jsonl replay files) as it's produced by the live engine, plus a
    periodic status/metrics message. No control happens over this socket
    -- it is receive-only from the browser's perspective; start/stop go
    through the POST endpoints above."""
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(0.05)
            frames = live_engine.pop_new_frames()
            if frames:
                await websocket.send_json({"type": "frames", "frames": frames})
            await websocket.send_json({"type": "status", "status": live_engine.status()})
    except WebSocketDisconnect:
        pass


@app.get("/control", response_class=HTMLResponse)
def control_page() -> str:
    return _CONTROL_HTML


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _PAGE_HTML


@app.get("/view/{run_name}", response_class=HTMLResponse)
def view_3d(run_name: str) -> str:
    run_name = _safe_run_name(run_name)
    return _VIEW3D_HTML.replace("__RUN_NAME__", run_name)


_PAGE_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>FSOC Tracker -- Results Dashboard</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         background: #0f1117; color: #e5e7eb; }
  header { padding: 20px 28px; border-bottom: 1px solid #23262f; }
  header h1 { margin: 0; font-size: 18px; font-weight: 600; }
  header p { margin: 4px 0 0; color: #8b8f9a; font-size: 13px; }
  .badge { display: inline-block; background: #1e293b; color: #7dd3fc;
           padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 8px; }
  .nav-link { float: right; font-size: 13px; color: #60a5fa; text-decoration: none; font-weight: 500; }
  .nav-link:hover { text-decoration: underline; }
  main { display: grid; grid-template-columns: 280px 1fr; gap: 0; min-height: calc(100vh - 80px); }
  #runlist { border-right: 1px solid #23262f; overflow-y: auto; }
  .run-item { padding: 12px 20px; cursor: pointer; border-bottom: 1px solid #1a1c24; font-size: 13px; }
  .run-item:hover { background: #171922; }
  .run-item.active { background: #1e2530; border-left: 3px solid #60a5fa; }
  .run-item .name { font-weight: 600; }
  .run-item .verdict { font-size: 11px; margin-top: 4px; }
  .verdict.pass { color: #4ade80; }
  .verdict.fail { color: #f87171; }
  #detail { padding: 24px 32px; }
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
                   gap: 12px; margin-top: 16px; }
  .metric-card { background: #171922; border: 1px solid #23262f; border-radius: 8px; padding: 14px; }
  .metric-card .label { font-size: 11px; color: #8b8f9a; text-transform: uppercase; letter-spacing: 0.03em; }
  .metric-card .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
  .metric-card .unit { font-size: 12px; color: #8b8f9a; margin-left: 4px; }
  .metric-card.ok .value { color: #4ade80; }
  .metric-card.bad .value { color: #f87171; }
  .metric-card.na .value { color: #6b7280; }
  .empty { color: #6b7280; padding: 40px; text-align: center; }
  .raw { margin-top: 24px; }
  .raw pre { background: #0a0b0f; padding: 16px; border-radius: 8px; overflow-x: auto;
             font-size: 12px; color: #a1a1aa; }
  .disclaimer { background: #1e2530; border: 1px solid #2d3444; border-radius: 6px;
                padding: 10px 14px; font-size: 12px; color: #93c5fd; margin-bottom: 20px; }
  .replay-btn { display: inline-block; margin-left: 12px; background: #2563eb; color: white;
                padding: 3px 10px; border-radius: 5px; text-decoration: none; font-size: 12px; }
  .replay-btn.disabled { background: #374151; color: #9ca3af; cursor: default; }
</style>
</head>
<body>
<header>
  <h1>FSOC Coarse-Alignment Tracker <span class="badge">results &amp; replay</span>
    <a href="/control" class="nav-link">Open Live Control &rarr;</a></h1>
  <p>Browses logs already written by past runs (from here or the desktop app). For starting a new
     live run from the browser, use <a href="/control">Live Control</a>.</p>
</header>
<main>
  <div id="runlist"><div class="empty">Loading...</div></div>
  <div id="detail"><div class="empty">Select a run on the left.</div></div>
</main>
<script>
const THRESHOLDS = {
  acquisition_time_sec: {op: "<=", val: 2.0, unit: "s"},
  avg_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  max_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  fps: {op: ">=", val: 20.0, unit: "FPS"},
  lock_retention_rate: {op: ">=", val: 0.95, unit: ""},
};

function verdictClass(key, val) {
  const t = THRESHOLDS[key];
  if (!t || val === null || val === undefined) return "na";
  const ok = t.op === "<=" ? val <= t.val : val >= t.val;
  return ok ? "ok" : "bad";
}

function fmt(val, unit) {
  if (val === null || val === undefined) return "N/A";
  if (Array.isArray(val)) return val.length + " event(s)";
  if (typeof val === "number") return val.toFixed(val < 10 ? 3 : 2) + (unit ? " " + unit : "");
  return String(val);
}

async function loadRuns() {
  const res = await fetch("/api/runs");
  const runs = await res.json();
  const list = document.getElementById("runlist");
  if (runs.length === 0) {
    list.innerHTML = '<div class="empty">No runs yet.<br>Run main.py, Start/Stop a session, then refresh.</div>';
    return;
  }
  list.innerHTML = "";
  runs.forEach((run, i) => {
    const m = run.metrics;
    const overall = ["acquisition_time_sec","avg_tracking_error_px","fps"]
      .map(k => verdictClass(k, m[k]))
      .filter(c => c !== "na");
    const verdictText = overall.length === 0 ? "no data" : (overall.every(c => c === "ok") ? "PASS" : "attention");
    const div = document.createElement("div");
    div.className = "run-item" + (i === 0 ? " active" : "");
    div.innerHTML = `<div class="name">${run.name}</div>
      <div class="verdict ${verdictText === 'PASS' ? 'pass' : verdictText === 'attention' ? 'fail' : ''}">${verdictText}</div>`;
    div.onclick = () => selectRun(run.name, div);
    list.appendChild(div);
  });
  if (runs.length > 0) selectRun(runs[0].name, list.firstChild);
}

async function selectRun(name, el) {
  document.querySelectorAll(".run-item").forEach(x => x.classList.remove("active"));
  if (el) el.classList.add("active");
  const res = await fetch(`/api/runs/${encodeURIComponent(name)}`);
  const m = await res.json();
  const detail = document.getElementById("detail");
  const cards = Object.entries(m).map(([key, val]) => {
    const cls = verdictClass(key, val);
    const unit = THRESHOLDS[key] ? THRESHOLDS[key].unit : "";
    return `<div class="metric-card ${cls}">
      <div class="label">${key.replace(/_/g, " ")}</div>
      <div class="value">${fmt(val, unit)}</div>
    </div>`;
  }).join("");
  const replayBtn = m._has_3d_frames
    ? `<a href="/view/${encodeURIComponent(name)}" class="replay-btn" target="_blank">Open 3D Replay &#8599;</a>`
    : `<span class="replay-btn disabled" title="No per-frame log for this run">3D Replay unavailable</span>`;
  detail.innerHTML = `
    <div class="disclaimer">Showing recorded results from <b>${name}</b>. This page only reads the log file -- it cannot start or affect a run. ${replayBtn}</div>
    <div class="metrics-grid">${cards}</div>
    <div class="raw"><div class="label" style="color:#8b8f9a;font-size:12px;margin-bottom:8px;">Raw JSON</div>
      <pre>${JSON.stringify(m, null, 2)}</pre></div>`;
}

loadRuns();
</script>
</body>
</html>"""


_VIEW3D_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>3D Replay -- __RUN_NAME__</title>
<style>
  html, body { margin: 0; background: #0a0b0f; color: #e5e7eb; font-family: -apple-system, Segoe UI, Roboto, sans-serif;
               overflow: hidden; }
  #canvas-holder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
  #hud { position: absolute; top: 0; left: 0; padding: 14px 18px; pointer-events: none; }
  #hud h1 { font-size: 14px; margin: 0 0 4px; font-weight: 600; }
  #hud .note { font-size: 11px; color: #9ca3af; max-width: 420px; line-height: 1.4; }
  #legend { position: absolute; top: 14px; right: 18px; font-size: 11px; background: rgba(15,17,23,0.75);
            border: 1px solid #23262f; border-radius: 8px; padding: 10px 14px; }
  #legend div { margin: 3px 0; }
  .dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }
  #controls { position: absolute; bottom: 0; left: 0; right: 0; background: rgba(15,17,23,0.9);
              border-top: 1px solid #23262f; padding: 12px 18px; display: flex; align-items: center; gap: 12px; }
  #controls button { background: #1e293b; color: #e5e7eb; border: 1px solid #334155; border-radius: 6px;
                      padding: 6px 14px; cursor: pointer; font-size: 13px; }
  #controls button:hover { background: #263447; }
  #scrub { flex: 1; }
  #frame-label { font-size: 12px; color: #9ca3af; min-width: 170px; }
  #status { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
             font-size: 13px; color: #9ca3af; }
</style>
</head>
<body>
<div id="canvas-holder"></div>
<div id="hud">
  <h1>3D PAT Replay -- __RUN_NAME__</h1>
  <div class="note">Real recorded telemetry, replayed frame-by-frame. Copper cone = camera boresight
    (actual PTZ pan/tilt this frame). Green dot = simulator ground truth. Yellow dot = tracker's
    estimate (predicted_px, converted back to an absolute angle). Positions are drawn at a fixed
    display range -- this simulator is 2D and does not model true 3D distance.</div>
</div>
<div id="legend">
  <div><span class="dot" style="background:#d98a4f"></span>Cone = camera boresight (real pan/tilt)</div>
  <div><span class="dot" style="background:#4ade80"></span>Ground truth target</div>
  <div><span class="dot" style="background:#facc15"></span>Tracker estimate</div>
  <div style="margin-top:6px;color:#5b6070;">Cone colour = lock state:</div>
  <div><span class="dot" style="background:#ef4444"></span>Searching</div>
  <div><span class="dot" style="background:#eab308"></span>Acquiring / reacquiring</div>
  <div><span class="dot" style="background:#22c55e"></span>Locked</div>
</div>
<div id="status">Loading real run data...</div>
<div id="controls" style="display:none">
  <button id="playBtn">Pause</button>
  <input type="range" id="scrub" min="0" max="0" value="0">
  <div id="frame-label">frame 0 / 0</div>
</div>

<script type="importmap">
{ "imports": { "three": "/static/three.module.min.js" } }
</script>
<script type="module">
import { createPATScene } from "/static/pat_scene.js";

const RUN_NAME = "__RUN_NAME__";
const patScene = createPATScene(document.getElementById("canvas-holder"));
patScene.startRenderLoop();

let frames = [];
let idx = 0;
let playing = true;

function showFrame(rec) {
  patScene.applyFrame(rec);
  document.getElementById("frame-label").textContent =
    `frame ${rec.frame_id} / ${frames.length - 1}   t=${rec.timestamp.toFixed(2)}s   lock=${rec.lock_state}`;
}

async function load() {
  const status = document.getElementById("status");
  try {
    const res = await fetch(`/api/runs/${encodeURIComponent(RUN_NAME)}/frames`);
    if (!res.ok) {
      const err = await res.json();
      status.textContent = "No 3D data: " + (err.detail || res.statusText);
      return;
    }
    frames = await res.json();
  } catch (e) {
    status.textContent = "Failed to load run data: " + e;
    return;
  }
  if (frames.length === 0) {
    status.textContent = "This run has no recorded frames.";
    return;
  }
  status.style.display = "none";
  document.getElementById("controls").style.display = "flex";
  const scrub = document.getElementById("scrub");
  scrub.max = frames.length - 1;
  scrub.addEventListener("input", () => {
    idx = parseInt(scrub.value, 10); playing = false; playBtn.textContent = "Play"; showFrame(frames[idx]);
  });
  showFrame(frames[0]);
}

const playBtn = document.getElementById("playBtn");
playBtn.addEventListener("click", () => {
  playing = !playing;
  playBtn.textContent = playing ? "Pause" : "Play";
});

let lastAdvance = performance.now();
function advance() {
  requestAnimationFrame(advance);
  const now = performance.now();
  if (playing && frames.length > 0 && now - lastAdvance > 33) {
    idx = (idx + 1) % frames.length;
    document.getElementById("scrub").value = idx;
    showFrame(frames[idx]);
    lastAdvance = now;
  }
}

load();
advance();
</script>
</body>
</html>"""


from web.control_page import CONTROL_HTML as _CONTROL_HTML  # noqa: E402


if __name__ == "__main__":
    import uvicorn
    print(f"Reading run logs from: {LOGS_DIR}")
    print("Open http://127.0.0.1:8420/       for results & replay")
    print("Open http://127.0.0.1:8420/control for live simulation control")
    uvicorn.run(app, host="127.0.0.1", port=8420, log_level="warning")
