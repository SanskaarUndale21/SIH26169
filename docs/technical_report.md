# Technical Report: AI-Based Virtual Camera Tracking System for FSOC Coarse Alignment

## 1. Problem understanding

Free Space Optical Communication (FSOC) links a laser beam between two
mobile terminals instead of an RF signal. The beam is extremely narrow, so
Pointing, Acquisition and Tracking (PAT) is split into two stages:

- **Coarse alignment** (this project): a wide-FOV camera on a pan-tilt
  mount finds the remote terminal's beacon and keeps it in-FOV while both
  platforms move.
- **Fine alignment** (out of scope): once the beacon is centred to camera
  resolution, a separate high-precision optical system takes over.

This system replaces the physical camera/gimbal/beacon with a fully
virtual simulation, so the coarse-alignment algorithm (detection, tracking,
control) can be developed and benchmarked without hardware.

This split matches how real FSOC terminals are actually built: coarse
pointing assemblies (gimbal + wide-FOV camera/beacon feedback) commonly
report accuracy near 1-1.6 mrad (3-sigma), handing off to a fine pointing
assembly (fast steering mirror + quadrant detector) reporting accuracy
near 80 microrad (3-sigma). This project's `fine_stage_capture_range_urad`
default (500 microrad) is set between those two regimes -- a realistic
coarse-to-fine handoff threshold, not an arbitrary number. See the README
"How this matches real FSOC/PAT practice" section for the rest of the
literature grounding (pointing-loss formula, IMM usage, coarse centroiding
practice).

## 2. System architecture

Three modules, connected only through two narrow interfaces:

```
Simulator --Frame--> Perception+Tracking --Telemetry--> Control+GUI
                                                              |
                                          pan/tilt feedback --+
                                          (from Control, not Simulator)
```

- **`FrameSource`** (`perception/frame_source.py`): a `Frame` (image,
  timestamp, frame_id, optional fov_deg) is produced by either
  `SimulatorFrameSource` (wraps the virtual scene/camera/PTZ) or
  `VideoFileFrameSource` (reads a raw `.mp4`, `fov_deg=None`).
  Perception+Tracking imports neither `simulator` internals nor anything
  video-specific -- it only depends on `Frame`.
- **`Telemetry`** (`perception/pipeline.py`): frame_id, timestamp,
  detected, centroid_px, predicted_px, confidence, lock_state,
  pointing_command_deg.

This split is what makes Benchmark-2 (raw `.mp4` in, bypassing the
simulator/PTZ entirely) run the *identical* detector + IMM tracker + lock-
state-machine code that Benchmark-1 (simulator scenarios) runs. Verified
directly: `perception/pipeline.py`'s `PerceptionTrackingPipeline` is
constructed and driven the same way in `control/run_loop.py` regardless of
which `FrameSource` implementation is passed in.

`control/stepper.py`'s `PointingStepper` is the one place that turns
`Telemetry` into a pan/tilt rate command; it is shared verbatim between the
headless `TrackingRunner` (tests, benchmark matrix) and the Qt GUI's
per-frame `step()`, so both entry points drive the PTZ identically.

## 3. GUI, parameter schema, and the web control surface

### 3.1 One parameter schema, two UIs

Every tweakable simulation parameter (63 total: screen size, camera FOV/
resolution, target shape/size/location, each of the four motion types'
own speed/radius/period parameters, PTZ speed limits, every disturbance's
intensity including structured jitter and physically-derived turbulence,
detector thresholds, IMM process/measurement noise, PID gains, link
budget, scenario presets, target count) is declared exactly once in
`config/param_schema.py` as a `Param(path, label, group, kind, ...)`
entry. Both the desktop GUI's `gui/config_panel.py` and the web control
page's `web/control_page.py` build their forms by walking this same list
-- there is no second, hand-maintained parameter list in either UI that
could silently expose a different knob set or drift out of sync with
what the engine actually reads. `resolve_ui_values()` /
`flatten_config_to_ui_values()` convert between the flat `{path: value}`
map either UI's widgets produce and the real nested config dict
`Scene.from_config` etc. expect; this round-trip is covered by direct
testing (build a config, flatten it, resolve it back, and diff against
the original).

