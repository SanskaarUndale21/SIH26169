"""HTML/JS for the /control live-control page. Kept in its own module so
dashboard_server.py (the FastAPI wiring) doesn't balloon in size.

The form is built entirely from GET /api/config/schema
(config/param_schema.py) -- there is no hand-typed list of parameters in
this file's JS, so it cannot drift out of sync with what the engine
actually reads or with what the desktop GUI's config panel exposes.
"""
from __future__ import annotations

CONTROL_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>FSOC Tracker -- Live Control</title>
<style>
  :root {
    color-scheme: dark;
    /* Graphite material + one warm accent (copper), pewter for
       processing-only states -- kept out of the pass/fail vocabulary
       below on purpose: --ok/--bad stay red/green because those encode
       an actual Section 10 pass/fail result, a real semantic a viewer
       already reads correctly; --accent is reserved for "this is live/
       primary," never reused for status. */
    --bg: #0a0a0c; --surface: rgba(19, 19, 22, 0.72); --surface-solid: #131316;
    --surface-raised: rgba(255,255,255,0.045);
    --border: rgba(217, 138, 79, 0.16); --border-light: rgba(217, 138, 79, 0.32);
    --text: #ece8e2; --text-muted: rgba(184, 188, 196, 0.75); --text-faint: rgba(107, 110, 117, 0.7);
    --accent: #d98a4f; --accent-bright: #ffb066; --accent-dim: #8a5230;
    --accent-wash: rgba(217, 138, 79, 0.14); --accent-glow: rgba(217, 138, 79, 0.35);
    --pewter: #93a1b0; --pewter-bright: #c3ccd6; --pewter-wash: rgba(147, 161, 176, 0.16);
    --ok: #7fb08a; --ok-text: #9fd4aa; --bad: #c9634f; --bad-text: #e8ab9d; --warn: #d9a94f;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: var(--bg); color: var(--text);
               font-family: "Segoe UI Semibold", "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
               height: 100%; overflow: hidden; }
  body {
    background-image:
      radial-gradient(circle at 15% 15%, rgba(217,138,79,0.06) 0%, transparent 40%),
      radial-gradient(circle at 85% 80%, rgba(147,161,176,0.05) 0%, transparent 45%);
  }
  header { padding: 12px 22px; border-bottom: 1px solid var(--border); background: rgba(15,15,17,0.9);
           backdrop-filter: blur(20px); display: flex; align-items: center; gap: 16px; }
  header .title-block { display: flex; flex-direction: column; gap: 1px; }
  header h1 { margin: 0; font-size: 15px; font-weight: 800; letter-spacing: 0.02em; }
  header .subtitle { font-size: 11px; color: var(--text-muted); }
  header .spacer { flex: 1; }
  .nav-link { font-size: 13px; color: var(--accent-bright); text-decoration: none; font-weight: 600; }
  .nav-link:hover { text-decoration: underline; }
  #status-badge { font-size: 10px; padding: 5px 13px; border-radius: 100px; font-weight: 700; letter-spacing: 0.08em;
                  text-transform: uppercase; border: 1px solid transparent; }
  .status-idle { background: rgba(255,255,255,0.06); color: var(--text-muted); }
  .status-live { background: var(--accent-wash); color: var(--accent-bright); border-color: var(--border-light);
                 box-shadow: 0 0 12px var(--accent-glow); }
  .status-error { background: rgba(201,99,79,0.14); color: var(--bad-text); border-color: rgba(201,99,79,0.4); }
  button.action { background: rgba(255,255,255,0.045); color: var(--text); border: 1px solid rgba(255,255,255,0.1);
                   border-radius: 10px; padding: 8px 18px; font-size: 13px; cursor: pointer; font-weight: 700;
                   transition: background 0.15s, border-color 0.15s, box-shadow 0.15s, transform 0.1s; }
  button.action:hover:not(:disabled) { transform: translateY(-1px); }
  button.action:active:not(:disabled) { transform: scale(0.97); }
  button.action:disabled { background: rgba(255,255,255,0.02); color: var(--text-faint); border-color: rgba(255,255,255,0.05); cursor: default; }
  button.action:not(.stop):not(:disabled) { background: linear-gradient(135deg, var(--accent), var(--accent-dim));
      border-color: var(--accent); color: #14100b; box-shadow: 0 4px 16px var(--accent-glow); }
  button.action:not(.stop):not(:disabled):hover { box-shadow: 0 6px 22px var(--accent-glow); }
  button.action.stop:not(:disabled) { border-color: rgba(201,99,79,0.5); color: var(--bad-text); }
  button.action.stop:not(:disabled):hover { background: rgba(201,99,79,0.14); }

  main { display: grid; grid-template-columns: 380px 1fr 320px; height: calc(100vh - 57px); }
  #config-col { border-right: 1px solid var(--border); overflow: hidden; display: flex; flex-direction: column;
                background: var(--surface-solid); }
  #source-box { padding: 14px 16px; border-bottom: 1px solid var(--border); }
  #source-box > label { font-size: 11px; color: var(--text-muted); font-weight: 700; text-transform: uppercase;
                          letter-spacing: 0.06em; }
  #source-box select, #source-box input[type=file] { width: 100%; margin-top: 6px; background: rgba(255,255,255,0.045);
      color: var(--text); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 7px 9px; font-size: 12px; }
  #config-body { flex: 1; display: flex; overflow: hidden; }
  #tab-buttons { width: 132px; overflow-y: auto; border-right: 1px solid var(--border);
                 padding: 6px 0; flex-shrink: 0; }
  #tab-buttons button { display: block; width: 100%; text-align: left; background: transparent;
      color: var(--text-muted); border: none; border-left: 2px solid transparent; padding: 9px 12px;
      font-size: 12px; cursor: pointer; transition: background 0.12s, color 0.12s; }
  #tab-buttons button.active { background: rgba(255,255,255,0.05); color: var(--accent-bright); border-left-color: var(--accent); }
  #tab-buttons button:hover:not(.active) { background: rgba(255,255,255,0.03); color: var(--text); }
  #tab-panels { flex: 1; overflow-y: auto; padding: 14px 18px; }
  .param-row { margin: 0 0 14px; }
  .param-row label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 5px; font-weight: 500; }
  .param-row .row-inputs { display: flex; align-items: center; gap: 10px; }
  .param-row input[type=range] { flex: 1; accent-color: var(--accent); }
  .param-row input[type=number] { width: 72px; background: rgba(255,255,255,0.045); color: var(--text);
      border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 4px 6px; font-size: 12px; }
  .param-row select { width: 100%; background: rgba(255,255,255,0.045); color: var(--text);
      border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 5px 8px; font-size: 12px; }
  .param-row input[type=checkbox] { transform: scale(1.25); accent-color: var(--accent); }

  #center-col { position: relative; background: var(--bg); }
  #canvas-holder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
  #legend { position: absolute; top: 12px; right: 16px; font-size: 11px; background: rgba(19,19,22,0.75);
            border: 1px solid var(--border); border-radius: 12px; padding: 12px 15px; backdrop-filter: blur(16px) saturate(1.3); }
  #legend div { margin: 4px 0; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  #frame-readout { position: absolute; bottom: 12px; left: 16px; font-size: 11px; color: var(--text-muted);
      background: rgba(19,19,22,0.75); border: 1px solid var(--border); border-radius: 12px; padding: 8px 13px;
      backdrop-filter: blur(16px) saturate(1.3); font-family: "JetBrains Mono", "SF Mono", Consolas, monospace; }

  #right-col { overflow-y: auto; padding: 16px; background: var(--surface-solid); }
  .chart-title { font-size: 10px; color: var(--text-muted); margin: 14px 0 6px; text-transform: uppercase;
                 letter-spacing: 0.06em; font-weight: 700; }
  .chart-title:first-child { margin-top: 0; }
  canvas.chart { width: 100%; height: 84px; background: rgba(0,0,0,0.3); border: 1px solid var(--border);
                 border-radius: 10px; display: block; }
  #cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .metric-card { background: rgba(255,255,255,0.035); border: 1px solid var(--border); border-radius: 10px;
                 padding: 10px 12px; transition: border-color 0.15s; }
  .metric-card .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.03em; }
  .metric-card .value { font-size: 17px; font-weight: 700; margin-top: 3px; }
  .metric-card.ok { border-color: rgba(127,176,138,0.35); }
  .metric-card.ok .value { color: var(--ok-text); }
  .metric-card.bad { border-color: rgba(201,99,79,0.4); }
  .metric-card.bad .value { color: var(--bad-text); }
  .metric-card.na .value { color: var(--text-faint); }
  #result-box { padding: 12px 14px; margin-top: 10px; background: rgba(127,176,138,0.1); border: 1px solid rgba(127,176,138,0.35);
                border-radius: 10px; font-size: 12px; line-height: 1.5; display: none; }
  #result-box a { color: var(--accent-bright); font-weight: 700; }
  ::-webkit-scrollbar { width: 5px; height: 5px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--accent-dim); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
