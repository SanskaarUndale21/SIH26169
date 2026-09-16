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
  :root { color-scheme: light dark; }
  html, body { margin: 0; background: #0f1117; color: #e5e7eb;
               font-family: -apple-system, Segoe UI, Roboto, sans-serif; height: 100%; overflow: hidden; }
  header { padding: 10px 20px; border-bottom: 1px solid #23262f; display: flex; align-items: center; gap: 16px; }
  header h1 { margin: 0; font-size: 16px; font-weight: 600; flex: 1; }
  .nav-link { font-size: 13px; color: #60a5fa; text-decoration: none; }
  .nav-link:hover { text-decoration: underline; }
  #status-badge { font-size: 11px; padding: 3px 10px; border-radius: 12px; font-weight: 600; }
  .status-idle { background: #23262f; color: #9ca3af; }
  .status-live { background: #0f2a1a; color: #4ade80; border: 1px solid #22c55e; }
  .status-error { background: #2a1414; color: #f87171; border: 1px solid #ef4444; }
  button.action { background: #2563eb; color: white; border: none; border-radius: 6px;
                   padding: 7px 16px; font-size: 13px; cursor: pointer; font-weight: 500; }
  button.action:disabled { background: #374151; color: #6b7280; cursor: default; }
  button.action.stop { background: #dc2626; }
  main { display: grid; grid-template-columns: 340px 1fr 300px; height: calc(100vh - 49px); }
  #config-col { border-right: 1px solid #23262f; overflow-y: auto; display: flex; flex-direction: column; }
  #source-box { padding: 12px 16px; border-bottom: 1px solid #23262f; }
  #source-box select, #source-box input[type=file] { width: 100%; margin-top: 6px; background: #171922;
      color: #e5e7eb; border: 1px solid #334155; border-radius: 4px; padding: 4px; font-size: 12px; }
  #tab-buttons { display: flex; flex-wrap: wrap; gap: 2px; padding: 6px 10px; border-bottom: 1px solid #23262f; }
  #tab-buttons button { background: #171922; color: #9ca3af; border: 1px solid #23262f; border-radius: 4px;
                          padding: 3px 8px; font-size: 10px; cursor: pointer; }
  #tab-buttons button.active { background: #1e2530; color: #93c5fd; border-color: #2563eb; }
  #tab-panels { flex: 1; overflow-y: auto; padding: 8px 16px; }
  .param-row { margin: 10px 0; }
  .param-row label { display: block; font-size: 11px; color: #9ca3af; margin-bottom: 3px; }
  .param-row .row-inputs { display: flex; align-items: center; gap: 8px; }
  .param-row input[type=range] { flex: 1; }
  .param-row input[type=number] { width: 70px; background: #171922; color: #e5e7eb; border: 1px solid #334155;
      border-radius: 4px; padding: 3px 5px; font-size: 12px; }
  .param-row select { width: 100%; background: #171922; color: #e5e7eb; border: 1px solid #334155;
      border-radius: 4px; padding: 4px; font-size: 12px; }
  .param-row input[type=checkbox] { transform: scale(1.2); }
  .param-unit { font-size: 11px; color: #6b7280; }
  #center-col { position: relative; }
  #canvas-holder { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
  #legend { position: absolute; top: 10px; right: 14px; font-size: 11px; background: rgba(15,17,23,0.75);
            border: 1px solid #23262f; border-radius: 8px; padding: 8px 12px; }
  #legend div { margin: 2px 0; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
  #frame-readout { position: absolute; bottom: 10px; left: 14px; font-size: 11px; color: #9ca3af;
      background: rgba(15,17,23,0.75); border: 1px solid #23262f; border-radius: 8px; padding: 6px 10px; }
  #right-col { overflow-y: auto; padding: 12px; }
  .metric-card { background: #171922; border: 1px solid #23262f; border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
  .metric-card .label { font-size: 10px; color: #9ca3af; text-transform: uppercase; }
  .metric-card .value { font-size: 16px; font-weight: 600; margin-top: 2px; }
  .metric-card.ok .value { color: #4ade80; }
  .metric-card.bad .value { color: #f87171; }
  .metric-card.na .value { color: #9ca3af; }
  canvas.chart { width: 100%; height: 80px; background: #0a0b0f; border: 1px solid #23262f; border-radius: 6px;
                 margin-bottom: 10px; }
  .chart-title { font-size: 10px; color: #9ca3af; margin: 10px 0 4px; text-transform: uppercase; }
  #result-box { padding: 10px; margin-top: 8px; background: #0f2a1a; border: 1px solid #22c55e; border-radius: 6px;
                font-size: 12px; display: none; }
  #result-box a { color: #93c5fd; }
</style>
</head>
<body>
<header>
  <h1>FSOC Live Control <span id="status-badge" class="status-idle">idle</span></h1>
  <button id="startBtn" class="action">Start</button>
  <button id="stopBtn" class="action stop" disabled>Stop</button>
  <a href="/" class="nav-link">Results &amp; Replay &rarr;</a>
</header>
<main>
  <div id="config-col">
    <div id="source-box">
      <label style="font-size:11px;color:#9ca3af;">Input source</label>
      <select id="sourceSelect">
        <option value="simulator">Simulator</option>
        <option value="video">Load video file (.mp4)</option>
      </select>
      <input type="file" id="videoFile" accept=".mp4" style="display:none;">
      <div id="videoStatus" style="font-size:11px;color:#6b7280;margin-top:4px;"></div>
    </div>
    <div id="tab-buttons"></div>
    <div id="tab-panels"></div>
  </div>
  <div id="center-col">
    <div id="canvas-holder"></div>
    <div id="legend">
      <div><span class="dot" style="background:#4ade80"></span>Ground truth target</div>
      <div><span class="dot" style="background:#facc15"></span>Tracker estimate</div>
      <div><span class="dot" style="background:#ef4444"></span>Lock: searching</div>
      <div><span class="dot" style="background:#eab308"></span>Lock: acquiring/reacquiring</div>
      <div><span class="dot" style="background:#22c55e"></span>Lock: locked</div>
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

const THRESHOLDS = {
  acquisition_time_sec: {op: "<=", val: 2.0, unit: "s"},
  avg_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  max_tracking_error_px: {op: "<=", val: 10.0, unit: "px"},
  fps: {op: ">=", val: 20.0, unit: "FPS"},
  lock_retention_rate: {op: ">=", val: 0.95, unit: ""},
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
function fmtVal(val, unit) {
  if (val == null) return "N/A";
  if (Array.isArray(val)) return val.length + " event(s)";
  if (typeof val === "number") return (Math.abs(val) < 10 ? val.toFixed(3) : val.toFixed(2)) + (unit ? " " + unit : "");
  return String(val);
}
function updateCards(metrics) {
  if (!metrics) return;
  const container = document.getElementById("cards");
  container.innerHTML = "";
  for (const [key, val] of Object.entries(metrics)) {
    const t = THRESHOLDS[key];
    const div = document.createElement("div");
    div.className = "metric-card " + verdict(key, val);
    div.innerHTML = `<div class="label">${key.replace(/_/g, " ")}</div>
      <div class="value">${fmtVal(val, t ? t.unit : "")}</div>`;
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
