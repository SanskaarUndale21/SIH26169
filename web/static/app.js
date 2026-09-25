// Shared helpers for every console page: nav icons, the engine status
// pill, spec thresholds and verdicts, number formatting, toasts, charts.

const ICONS = {
  overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.5"/><path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4"/></svg>',
  setup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>',
  live: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M12 9v6M9 12h6"/></svg>',
  runs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/></svg>',
  spec: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 9 2 2 4-4M8 15h8"/></svg>',
};

export const BRAND_SVG = `<svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
  <circle cx="17" cy="17" r="15" stroke="#2b3a63" stroke-width="2"/>
  <circle cx="17" cy="17" r="9" stroke="#37d8a8" stroke-width="2"/>
  <path d="M17 2v6M17 26v6M2 17h6M26 17h6" stroke="#6c7aa3" stroke-width="2"/>
  <rect x="14.5" y="14.5" width="5" height="5" fill="#ffb53d"/></svg>`;

// ---- Spec thresholds (problem statement, Performance Specifications) ----
export const SPEC = [
  { key: "acquisition", label: "Acquisition time", unit: "s", op: "<=", target: 2,
    get: m => m.acquisition_time_sec, note: "≤ 2 s from start to first lock" },
  { key: "error", label: "Tracking error", unit: "px", op: "<=", target: 10,
    get: m => m.avg_tracking_error_px, note: "≤ 10 px average while locked" },
  { key: "loss", label: "Target loss", unit: "%", op: "<", target: 5,
    get: m => (m.lock_retention_rate == null || m.acquisition_time_sec == null) ? null : (1 - m.lock_retention_rate) * 100,
    note: "< 5% of frames after first lock" },
  { key: "reacq", label: "Re-acquisition", unit: "s", op: "<=", target: 1,
    get: m => (m.re_acquisition_times_sec && m.re_acquisition_times_sec.length) ? Math.max(...m.re_acquisition_times_sec) : null,
    note: "≤ 1 s, worst case", noneText: "no losses" },
  { key: "fps", label: "Processing speed", unit: "FPS", op: ">=", target: 20,
    get: m => m.fps, note: "≥ 20 frames per second" },
];

export function judge(spec, value) {
  if (value == null || Number.isNaN(value)) return "na";
  const ok = spec.op === "<=" ? value <= spec.target : spec.op === "<" ? value < spec.target : value >= spec.target;
  return ok ? "pass" : "fail";
}

export function overallVerdict(m) {
  if (!m) return "na";
  const vs = SPEC.map(s => judge(s, s.get(m)));
  if (m.acquisition_time_sec == null) return "fail";
  return vs.every(v => v !== "fail") ? "pass" : "fail";
}

export function fmt(v, digits) {
  if (v == null || Number.isNaN(v)) return "–";
  const d = digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2);
  return Number(v).toFixed(d);
}

export function readoutHTML(spec, m) {
  const v = m ? spec.get(m) : null;
  const verdict = judge(spec, v);
  const shown = v == null ? (m && spec.noneText && m.acquisition_time_sec != null ? spec.noneText : "–") : fmt(v);
  const unit = v == null ? "" : `<span class="u">${spec.unit}</span>`;
  return `<div class="readout ${verdict}"><span class="k">${spec.label}</span>
    <span class="v num">${shown}${unit}</span><span class="t">${spec.note}</span></div>`;
}

export function runDate(name) {
  const m = /run_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/.exec(name || "");
  if (!m) return name;
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const MOTION_NAMES = {
  straight_line: "Straight line", circular: "Circular", figure8: "Figure of 8", random: "Random walk",
  spiral: "Spiral", sinusoidal: "Sinusoidal", user_defined: "User-defined path",
};
export const LOCK_NAMES = { searching: "Searching", acquiring: "Acquiring", reacquiring: "Re-acquiring", locked: "Locked" };
export const LOCK_COLORS = { searching: "#ff6e57", acquiring: "#8fb4ff", reacquiring: "#8fb4ff", locked: "#37d8a8" };

export function describeRun(info) {
  if (!info) return "Desktop app run";
  if (info.mode === "video") return `Video: ${info.video_name || "file"}`;
  if (info.preset) return info.preset.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  const n = info.num_targets > 1 ? `, ${info.num_targets} targets` : "";
  return (MOTION_NAMES[info.motion] || "Simulator") + n;
}

// ---- toast ----
let toastEl, toastTimer;
export function toast(msg, isError = false) {
  if (!toastEl) {
    toastEl = document.createElement("div");
    toastEl.className = "toast";
    toastEl.setAttribute("role", "status");
    document.body.appendChild(toastEl);
  }
  toastEl.textContent = msg;
  toastEl.classList.toggle("error", isError);
  toastEl.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 3800);
}