</style>
</head>
<body>
<header>
  <div class="title-block">
    <h1>FSOC Live Control</h1>
    <span class="subtitle">Real live simulation engine -- same TrackingRunner as the desktop app</span>
  </div>
  <span id="status-badge" class="status-idle">idle</span>
  <span class="spacer"></span>
  <button id="startBtn" class="action">&#9654;&nbsp; Start</button>
  <button id="stopBtn" class="action stop" disabled>&#9632;&nbsp; Stop</button>
  <a href="/" class="nav-link">Results &amp; Replay &rarr;</a>
</header>
<main>
  <div id="config-col">
    <div id="source-box">
      <label>Input source</label>
      <select id="sourceSelect">
        <option value="simulator">Simulator</option>
        <option value="video">Load video file (.mp4)</option>
      </select>
      <input type="file" id="videoFile" accept=".mp4" style="display:none;">
      <div id="videoStatus" style="font-size:11px;color:var(--text-faint);margin-top:4px;"></div>
    </div>
    <div id="config-body">
      <div id="tab-buttons"></div>
      <div id="tab-panels"></div>
    </div>
  </div>
  <div id="center-col">
    <div id="canvas-holder"></div>
    <div id="legend">
      <div><span class="dot" style="background:#d98a4f"></span>Cone = camera boresight (real pan/tilt)</div>
      <div><span class="dot" style="background:#4ade80"></span>Ground truth target</div>
      <div><span class="dot" style="background:#facc15"></span>Tracker estimate</div>
      <div style="margin-top:6px;color:#5b6070;">Cone colour = lock state:</div>
      <div><span class="dot" style="background:#ef4444"></span>Searching</div>
      <div><span class="dot" style="background:#eab308"></span>Acquiring / reacquiring</div>
      <div><span class="dot" style="background:#22c55e"></span>Locked</div>
    </div>
    <div id="frame-readout">No live data yet. Press Start.</div>
  </div>
  <div id="right-col">
    <div class="chart-title">Tracking error (px) -- real per-frame value, 10px threshold line</div>
    <canvas id="errChart" class="chart"></canvas>
    <div class="chart-title">FPS (live aggregate) -- 20 FPS threshold line</div>
    <canvas id="fpsChart" class="chart"></canvas>
    <div class="chart-title">Live metrics</div>
    <div id="cards"></div>
    <div id="result-box"></div>
  </div>
