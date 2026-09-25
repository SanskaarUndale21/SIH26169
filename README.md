# FSOC Coarse-Alignment Tracker

Software-only virtual camera tracking system for coarse pointing/acquisition/
tracking (PAT) of a simulated FSOC beacon, plus an identical pipeline path
for raw external `.mp4` video (Benchmark-2 style ingestion).

## Install

```
pip install -r requirements.txt
```

Requires Python 3.10+.

## Run the desktop GUI

```
python main.py
```

Pick "Simulator" or "Load video file (.mp4)" in the config panel, tweak
any of the 74 exposed parameters (screen/camera/target motion of all
four types/PTZ/every disturbance intensity/detector/IMM/PID/link
budget/scenario presets), and press Start. Live 2D dashboard and a 3D
pan-tilt visualization update as the run progresses; every parameter is
also readable/writable from `config/param_schema.py` if you want to
script a sweep.

## Run the web console

```
python web/dashboard_server.py
```

Open `http://127.0.0.1:8420/`. One page per job, same engine as the
desktop GUI (`web/live_engine.py` runs a real `TrackingRunner`):

- `/` Overview: latest run scored against the spec, recent runs.
- `/setup` New run: five-step scenario builder (source, scene and
  camera, beacon and motion, disturbances, tracking) with quick-start
  scenarios, a live rendered camera preview and the beacon's path on the
  full screen. Upload an `.mp4` here for Benchmark 2.
- `/live` Live: real camera feed with tracker overlays, whole-screen map,
  3D gimbal view, lock state and each spec target updating live.
- `/runs` and `/runs/<name>`: every run, and a report per run with charts,
  3D replay, and downloads (performance log JSON/CSV, per-frame centroid
  log CSV).
- `/algorithms` Algorithms: browse built-in and plugin algorithms, write
  one from a template in the browser, upload a `.py`, and check it on two
  quick scenarios before saving.
- `/compare` Compare: run two to four algorithm sets through the same
  scenarios with the same seeds, scored against the spec targets.
- `/spec` Spec check: every problem-statement requirement and its status.

## Test your own algorithm

Any of the three loop stages (detector, tracker, pointing controller) can
be replaced by a Python class in `user_algorithms/`, written against
`algorithms/api.py`. See `docs/algorithm_guide.md`. Three working
examples ship in `user_algorithms/`.

## Run tests

```
pytest tests/                      # unit tests + robustness/stress tests
python tests/benchmark_matrix.py   # Section 12 motion x disturbance matrix
python tests/smoke_test.py         # quick headless end-to-end check
```

`tests/test_robustness.py` runs the real `TrackingRunner` (not a mock)
through conditions well outside a rehearsed demo: every disturbance
stacked at its schema-legal maximum at once, a target faster than the
configured PTZ can physically slew, tiny/huge screen and camera sizes,
5 simultaneous targets, a ~2000-frame long-haul run under combined noise,
and a target that is never detectable for the entire run -- checking the
engine degrades to `searching`/`reacquiring` and reports finite metrics
instead of crashing or dividing by zero.

## Architecture

Three modules, connected only through the `Frame` -> `Telemetry` interfaces
in `perception/frame_source.py` and `perception/pipeline.py`:

- `simulator/` -- virtual scene, target motion models, camera/PTZ model,
  disturbance injection. Produces `Frame` objects only.
- `perception/` -- DoG point-source detector + IMM tracker (CV/CT/random-
  walk models) + lock-state machine + search patterns. Consumes `Frame`,
  produces `Telemetry`. Never imports from `simulator/`.
- `control/` -- PID pointing controller, PTZ actuator interface, search
  sweep drivers, and `run_loop.py` which orchestrates a full run headlessly.
- `gui/` -- Qt GUI wiring config -> frame source -> pipeline -> control ->
  live view/dashboard/performance log.
- `perf_logging/` -- performance log writer (named `perf_logging`, not
  `logging`, to avoid shadowing Python's stdlib `logging` module that
  several dependencies rely on) plus `frame_log.py`'s per-frame recorder,
  the real telemetry trace both 3D views (GUI and web) replay/stream from.
- `web/` -- `dashboard_server.py` (FastAPI: pages, run logs, preview,
  live control, WebSocket stream), `live_engine.py` (runs a real
  `TrackingRunner` in a background thread), `ui/*.html` (one file per
  page), `static/app.css` + `app.js` (shared design system and charts),
  `static/pat_scene.js` (Three.js 3D gimbal scene).
- `config/param_schema.py` -- the single list of every tweakable
  parameter (74 across scene/camera/target-motion/PTZ/disturbances/
  detector/tracker/PID/link-budget/scenario-presets), consumed by
  *both* `gui/config_panel.py` and the web New run page so neither UI
  can silently expose a different knob set than the other.