### 3.2 Desktop GUI (`gui/`)

`gui/main_window.py` wires the config panel to a `FrameSource`
(`SimulatorFrameSource` or `VideoFileFrameSource`) to the same
`PerceptionTrackingPipeline` + `PointingStepper` the headless runner
uses, to three output panels:

- `video_panel.py`: the live camera feed with a lock-state-coloured
  border and detection/prediction markers.
- `dashboard_panel.py`: tracking-error/FPS/lock-state plots plus
  colour-coded metric cards (green/red against the Section 11
  thresholds) -- replacing an earlier version of this panel that only
  dumped the raw metrics dict as text.
- `view3d_panel.py`: a live `pyqtgraph.opengl` 3D view of the real PAT
  geometry (Section 3.4).

### 3.3 Web dashboard and live control (`web/`)

A second, independent front-end onto the *same* real engine, not a
reimplementation:

- `web/dashboard_server.py` (FastAPI) serves both the results-browsing
  page (`/`, reads only `logs/*.json` and `*_frames.jsonl`) and the live
  control page (`/control`).
- `web/live_engine.py`'s `LiveEngine` runs a real `TrackingRunner` in a
  background thread so `/control` can Start/Stop/configure an actual
  simulation run from the browser -- the identical engine code
  `gui/main_window.py` drives. Only one run is live per server process
  at a time (a second start attempt while one is active gets an HTTP 409,
  verified directly against the running server); this matches "one
  simulation engine," not two that could disagree.
- `/api/config/schema` serves `config/param_schema.py`'s parameter list
  as JSON, so `web/control_page.py`'s JS builds the identical form the
  desktop GUI shows, from the same source.
- `/ws/live` streams real per-frame telemetry (the same `FrameRecord`
  schema as the `.jsonl` replay files, Section 3.4) plus periodic status/
  metrics as a live run progresses.
- This is a deliberate scope change from an earlier version of this
  project, where the web page was kept strictly read-only and imported
  nothing from `simulator/perception/control` specifically so it could
  never affect a judged run. That guarantee is explicitly given up now
  that the product includes a genuine live web engine; `/view/{name}`
  and `/api/runs/*` (pure log readers) still carry no such coupling.

### 3.4 Real per-frame telemetry and the two 3D views

`perf_logging/frame_log.py`'s `FrameRecord` captures one real record per
frame: detected/predicted position, lock state, confidence, pointing
command, and -- only when a real camera model exists for this run --
`fov_deg`, `cam_pan_deg`/`cam_tilt_deg` (derived directly from the
`CameraModel`'s own `world_x`/`world_y` state, never fabricated for
display), and the simulator's real ground-truth target position(s). This
is written as `<run_name>_frames.jsonl` alongside the existing summary
`.json`/`.csv`, and is what both 3D views consume:

- `gui/view3d_panel.py` (`pyqtgraph.opengl`, live) and
  `web/static/pat_scene.js` (Three.js, used by both the static replay
  page and the live-control page) draw a cone for the camera's real
  pointing direction, a dot for the real ground truth, and a dot for the
  tracker's own belief (`predicted_px` converted back to an absolute
  angle by adding the camera's current pan/tilt) -- with motion trails
  for the first two. The pan/tilt-to-3D-point conversion was verified
  numerically identical between the Python and JavaScript
  implementations (same formula, floating-point-identical output for
  matched inputs), so the two independent renderers can't silently show
  different geometry for the same recorded data.
- A fixed display range turns pure angles into a 3D point purely so
  there's something to plot -- this simulator is 2D and does not model
  true 3D distance; both views label this explicitly rather than
  implying a measured range.
- In raw-video (Benchmark-2) mode there is no camera model and therefore
  no real pan/tilt to plot; the desktop panel shows an explicit "3D view
  unavailable" placeholder and the web replay/live view returns 404 for
  that run's frames endpoint, rather than either one fabricating a scene.

## 4. Simulator design

### 4.1 Target motion models (`simulator/target_motion.py`)

- **Straight line**: `x(t)=x0+vx*t`, `y(t)=y0+vy*t`, triangle-wave
  reflection at the screen bounds.