</main>

<script type="importmap">
{ "imports": { "three": "/static/three.module.min.js" } }
</script>
<script type="module">
import { createPATScene } from "/static/pat_scene.js";

// Metrics with an actual Section 10 pass/fail target -- colour-coded.
const THRESHOLDS = {
  acquisition_time_sec: {op: "<=", val: 2.0, unit: "s"},
  avg_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  max_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  fps: {op: ">=", val: 20.0, unit: "FPS"},
  lock_retention_rate: {op: ">=", val: 0.95, unit: ""},
  processing_time_per_frame_ms: {op: "<=", val: 50.0, unit: "ms"},
};
// Units for metrics with no hard threshold, so cards like "Max pointing
// loss" or "Handoff-ready rate" still show a real unit instead of a
// bare, context-free number (the actual bug in an earlier screenshot).
const UNITS = {
  simulation_duration_sec: "s", rmse_px: "px",
  avg_angular_error_urad: "µrad", max_angular_error_urad: "µrad",
  avg_pointing_loss_db: "dB", max_pointing_loss_db: "dB",
  handoff_ready_rate: "%", time_to_handoff_ready_sec: "s",
};
const PERCENT_KEYS = new Set(["handoff_ready_rate", "lock_retention_rate"]);
const LABELS = {
  simulation_duration_sec: "Sim duration", fps: "FPS", acquisition_time_sec: "Acquisition time",
  avg_tracking_error_px: "Avg tracking error", max_tracking_error_px: "Max tracking error",
  lock_retention_rate: "Lock retention", processing_time_per_frame_ms: "Proc. time/frame",
  rmse_px: "RMSE", re_acquisition_count: "Re-acquisitions",
  avg_angular_error_urad: "Avg angular error", max_angular_error_urad: "Max angular error",
  avg_pointing_loss_db: "Avg pointing loss", max_pointing_loss_db: "Max pointing loss",
  handoff_ready_rate: "Handoff-ready rate", time_to_handoff_ready_sec: "Time to handoff-ready",
  re_acquisition_times_sec: "Re-acquisition times", target_loss_events: "Target loss events",
};

