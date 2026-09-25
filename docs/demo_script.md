# Demo script (SIH-style live judging)

A run-of-show for presenting this project to a panel, plus the likely
technical questions and where the honest answer lives in this repo. Keep
this open on a second screen during the demo, don't read from it live.

## 1. 60-second framing (say this before touching the keyboard)

"This is a coarse-alignment pointing-acquisition-tracking system for
mobile FSOC terminals. It's the coarse stage of a real two-stage PAT
architecture -- wide field of view, camera-based centroid tracking, PID-
driven gimbal -- that hands off to a fine-pointing stage once the target
is within capture range. Everything you'll see is a real simulation
engine and a real live control loop, not a scripted animation: the same
`TrackingRunner` class drives both the desktop app and the web dashboard."

## 2. Live demo order

1. **Open the desktop GUI** (`python main.py`). Point out the sidebar:
   74 real tunable parameters (scene, camera, target motion, disturbances,
   detector, IMM tracker, PID, link budget), all read from one shared
   schema (`config/param_schema.py`) so the web UI can never drift out of
   sync with it.
2. **Start a clean run** (straight-line motion, no disturbances). Narrate
   the lock-state colours as they change: red = searching, yellow =
   acquiring/re-acquiring, green = locked. Point at the 3D view tab --
   the cone is the camera's real boresight direction, not a decoration.
3. **Stop, then start a harder run**: switch motion to `figure8`, turn on
   jitter + turbulence. Show the tracking-error chart holding under the
   10px line and the FPS chart holding above 20 -- these are the Section
   10 pass/fail thresholds, colour-coded live on the metric cards.
4. **Switch to the web console** (`python web/dashboard_server.py`,
   then `http://127.0.0.1:8420/`). Open **New run**, pick the "Heavy
   sensor noise" scenario, show the camera preview updating as you add
   fog, then **Start run**: the Live page streams the real camera feed
   with the tracker's crosshair on the beacon. Stop and save, then open
   the report: scorecard, error chart, centroid log CSV, 3D replay. Finish
   on **Spec check**, which maps every problem-statement line to what the
   system does.
5. **If asked "does it handle real video?"** -- switch input source to
   "Load video file", pick a `.mp4`, and run it: same pipeline, no camera
   model/PTZ geometry (so the 3D view honestly shows "unavailable" instead
   of faking it).
6. **Close on the link-budget numbers**: point at "avg pointing loss (dB)"
   and "handoff-ready rate" on the metric cards -- this is the tracking
   error converted into what it actually costs the optical link, and
   whether the fine-pointing stage could take over right now.

## 3. Likely panel questions and where the real answer is

- **"Is this real physics or just numbers you picked?"** -- Pointing loss
  is the standard Gaussian-beam boresight formula used in deep-space/LEO
  optical link budgets (`simulator/link_budget.py`); turbulence strength
  can be derived from a real Hufnagel-Valley Cn^2 integration instead of a
  hand-picked constant; the three scenario presets derive target motion
  from real orbital-mechanics formulas (`simulator/orbital.py`). See
  README "How this matches real FSOC/PAT practice".
- **"Why IMM instead of a simple Kalman filter?"** -- IMM is standard
  practice in radar/missile-guidance maneuvering-target tracking; it lets
  one estimator handle straight-line, turning, and erratic motion without
  manually switching models. Real FSOC coarse cameras more often use
  simpler filters -- frame this as a deliberate upgrade, not "how it's
  always done" (`docs/technical_report.md` Section 6).
- **"What happens if the target is lost completely?"** -- Hybrid spiral-
  then-raster search: fast outward spiral for the first 3s, then a raster
  sweep sized to guarantee full-screen coverage as a bounded worst case
  (`perception/lock_state.py`, `control/search_driver.py`, Section 8).
  `tests/test_robustness.py::test_target_never_detected` proves the engine
  survives a target that's never detectable for an entire run.
- **"What's your weakest point / biggest limitation?"** -- Be upfront:
  Section 9 of the technical report lists honest limitations (e.g. the
  2s/10px/95%-lock-retention Section 10 thresholds are engineering targets
  for this project, not figures drawn from a specific paper). Naming this
  unprompted reads better to a technical judge than being caught on it.
- **"Does the web version actually run the simulation, or is it just
  displaying the desktop app's output?"** -- It runs its own real
  `TrackingRunner` in a background thread (`web/live_engine.py`),
  independent of the desktop app; only one run can be live per server
  process at a time (enforced with an HTTP 409, not silently ignored).

## 4. Fallback plan if something breaks live

- **Camera/GPU issue on the demo machine**: fall back to the web console
  only (no OpenGL dependency) -- `python web/dashboard_server.py`, open
  `http://127.0.0.1:8420/setup` in any browser.
- **A run won't start / errors out**: reset to the default config
  (`config/default_config.yaml` has no disturbances enabled) and retry
  before touching anything else -- narrow down which slider caused it
  afterward, not during the demo.
- **No network / can't reach the web UI**: everything after step 1 above
  still works from the desktop GUI alone; skip step 4.
- Rehearse the "clean run" (step 2) enough that it never fails -- it's the
  one moment you cannot afford to debug live.