- **Circular**: `x(t)=cx+r*cos(wt)`, `y(t)=cy+r*sin(wt)`.
- **Figure-8**: Lissajous with a 1:2 frequency ratio,
  `x(t)=cx+A*sin(wt)`, `y(t)=cy+B*sin(2wt)`.
- **Random walk**: Ornstein-Uhlenbeck-smoothed heading (`heading +=
  N(0, theta_std^2 * dt)`), integrated into position; reflects at bounds.
- **Spiral** (optional/stretch): `r(t)=r0+k*t` combined with circular angle.

### 4.2 Camera model (`simulator/camera_model.py`)

Linear small-angle FOV-to-pixel mapping, as the spec explicitly allows for
a simulation: the world offset from the camera boresight is converted to
degrees via a configurable `world_px_per_deg` scale, then to pixels via
`px_per_deg = W_cam / fov_x_deg`. `PTZActuator.step()` clamps the commanded
pan/tilt rate to `max_pan/tilt_speed_deg_s` before integrating -- this
clamp is what makes "just point directly at the target" an insufficient
controller under fast motion (Section 7).

### 4.3 Disturbances (`simulator/disturbances.py`)

Salt & pepper, Gaussian, and Poisson noise; camera jitter (random per-frame
pixel shift); atmospheric presets (clear/haze/fog/rain/low-light as
contrast+brightness transforms, rain adds streak overlay); platform motion
drift (moves the boresight itself, stacking on top of PTZ commands); and a
Kolmogorov/von-Karman turbulence phase-screen model (FFT-synthesized
random phase screen, PSD `Phi(f) ~ 0.023 * r0^(-5/3) * f^(-11/3)`, applied
as a spatial warp via `cv2.remap` plus mild intensity scintillation).