const patScene = createPATScene(document.getElementById("canvas-holder"));
patScene.startRenderLoop();

let videoPath = null;
let ws = null;
let currentRunName = null;

// ---- Build the config form from the shared schema ----
let schema = null;
async function loadSchema() {
  const res = await fetch("/api/config/schema");
  schema = await res.json();
  const tabButtons = document.getElementById("tab-buttons");
  const tabPanels = document.getElementById("tab-panels");
  const byGroup = {};
  for (const p of schema.params) (byGroup[p.group] ??= []).push(p);

  let first = true;
  for (const group of schema.groups) {
    if (!byGroup[group]) continue;
    const btn = document.createElement("button");
    btn.textContent = group;
    btn.className = first ? "active" : "";
    const panel = document.createElement("div");
    panel.style.display = first ? "block" : "none";
    panel.dataset.group = group;
    for (const p of byGroup[group]) {
      panel.appendChild(buildParamRow(p));
    }
    btn.addEventListener("click", () => {
      document.querySelectorAll("#tab-buttons button").forEach(b => b.classList.remove("active"));
      document.querySelectorAll("#tab-panels > div").forEach(d => d.style.display = "none");
      btn.classList.add("active");
      panel.style.display = "block";
    });
    tabButtons.appendChild(btn);
    tabPanels.appendChild(panel);
    first = false;
  }
}

function pathKey(path) { return path.join("/"); }