See `config/default_config.yaml` for every configurable parameter and its
default, `docs/` for the technical report and user manual, and
`docs/demo_script.md` for a live-judging run-of-show, likely panel
questions, and a fallback plan if something breaks mid-demo.

## Space-science relevance additions

- `simulator/link_budget.py` -- converts tracking error (px) to angular
  pointing error (µrad) to actual link cost (dB pointing loss against a
  configured beam divergence), and reports when coarse pointing is inside
  the fine-pointing stage's capture range (`handoff_ready_rate`,
  `time_to_handoff_ready_sec` in the performance log). Also derives the
  turbulence Fried parameter from a real Hufnagel-Valley Cn² integration
  (`disturbances.turbulence.physical: true`) instead of an arbitrary
  tuning constant.
- `simulator/orbital.py` + `simulator/scenario_presets.py` -- three named
  scenarios (`leo_leo_crosslink`, `leo_ground_downlink`, `geo_ground`)
  whose target motion is derived from real orbital-mechanics formulas
  (orbital velocity, pass geometry, station-keeping residual), not a
  radius/speed picked to look reasonable. Select via `scenario_preset` in
  config or the GUI's scenario dropdown.
- `simulator/disturbances.py`'s `StructuredJitterModel` -- optional
  resonant-PSD jitter (`disturbances.jitter.structured: true`) modeling
  reaction-wheel-like narrow-band vibration instead of flat random noise.

See `docs/technical_report.md` Section 11 for the full writeup and the
formulas behind each.

## How this matches real FSOC/PAT practice

This isn't just a simulator with plausible-looking numbers -- the core
formulas and architecture line up with how real free-space-optical
pointing-acquisition-tracking (PAT) systems are actually built:

- **Two-stage PAT architecture.** Real FSOC terminals split pointing into
  a coarse stage (gimbal, wide field of view, camera/beacon feedback) and
  a fine stage (fast steering mirror, narrow field of view, quadrant
  detector), with reported accuracies around ±1-1.6 mrad (3σ) coarse and
  ±80 µrad (3σ) fine. Our `fine_stage_capture_range_urad` default (500
  µrad) sits between those two regimes -- a realistic coarse-to-fine
  handoff threshold, not an arbitrary number.
- **Pointing-loss formula.** `simulator/link_budget.py`'s
  `L_dB = 8.686 * (theta / theta_divergence)^2` is the standard Gaussian-
  beam boresight pointing-loss result used in deep-space and LEO optical
  link budgets, not an invented curve.
- **IMM tracking.** Interacting Multiple Model estimation is a
  well-established maneuvering-target-tracking technique from radar/
  missile-guidance practice, applied here to the coarse camera's centroid
  so one estimator robustly handles straight-line, turning, and erratic
  target motion.
- **Camera-based coarse centroiding.** DoG-filtered point-source
  detection + adaptive thresholding + intensity centroiding matches how
  real CCD-based coarse tracking assemblies extract a beacon position
  (reported figures: ~120 µrad accuracy at up to 100 FPS with ROI
  readout). Our 20 FPS floor is deliberately framed as a *minimum
  acceptable* threshold, not a target -- real coarse trackers commonly run
  well above it.

The 2s acquisition-time, 10px tracking-error, and 95% lock-retention
thresholds (Section 10) are reasonable engineering targets for this
project, not figures drawn from a specific paper -- worth being upfront
about that distinction if asked.

## Known characteristics / tuning notes

See `docs/technical_report.md` Sections 8-9 for the full writeup,
including three real bugs found and fixed during development (candidate-
count explosion under salt & pepper noise, a background-level bias that
broke the detector's noise estimate under Gaussian noise, and a lock-state
false-positive on noise blobs) -- summary:

- Default target spawn is bounded to a radius around screen centre (see
  comment in `simulator/scene.py`) rather than fully uniform across the
  2000x2000 canvas -- with the default narrow FOV (4x3 deg) and bounded
  PTZ slew rate (5 deg/s), a fully uniform spawn can start the target many
  seconds of physical slew away from the initial boresight, which makes
  the <=2s acquisition-time target physically unreachable regardless of
  detector/tracker quality. Set `target.initial_location` explicitly for
  wider-area search testing.
- Search: a fast outward spiral (`control/search_driver.py`) is used for
  the first 3s of searching and for re-acquisition; after 3s with no
  detection at all, it hands off to a raster sweep sized to guarantee full
  2000x2000-screen coverage as a bounded-worst-case fallback (~100s at the
  default 5 deg/s slew rate).
- The IMM's velocity and turn-rate are corrected once, from finite
  differences of the first few post-lock measurements, rather than left at
  zero -- this removes most of the tracking-error transient right after
  lock on fast-curving motion. Measured avg tracking error while locked is
  typically 1-5px across all four motion types; max error is typically
  under 15px with occasional spikes above 10px on aggressive figure-8
  curvature reversals (see technical report Section 5's documented
  residual limitation).