export async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// ---- charts (canvas, no library) ----
function prepCanvas(canvas) {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

/** xs/ys arrays, optional threshold line. Nulls break the line. */
export function drawLine(canvas, xs, ys, { threshold = null, color = "#ffb53d", yMin = 0, yMaxFloor = 1, thresholdLabel = "" } = {}) {
  const { ctx, w, h } = prepCanvas(canvas);
  const padL = 34, padB = 20, padT = 8, padR = 8;
  const valid = ys.filter(v => v != null);
  let yMax = Math.max(yMaxFloor, threshold ? threshold * 1.4 : 0, ...(valid.length ? valid : [0]));
  const step = niceCeil((yMax - yMin) / 4);
  yMax = yMin + step * 4;
  const x0 = xs.length ? xs[0] : 0, x1 = xs.length ? xs[xs.length - 1] : 1;
  const sx = x => padL + ((x - x0) / Math.max(1e-9, x1 - x0)) * (w - padL - padR);
  const sy = y => padT + (1 - (y - yMin) / (yMax - yMin)) * (h - padT - padB);
  ctx.font = "11px Archivo, system-ui"; ctx.fillStyle = "#6c7aa3"; ctx.strokeStyle = "rgba(143,164,222,0.12)"; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const v = yMin + (yMax - yMin) * i / 4, y = sy(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    ctx.fillText(fmt(v, v >= 10 ? 0 : 1), 4, y + 4);
  }
  if (xs.length > 1) {
    ctx.fillText(`${fmt(x0, 0)} s`, padL, h - 5);
    const end = `${fmt(x1, 0)} s`;
    ctx.fillText(end, w - padR - ctx.measureText(end).width, h - 5);
  }
  if (threshold != null) {
    ctx.strokeStyle = "rgba(255,110,87,0.7)"; ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(padL, sy(threshold)); ctx.lineTo(w - padR, sy(threshold)); ctx.stroke(); ctx.setLineDash([]);
    if (thresholdLabel) { ctx.fillStyle = "#ff9a88"; ctx.fillText(thresholdLabel, w - padR - ctx.measureText(thresholdLabel).width, sy(threshold) - 5); }
  }
  ctx.strokeStyle = color; ctx.lineWidth = 1.6; ctx.lineJoin = "round"; ctx.beginPath();
  let pen = false;
  for (let i = 0; i < xs.length; i++) {
    if (ys[i] == null) { pen = false; continue; }
    const X = sx(xs[i]), Y = sy(Math.min(ys[i], yMax));
    pen ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); pen = true;
  }
  ctx.stroke();
}

function niceCeil(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

/** Horizontal ribbon of lock state over time. */
export function drawLockRibbon(canvas, times, states) {
  const { ctx, w, h } = prepCanvas(canvas);
  if (times.length < 2) return;
  const t0 = times[0], t1 = times[times.length - 1];
  const sx = t => ((t - t0) / Math.max(1e-9, t1 - t0)) * w;
  for (let i = 0; i < times.length - 1; i++) {
    ctx.fillStyle = LOCK_COLORS[states[i]] || "#6c7aa3";
    ctx.fillRect(sx(times[i]), 0, Math.max(1, sx(times[i + 1]) - sx(times[i]) + 0.5), h);
  }
}

// ---- shell: icons + engine pill ----
function initShell() {
  document.querySelectorAll("[data-ico]").forEach(el => { el.innerHTML = ICONS[el.dataset.ico] || ""; });
  const brand = document.querySelector("[data-brand]");
  if (brand) brand.innerHTML = BRAND_SVG;
  const pill = document.getElementById("engine-pill");
  if (!pill) return;
  async function poll() {
    try {
      const s = await api("/api/control/status");
      const live = s.running;
      pill.querySelector(".dot").classList.toggle("live", live);
      pill.querySelector(".label").textContent = live ? "Run in progress" : "Engine idle";
      pill.querySelector(".sub").textContent = live ? "Open the live view" : "Ready for a new run";
      pill.href = live ? "/live" : "/setup";
    } catch {
      pill.querySelector(".label").textContent = "Server unreachable";
      pill.querySelector(".sub").textContent = "Restart dashboard_server.py";
    }
  }
  poll(); setInterval(poll, 2500);
}
initShell();