function buildParamRow(p) {
  const row = document.createElement("div");
  row.className = "param-row";
  row.dataset.key = pathKey(p.path);
  row.dataset.kind = p.kind;
  const label = document.createElement("label");
  label.textContent = p.label + (p.unit ? ` (${p.unit})` : "");
  if (p.help) label.title = p.help;
  row.appendChild(label);

  const inputs = document.createElement("div");
  inputs.className = "row-inputs";

  if (p.kind === "bool") {
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = !!p.default;
    row.dataset.widget = "checkbox";
    inputs.appendChild(cb);
    row._input = cb;
  } else if (p.kind === "enum") {
    const sel = document.createElement("select");
    for (const [value, disp] of p.options) {
      const opt = document.createElement("option");
      opt.value = value; opt.textContent = disp;
      if (value === p.default) opt.selected = true;
      sel.appendChild(opt);
    }
    row.dataset.widget = "select";
    inputs.appendChild(sel);
    row._input = sel;
  } else {
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = p.min; slider.max = p.max; slider.step = p.step || (p.kind === "int" ? 1 : 0.1);
    slider.value = p.default;
    const num = document.createElement("input");
    num.type = "number";
    num.min = p.min; num.max = p.max; num.step = p.step || (p.kind === "int" ? 1 : 0.1);
    num.value = p.default;
    slider.addEventListener("input", () => { num.value = slider.value; });
    num.addEventListener("input", () => { slider.value = num.value; });
    row.dataset.widget = "numeric";
    inputs.appendChild(slider);
    inputs.appendChild(num);
    row._input = num;
  }
  row.appendChild(inputs);
  return row;
}

function collectUiValues() {
  const values = {};
  document.querySelectorAll(".param-row").forEach(row => {
    const kind = row.dataset.kind;
    const input = row._input;
    if (kind === "bool") values[row.dataset.key] = input.checked;
    else if (kind === "enum") values[row.dataset.key] = input.value;
    else values[row.dataset.key] = parseFloat(input.value);
  });
  return values;
}

// ---- Input source ----
document.getElementById("sourceSelect").addEventListener("change", (e) => {
  document.getElementById("videoFile").style.display = e.target.value === "video" ? "block" : "none";
});
document.getElementById("videoFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const statusEl = document.getElementById("videoStatus");
  statusEl.textContent = "Uploading...";
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/control/upload_video", { method: "POST", body: form });
  const data = await res.json();
  videoPath = data.path;
  statusEl.textContent = "Uploaded: " + file.name;
});

