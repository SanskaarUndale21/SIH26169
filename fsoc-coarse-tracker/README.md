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

## Known characteristics / tuning notes

- Default target spawn is bounded to a radius around screen centre (see
  comment in `simulator/scene.py`) rather than fully uniform across the
  2000x2000 canvas -- with the default narrow FOV (4x3 deg) and bounded
  PTZ slew rate (5 deg/s), a fully uniform spawn can start the target many
  seconds of physical slew away from the initial boresight, which makes
  the <=2s acquisition-time target physically unreachable regardless of
  detector/tracker quality. Set `target.initial_location` explicitly for
  wider-area search testing.
- Search behaviour: an outward spiral (`control/search_driver.py`) is used
  for both first acquisition and re-acquisition; a raster sweep is also
  implemented and available if a deployment's spawn distribution needs
  exhaustive full-range coverage instead.
- The IMM's turn-rate (CT model) and velocity are seeded from finite
  differences of the first 2-3 raw detections rather than zero, to avoid a
  multi-frame tracking-error transient right after lock on fast-curving
  motion. Residual transient spikes above the 10px target can still occur
  in the first few frames after lock on aggressive circular/figure-8
  motion; see the technical report's performance analysis for measured
  numbers against the Section 12 test matrix.
