# FSOC Coarse-Alignment Tracker

Software-only virtual camera tracking system for coarse pointing/acquisition/
tracking (PAT) of a simulated FSOC beacon, plus an identical pipeline path
for raw external `.mp4` video (Benchmark-2 style ingestion).

## Install

```
pip install -r requirements.txt
```

Requires Python 3.10+.

## Run the GUI

```
python main.py
```

Pick "Simulator" or "Load video file (.mp4)" in the config panel, adjust
parameters, and press Start.

## Run tests

```
pytest tests/test_motion_models.py tests/test_detector.py tests/test_imm_tracker.py tests/test_control_loop.py
python tests/benchmark_matrix.py   # Section 12 motion x disturbance matrix
python tests/smoke_test.py         # quick headless end-to-end check
```

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
  several dependencies rely on).

See `config/default_config.yaml` for every configurable parameter and its
default, and `docs/` for the technical report and user manual outlines.

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