**Rendered background level**: the pre-disturbance image starts from a
configurable `background_level` (default 20), not pure 0. This matters:
additive Gaussian noise on a 0 background, clipped to `uint8`, produces a
*half-Gaussian* (all negative excursions clip to 0), which biased the
detector's robust background estimator toward reading near-zero noise even
when real injected sigma was large (see Section 10.2's writeup of this bug).
A nonzero floor -- realistic anyway, since real FPA sensors have a dark
current/bias level -- keeps the noise distribution symmetric.

## 5. Detection method (`perception/detector.py`)

1. **3x3 median pre-filter.** Standard defense against impulsive salt &
   pepper noise: kills isolated 1-2px outliers while leaving a real 5-20px
   target blob intact. Added after discovering it was load-bearing for
   both accuracy and throughput (Section 10.1).
2. **Robust background stats**: median + MAD (scaled 1.4826x for a
   Gaussian-equivalent sigma) computed on a strided (every 4th pixel)
   subsample for speed.
3. **DoG (Difference of Gaussians)**: `G(sigma1)*I - G(sigma2)*I`,
   sigma1=1.0, sigma2=3.0 by default, tuned to the target's expected scale.
4. **Adaptive threshold**: `DoG > k * sigma_local`, k=4.0 by default.
5. **Connected components**, filtered by area. The min/max area window is
   derived from the configured `target.size_px` (a known parameter, not
   something to discover) -- `[0.35, 3.0] * nominal_area` by default --
   rather than a fixed generic range. This was a second load-bearing fix
   (Section 10.2): a generic 4-400px window let enough noise-sized blobs
   through under salt & pepper / Gaussian noise to occasionally satisfy
   the lock-state machine's confirm-frames requirement on pure noise.
6. **Intensity-weighted centroid** over the surviving blob's pixels, for
   sub-pixel accuracy.
7. **Gating**: candidates are matched against the IMM's current prediction
   (tight 60px gate) whenever a track exists at all (acquiring, locked, or
   reacquiring) -- not just once "locked". An earlier version gated loosely
   throughout "acquiring", which let the confirm-frames counter advance on
   a *different* noise blob each frame instead of the same physical target.

## 6. Tracking method: IMM (`perception/imm_tracker.py`)

Three models sharing a common 5-state `[x, y, vx, vy, omega]` (a documented
simplification -- see the module's docstring -- that keeps mixing/
combination plain linear algebra instead of the heavier variable-dimension
IMM formulation):

- **CV** (constant velocity): best for straight-line motion.
- **CT** (nearly-constant-turn, Bar-Shalom's standard linearized model):
  best for circular motion, and reduces to CV as omega->0.
- **RW** (high process noise "catch-all"): best for random/erratic motion.

Standard IMM cycle each frame: mixing (blend prior states by mode-
transition probabilities), per-model Kalman predict+update (skipping the
correction on a missed detection), mode-probability update from each
model's measurement likelihood, and probability-weighted combination for
the reported position/velocity.

**Convergence-lag fix**: rather than seed every new track at zero velocity
and omega (which produced a large, multi-frame tracking-error transient
right after lock on fast/curving motion), the pipeline keeps a short
pre-lock history of raw detections and seeds the IMM's initial velocity
(2-point finite difference) and turn-rate (3-point, via the signed angle
between two consecutive velocity vectors) directly. When the seed data
shows real curvature (|omega| > ~8.6 deg/s), the initial mode
probabilities are also biased toward CT (0.70) instead of uniform 1/3-1/3-
1/3, since a uniform blend still drags the *combined* estimate off a curve
even when CT's own state is seeded correctly.

**Why IMM over a single Kalman filter**: a fixed constant-velocity filter
lags badly on circular/figure-8 motion; a fixed constant-turn filter drifts
on straight-line motion (or over/undershoots at curvature reversals, e.g.
figure-8's crossing point). The tracker is never told which motion type is
active, so a blend that adapts online is required.

**Known residual limitation**: figure-8 motion's periodic curvature-sign
reversal is the hardest case for this model set -- a single CT model's
omega estimate necessarily lags at each reversal, producing transient
tracking-error spikes larger than seen on pure circular motion. This is
documented rather than fully eliminated; see Section 11 for measured
numbers and Section 14 for a proposed fix (a second CT model for the
opposite turn sign, or an explicit curvature-reversal detector).

## 7. Control method (`control/pid_controller.py`, `control/stepper.py`)

Per-axis PID on the pixel error converted to degrees:
`pan_rate_cmd = Kp*err_deg + Ki*int(err_deg) + Kd*d(err_deg)/dt`, clamped
to `+-MAX_PAN/TILT_SPEED` with anti-windup (integral term clamped so it
alone can't exceed the speed limit). Default gains (Kp=2.5, Ki=0.15,
Kd=0.35) were hand-tuned against the simulator's own motion models to
minimize steady-state error without oscillation, given the actuator speed
clamp -- documented as a reasonable choice, not a formally optimized one
(the spec explicitly allows this: "make a reasonable choice, document the
reasoning").

`PointingStepper` switches between three regimes based on `lock_state`:
PID while `locked`/`acquiring`; an outward spiral search
(`control/search_driver.py`'s `SpiralSweepDriver`) while `reacquiring`,
centred on the IMM's last known position; and a **hybrid** search while
`searching` with no track at all -- the same spiral for the first 3
seconds (fast for the common case: target within a few degrees of the
initial boresight, see Section 9's spawn-radius note), then a handoff to a
`RasterSweepDriver` sized to guarantee full-screen coverage as a bounded-
worst-case fallback.

## 8. Re-acquisition strategy (`perception/lock_state.py`)

States: `searching -> acquiring -> locked -> reacquiring -> (locked |
searching)`. `acquiring` requires 8 consecutive *spatially consistent* raw
detections (max implied speed 200px/s between consecutive pre-lock points,
generous above the fastest default motion's ~90px/s but well below what
spatially clustered noise near a slowly-moving search probe could
otherwise satisfy) before confirming `locked` -- raised from an initial 4
after discovering that a looser requirement let salt & pepper / Gaussian
noise conditions occasionally confirm a false lock onto noise within a few
frames (Section 10.2). `locked` drops to `reacquiring` on the very next
missed detection; `reacquiring` falls back to `searching` after
`reacquire_timeout_frames` (30 by default) with no re-detection.

## 9. Known characteristics / honest limitations

- **Acquisition time (<=2s spec)**: reliably met when the target spawns
  within the default bounded radius (15% of screen extent) of the initial
  boresight -- the common case, and the one exercised by
  `tests/smoke_test.py`. A target that spawns (or drifts, for fast
  straight-line motion) far from the search path can take substantially
  longer, bounded above by the raster fallback's full-coverage time
  (~100s at the default 5 deg/s slew rate over a 2000x2000 screen). This
  is a physical consequence of narrow FOV (4x3 deg) + bounded slew rate +
  large screen, not a software defect -- see Section 11 for the actual
  matrix results this produces.
- **Tracking error (<=10px while locked)**: reliably met on average
  (typically 1-5px) across all four motion types once locked. Transient
  spikes above 10px can still occur in the first few frames after lock on
  fast circular motion, and more persistently on figure-8's curvature
  reversals (Section 6's residual limitation).
- **Turbulence** is real-time-costly (~90ms/frame at 640x480, ~11 FPS
  alone) and is documented as an offline/demo differentiator, not
  something to run continuously during a benchmarked pass.
- **CNN false-positive filter** (Section 8.4, `perception/cnn_filter.py`)
  is implemented, integrates as an additive gate with a verified graceful
  fallback (missing/failed model -> classical-only, never raises), and was
  validated end-to-end with a hand-trained model. The bundled/documented
  training pipeline (`generate_training_labels` from simulator ground
  truth) is functional but was only exercised with a small ad-hoc dataset
  in this session -- not tuned or validated as a real accuracy
  improvement. It ships disabled by default and its removal changes
  nothing else in the pipeline.

## 10. Debugging notes worth reporting as findings

### 10.1 Salt & pepper noise without a median pre-filter

At the spec's ~10% salt & pepper density, DoG's sigma1=1px scale meant
isolated noise pixels produced a DoG response comparable to a real point
source. Without a median pre-filter, this produced 2000-4000 candidate
blobs per frame, which both (a) made centroiding/candidate-selection cost
dominate the frame budget (measured ~300ms/frame, ~3 FPS, versus a 20 FPS
target) and (b) periodically fed a plausible-looking "detection" into the
lock-state machine. A 3x3 median filter, applied unconditionally before
DoG, cut this to single digits of candidates per frame (~7ms/frame) with
no measurable cost on the clean-image case.

### 10.2 Gaussian noise on a zero background biasing the robust estimator

With the rendered background at pure 0, `img + N(0, sigma)` clipped to
`uint8` is a half-Gaussian: essentially every pixel that would go negative
clips to exactly 0. The detector's median/MAD background estimator reads
this distribution as having near-zero spread (median=0, most values
exactly 0), so the adaptive threshold `k * sigma_local` came out near zero
regardless of the actual injected sigma -- letting thousands of noise
excursions past threshold. Symptom: catastrophic tracking error (300-700px
average) and FPS collapse (~2 FPS) specifically under the Gaussian-noise
disturbance condition, while other conditions looked fine. Fixed by giving
the rendered image a nonzero background floor (`background_level`,
default 20) before any noise injection -- also more physically realistic,
since real FPA sensors have a nonzero dark-current/bias level.

### 10.3 Confirm-frames requirement satisfied by unrelated noise blobs

The lock-state machine's `acquiring -> locked` transition originally only
checked "was *some* candidate selected N frames in a row" -- with the
search gate wide open (whole-frame) throughout `acquiring` (since no track
existed yet to gate against), a different noise blob each frame, each
merely nearest to a slowly-moving search probe point, could satisfy this.
Symptom: under salt & pepper noise, the system reported `locked` within
0.1-0.2s even when the real target's ground truth was never in the
camera's FOV during the entire run (tracking-error fields silently read
`None` since ground truth was never available to compare against, which is
what made this easy to miss initially). Fixed with three changes together:
(1) gate tightly around the IMM's prediction as soon as *any* track exists,
not only once `locked`; (2) require pre-lock raw detections to be
spatially continuous (implied speed < 200px/s between consecutive points,
history resets otherwise); (3) tie the detector's blob-size filter to the
configured target size instead of a generic range, and raise
`confirm_frames` from 4 to 8 for margin. Verified fixed: the previously
"instant false lock" scenarios now correctly report no lock at all when
the target genuinely never entered FOV within the test window.

### 10.4 Jitter's ground truth not accounting for the jitter shift itself

Camera jitter (`apply_jitter`) shifts the *rendered image content* by a
random `(dx, dy)` each frame to simulate sensor-level vibration. The
Simulator's ground-truth position (used only for the Simulator's own
`avg/max_tracking_error_px` logging, never fed to Perception+Tracking) was
computed *before* that shift was applied, so it silently disagreed with
where the target actually appeared in the image the detector saw --
producing a spurious tracking-error reading up to the jitter magnitude
(~20px) even when the detector correctly found the target exactly where
it was drawn. Fixed by shifting the reported ground-truth position by the
same `(dx, dy)` the renderer actually applied. Residual jitter tracking
error (Section 11) after this fix is real, not a bookkeeping artifact: a
true per-frame random jump is inherently harder for any smooth-motion
model to predict than the four smooth target-motion types themselves.

## 11. Test methodology and performance analysis

`tests/benchmark_matrix.py` crosses the 4 mandatory motion types against
10 disturbance conditions (clean, salt & pepper, Gaussian, Poisson,
jitter, haze, fog, rain, low light, platform motion, all-combined),
running each for a fixed frame budget (300 frames, seed 42) and checking
the Section 11 thresholds.

**Measurement caveat on FPS**: the matrix runs all 40 scenarios back to
back in one long-lived Python process. The reported `fps` column (wall-
clock frames/second for that scenario) reads noticeably lower there
(~35-55 FPS on "clean") than the same scenario run in isolation
(~130-150 FPS, `processing_time_per_frame_ms` ~7ms) -- this is sustained-
run/shared-machine overhead accumulating across 40 sequential scenarios
in one process, not a per-scenario regression; `processing_time_per_frame_ms`
(reported per scenario in the JSON/CSV log, not the summary table) is the
more reliable per-frame cost figure. Even with that overhead, every
condition except Poisson-with-other-load cleared 20 FPS; Poisson alone in
isolation measures 28-37 FPS.

Representative results (4 motions x 10 conditions, 300 frames/10s each,
seed 42):

| Condition | avg tracking error (px) | max tracking error (px) | notes |
|---|---|---|---|
| clean | 1.7-2.4 | 8.6-11.2 | acquisition 3.5-4.6s in this fixed-seed run (see Sec. 8) |
| salt & pepper | 0.85 (when locked) | 19.3 (circular) | lock_retention 0.83-0.92 -- flickers in/out rather than a stable false lock, see Sec. 9.3 |
| Gaussian | 1.7-2.3 | 8.6-11.2 | matches clean closely once the Sec. 9.2 fix was applied |
| Poisson | 1.6-2.4 | 8.6-11.2 | matches clean; FPS is the tightest margin (see caveat above) |
| jitter | 8.1-9.9 | 23.0-31.7 | genuinely harder: jitter is a true per-frame random shift (non-smooth by design), which the IMM's smooth-motion models cannot predict away -- ground-truth is jitter-compensated (Sec. 9.4) so this reflects real residual tracking lag against a target that jumps unpredictably every frame |
| haze/fog/rain/low_light | 1.7-2.4 | 8.6-11.2 | matches clean -- atmosphere presets affect contrast/brightness, not candidate count, so no accuracy impact given the adaptive threshold |
| platform_motion | 1.8-2.2 | 9.1-11.0 | small increase over clean from the added boresight drift |
| all_combined | 5.5-6.5 (locked cases) | 19.6-22.2 | stacks salt&pepper + Gaussian + jitter + fog + platform motion; acquisition frequently exceeds the 300-frame budget |

Acquisition time in this fixed-seed (42), fixed-duration (10s) matrix run
is often >2s or "never within budget" for non-noisy conditions -- this is
the spawn-distance effect documented in Section 9, not a detection/tracking
failure: the same pipeline acquires in 0.1-0.9s when the target starts
near the boresight (see `tests/smoke_test.py`'s varied-seed results, e.g.
seed 7/figure8 acquired in 0.67-0.87s, seed 99/figure8 in 0.63-0.67s).
Interestingly, salt & pepper and Gaussian conditions in *this* matrix run
show *faster* apparent acquisition (1.6s) than clean (3.5-4.6s) for the
same seed -- because noise-driven detections near the search path can
occasionally supply the third consistency-building detection sooner, not
because noise helps tracking; this is a fixed-seed-and-duration artifact
of the test harness, not a claim that noise improves acquisition.

## 12. Space-science relevance additions

Tracking accuracy in pixels is an implementation detail; what actually
matters for FSOC is what that error costs the *link*. This section adds
the pieces that connect the two, and moves scenario parameters from
"picked to look reasonable on screen" to "derived from real orbital
mechanics / atmospheric optics."

### 12.1 Link-margin translation (`simulator/link_budget.py`)

Every run now additionally reports, wherever camera FOV is known
(simulator mode; not meaningful for a raw benchmark video with no FOV
metadata):

- `avg/max_angular_error_urad` -- the pixel tracking error converted to
  microradians via the camera's own deg/pixel scale (co-boresighted
  assumption between the coarse camera and the laser).
- `avg/max_pointing_loss_db` -- that angular error's cost on the link, via
  the standard Gaussian-beam pointing-loss formula `L_dB = 8.686 *
  (theta/theta_div)^2` against the configured beam divergence
  (`link_budget.beam_divergence_urad`), clamped at 60dB so an
  already-enormous loss doesn't report a meaningless four-digit number.
- `handoff_ready_rate` / `time_to_handoff_ready_sec` -- the fraction of
  locked time (and time to first reach) the coarse-pointing error dropping
  inside `link_budget.fine_stage_capture_range_urad`, i.e. the actual
  criterion for handing off to the fine-pointing stage this project
  explicitly stops short of building (Section 1). This directly answers
  "what happens right after coarse alignment succeeds" -- a question this
  scope naturally invites.

### 12.2 Physically-derived turbulence strength

`simulator/link_budget.py`'s `compute_fried_parameter` integrates the
Hufnagel-Valley 5/7 Cn^2(h) profile (the standard atmospheric-optics
turbulence model) along a slant path set by wavelength, path altitude and
zenith angle, producing a real Fried parameter r0 (metres) instead of an
arbitrary tuning constant. `fried_parameter_pixel_equivalent` converts
that to the pixel-space r0 the existing Kolmogorov-phase-screen turbulence
model (`simulator/disturbances.py`) consumes, via the seeing-angle
relation `angular_seeing ~= wavelength/r0`. Enabled per-scenario with
`disturbances.turbulence.physical: true`.

### 12.3 Orbital-mechanics-derived scenario presets (`simulator/orbital.py`, `simulator/scenario_presets.py`)

Three named scenarios, selectable via `scenario_preset` in config (or the
GUI's scenario dropdown), each deriving its target-motion parameters from
real orbital formulas rather than a hand-picked radius/speed:

- **`leo_leo_crosslink`**: two ~500km-altitude LEO satellites at a given
  crosslink range and relative inclination; relative LOS angular rate via
  `2*v_orbital*sin(di/2) / range`, modeled as straight-line motion at that
  derived speed.
- **`leo_ground_downlink`**: a ground station tracking a LEO satellite's
  overhead pass; peak angular rate `v_orbital / altitude` at zenith
  crossing, modeled as circular motion with that peak tangential speed.
- **`geo_ground`**: a GEO satellite's residual station-keeping drift
  (typically +-0.05deg box) -- angular rate ~6 orders of magnitude below
  LEO, i.e. effectively stationary; the real tracking challenge here is
  rejecting jitter/atmosphere, not chasing motion, which is realistic.

Every preset also sets scenario-appropriate `link_budget` values (range,
wavelength) so the pointing-loss/handoff numbers above mean something
concrete for that scenario. `cfg["_scenario_derivation"]` carries a
one-line trace of the formula used, for the demo/report to quote directly
rather than asserting the numbers are realistic.

### 12.4 Structured (resonant) platform jitter

Real spacecraft jitter is not spectrally flat -- reaction wheels and other
rotating/reciprocating mechanisms impose narrow-band vibration at their
operating frequency. `simulator/disturbances.py`'s `StructuredJitterModel`
drives a per-axis damped second-order resonant filter with white noise,
producing displacement with a PSD peak at a configurable
`resonance_hz` instead of independent uniform-random per-frame
displacement -- closer to what an ADCS/pointing engineer would actually
simulate for a reaction-wheel-induced disturbance. Enabled per-scenario
with `disturbances.jitter.structured: true`; the original uniform-random
model remains the default (matches the spec's literal "up to +-20px/frame"
wording) and is unaffected when this is off.

## 13. Innovation/novelty summary

- Physically-grounded Kolmogorov/von-Karman turbulence model (FFT phase
  screen from the real PSD, not a generic blur), with its strength now
  optionally derived from a real Hufnagel-Valley Cn^2 integration rather
  than picked by hand (Section 12.2).
- Link-margin translation and PAT handoff-readiness reporting (Section
  12.1) -- ties the graded tracking-error metric to what it actually
  costs the communication link, and to the real coarse-to-fine handoff
  criterion this project's scope stops short of building.
- Orbital-mechanics-derived scenario presets (Section 12.3): LEO-LEO
  crosslink, LEO-ground downlink, and GEO-ground scenarios whose motion
  parameters trace back to actual orbital velocity/geometry formulas.
- IMM with finite-difference velocity/turn-rate seeding and curvature-
  aware initial mode-probability biasing, specifically to remove the
  post-lock convergence lag that a naive zero-initialized IMM shows on
  fast curving motion.
- Hybrid spiral-then-raster search: fast average-case acquisition via an
  outward spiral, with a raster fallback that provides a genuine bounded-
  worst-case full-screen coverage guarantee.
- Structured (resonant) platform jitter model (Section 12.4), closer to
  real reaction-wheel-induced vibration than flat random noise.
- Shared `PointingStepper` control core used identically by the headless
  runner and the Qt GUI, so there is exactly one implementation of the
  search/PID state machine to reason about and fix.
- A single parameter schema (Section 3.1) driving both the desktop GUI
  and a genuine live web control surface, plus two independent 3D PAT
  visualizations (OpenGL and Three.js, verified geometrically identical)
  that only ever draw real recorded/streamed data -- never a fabricated
  scene, with both explicitly declining to render one when a run has no
  real camera-model geometry to plot (Section 3.4).
- A real live-run web engine (Section 3.3) rather than a static/read-only
  dashboard: `/control` runs the same `TrackingRunner` the desktop app
  does, in a background thread, with its telemetry streamed live over a
  WebSocket -- verified end-to-end against the running server, not just
  unit-tested in isolation.

## 14. Future improvements

- A second CT model (or explicit sign-of-curvature detection) to remove
  the residual figure-8 curvature-reversal tracking-error spike.
- Cache/evolve the turbulence phase screen across frames instead of
  resynthesizing from scratch each frame, to make it real-time-viable.
- Train the CNN false-positive filter on a properly balanced, larger
  simulator-generated dataset across all disturbance conditions, and
  measure its actual effect on precision/recall versus classical-only.
- Multi-target data association (the spec marks this optional; the
  current gating logic assumes one target of interest).
- A jitter-aware prediction term (predicting "expect a random per-frame
  offset" rather than trying to smooth through it) to reduce the residual
  jitter tracking error documented in Sections 9.4/10.
- `tests/benchmark_matrix.py` currently runs all 40 scenarios sequentially
  in one process; its reported FPS column reads lower than a scenario's
  true per-frame cost because of accumulated overhead across the run
  (Section 11's measurement caveat). Running each scenario in a fresh
  subprocess (or reporting `processing_time_per_frame_ms` instead of
  wall-clock FPS in the summary table) would give a cleaner comparison.
- Full 3D orbital geometry (SGP4 propagation) instead of Section 12.3's
  closed-form peak-rate approximations, for a pass profile that eases in
  from the horizon rather than only matching the zenith-crossing peak.
- Cache/evolve the turbulence phase screen across frames (already noted
  above) would also make `turbulence.physical: true` viable in real time,
  since the physically-derived r0 tends toward the stronger-turbulence
  end of the model's range for slant paths.