// ---- Charts (hand-rolled canvas line charts, no extra library) ----
function makeChart(canvasId, thresholdVal, color) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const data = [];
  const MAX_POINTS = 200;
  function push(val) {
    if (val == null || Number.isNaN(val)) return;
    data.push(val);
    if (data.length > MAX_POINTS) data.shift();
    draw();
  }
  function draw() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = w * devicePixelRatio; canvas.height = h * devicePixelRatio;
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (data.length < 2) return;
    const maxVal = Math.max(thresholdVal * 1.3, ...data) || 1;
    const scaleX = w / (MAX_POINTS - 1);
    const scaleY = (v) => h - (v / maxVal) * h;
    ctx.strokeStyle = "#374151"; ctx.setLineDash([4, 3]); ctx.beginPath();
    ctx.moveTo(0, scaleY(thresholdVal)); ctx.lineTo(w, scaleY(thresholdVal)); ctx.stroke();
    ctx.setLineDash([]);
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
    data.forEach((v, i) => {
      const x = i * scaleX, y = scaleY(v);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  return { push };
}
const errChart = makeChart("errChart", 10.0, "#e05252");
const fpsChart = makeChart("fpsChart", 20.0, "#4a90d9");

// ---- Metric cards ----
function verdict(key, val) {
  const t = THRESHOLDS[key];
  if (!t || val == null) return "na";
  const ok = t.op === "<=" ? val <= t.val : val >= t.val;
  return ok ? "ok" : "bad";
}
function fmtVal(key, val, unit) {
  if (val == null) return "N/A";
  if (Array.isArray(val)) return val.length + " event(s)";
  if (PERCENT_KEYS.has(key) && typeof val === "number") return (val * 100).toFixed(1) + "%";
  if (typeof val === "number") return (Math.abs(val) < 10 ? val.toFixed(3) : val.toFixed(2)) + (unit ? " " + unit : "");
  return String(val);
}
function updateCards(metrics) {
  if (!metrics) return;
  const container = document.getElementById("cards");
  container.innerHTML = "";
  for (const [key, val] of Object.entries(metrics)) {
    const t = THRESHOLDS[key];
    const unit = t ? t.unit : (UNITS[key] || "");
    const label = LABELS[key] || key.replace(/_/g, " ");
    const div = document.createElement("div");
    div.className = "metric-card " + verdict(key, val);
    div.innerHTML = `<div class="label">${label}</div>
      <div class="value">${fmtVal(key, val, unit)}</div>`;
    container.appendChild(div);
  }
}

// ---- Live frame handling ----
function showFrame(rec) {
  const result = patScene.applyFrame(rec);
  document.getElementById("frame-readout").textContent =
    `frame ${rec.frame_id}   t=${rec.timestamp.toFixed(2)}s   lock=${rec.lock_state}   ` +
    `pan=${(rec.cam_pan_deg ?? 0).toFixed(2)}deg  tilt=${(rec.cam_tilt_deg ?? 0).toFixed(2)}deg`;
  if (result && result.trackingErrorPx != null) errChart.push(result.trackingErrorPx);
}

// ---- Start / Stop ----
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusBadge = document.getElementById("status-badge");

function setBadge(cls, text) {
  statusBadge.className = cls;
  statusBadge.textContent = text;
}

startBtn.addEventListener("click", async () => {
  document.getElementById("result-box").style.display = "none";
  const ui_values = collectUiValues();
  const isVideo = document.getElementById("sourceSelect").value === "video";
  if (isVideo && !videoPath) { alert("Upload a video file first."); return; }
  const payload = { ui_values, video_path: isVideo ? videoPath : null };
  const res = await fetch("/api/control/start", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    alert("Could not start: " + (err.detail || res.statusText));
    return;
  }
  const data = await res.json();
  currentRunName = data.run_name;
  startBtn.disabled = true;
  stopBtn.disabled = false;
  setBadge("status-live", "LIVE -- " + currentRunName);
  patScene.resetTrails();
  connectWebSocket();
});

stopBtn.addEventListener("click", async () => {
  const res = await fetch("/api/control/stop", { method: "POST" });
  const data = await res.json();
  startBtn.disabled = false;
  stopBtn.disabled = true;
  setBadge("status-idle", "idle");
  if (ws) { ws.close(); ws = null; }
  if (data.metrics) {
    const box = document.getElementById("result-box");
    box.style.display = "block";
    box.innerHTML = `Run <b>${data.run_name}</b> finished.
      Acquisition: ${fmtVal(data.metrics.acquisition_time_sec, "s")},
      Avg error: ${fmtVal(data.metrics.avg_tracking_error_px, "px")},
      FPS: ${fmtVal(data.metrics.fps, "")}.
      ${data.frames_path ? `<a href="/view/${encodeURIComponent(data.run_name)}" target="_blank">Open full 3D replay &#8599;</a>` : ""}`;
  }
});

function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/live`);
  ws.onmessage = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === "frames") {
      for (const rec of msg.frames) showFrame(rec);
    } else if (msg.type === "status") {
      updateCards(msg.status.metrics);
      if (msg.status.metrics && msg.status.metrics.fps != null) fpsChart.push(msg.status.metrics.fps);
      if (msg.status.error) {
        setBadge("status-error", "ERROR: " + msg.status.error);
      } else if (!msg.status.running && startBtn.disabled) {
        // engine stopped itself (e.g. video file ended) without the Stop button being pressed
        setBadge("status-idle", "finished");
        startBtn.disabled = false;
        stopBtn.disabled = true;
        if (ws) { ws.close(); ws = null; }
      }
    }
  };
}

loadSchema();
</script>
</body>
</html>"""
