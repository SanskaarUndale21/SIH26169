# User Manual: FSOC Coarse-Alignment Tracker

## 1. Installation

Requires Python 3.10+.

```
pip install -r requirements.txt
python main.py
```

This launches the desktop GUI. To also use the web dashboard/live-control
UI (Section 8), run `python web/dashboard_server.py` in a second terminal.

To build a standalone executable (no Python install required to run it):

```
pyinstaller fsoc-coarse-tracker.spec --noconfirm
```

The result is `dist/fsoc-coarse-tracker/fsoc-coarse-tracker.exe`. Run it
directly; it bundles its own Python runtime and dependencies (torch is
deliberately excluded from the packaged build -- see Section 9's note on
the optional CNN filter). The packaged exe covers the desktop GUI only;
the web dashboard is run from source (`python web/dashboard_server.py`)
since it's a Python-server component, not something PyInstaller packages.

## 2. Application overview

The desktop window has three panels:

- **Left**: configuration panel -- tabbed, one tab per parameter group
  (Scene, Camera, Target, one tab per motion type, PTZ, Noise, Jitter,
  Atmosphere, Turbulence, Platform Motion, Link Budget, Scenario Preset,
  Detector, IMM Tracker, PID Control). Every one of the 62 tweakable
  simulation parameters has a slider+spinbox (numeric), checkbox (bool),
  or dropdown (enum) here -- see Section 3.
- **Centre**: live video feed with detection/prediction overlay, and
  Start/Stop/Reset controls.
- **Right**: two tabs -- **2D Dashboard** (tracking-error/FPS/lock-state
  plots plus colour-coded metric cards) and **3D View** (a live OpenGL
  rendering of the actual pan/tilt geometry -- see Section 6).

The web dashboard (`http://127.0.0.1:8420/`, Section 8) is a second,
independent front-end onto the same real engine, reachable from a
browser: results browsing + 3D replay at `/`, and a full live-control
page (identical parameter set, Start/Stop, live 3D view + charts over a
WebSocket) at `/control`.

## 3. Parameter configuration guide

Every parameter is defined once in `config/param_schema.py` and both UIs
build their forms from that single list, so nothing is exposed in one UI
and missing from the other. Groups, by tab:

- **Scene**: screen width/height (world canvas the simulator renders on).
- **Camera**: resolution, horizontal/vertical FOV, update rate.
- **Target**: number of targets, shape, size, initial location, motion
  type (straight line / circular / figure-8 / random walk / spiral).
- **Motion: \<type\>**: each motion type's own parameters (speed/heading
  for straight line, radius/period for circular, amplitudes/period for
  figure-8, speed/heading-std for random walk) -- all four sets are kept
  live regardless of which motion type is currently selected, so you can
  tune one and switch to it later without losing the values.
- **PTZ**: max pan/tilt slew speed, update interval.
- **Noise**: salt & pepper (enable + amount), Gaussian (enable + sigma),
  Poisson shot noise (enable).
- **Jitter**: enable, max pixel amplitude, structured (resonant)
  jitter toggle + its resonance frequency.
- **Atmosphere**: clear / haze / fog / rain / low-light preset.
- **Turbulence**: enable, "derive r0 from real physics" toggle (Hufnagel-
  Valley Cn² integration) vs. manual Fried parameter, wavelength,
  path altitude, zenith angle.
- **Platform Motion**: enable, mode (linear/circular/random/spiral/
  figure-8), max per-frame drift.
- **Link Budget**: beam divergence, fine-stage capture range, wavelength,
  link range -- context for the angular-error/pointing-loss/handoff
  metrics (Section 7).
- **Scenario Preset**: none, or one of the orbital-mechanics-derived
  presets (LEO-LEO Crosslink, LEO-Ground Downlink, GEO-Ground) -- selecting
  one overrides Target motion + Link Budget with values traced back to
  real orbital formulas.
- **Detector**: DoG filter sigmas, adaptive-threshold k.
- **IMM Tracker**: per-model (CV/CT/random-walk) process noise,
  measurement noise, lock-confirm frame count, re-acquire timeout.
- **PID Control**: pan/tilt Kp/Ki/Kd.

## 4. Running a simulation scenario (desktop GUI)

1. Select "Simulator" as the input source (top of the config panel).
2. Adjust parameters across the tabs as needed.
3. Press **Start**. The video panel shows the live feed with a coloured
   border/marker: **red** = searching, **yellow** = acquiring or
   reacquiring, **green** = locked. The 3D View tab shows the real
   camera-pointing cone, the ground-truth target dot, and the tracker's
   own belief dot, all live.
4. Press **Stop** at any point -- the performance log and the per-frame
   trace are written automatically to `logs/` (Section 7).
5. **Reset** clears the run state without starting a new one.

## 5. Loading and running an external video file (desktop GUI)

1. Select "Load video file (.mp4)".
2. Click **Browse...** and pick a `.mp4` file.
3. Press **Start**. The identical detector + IMM tracker + lock-state
   machine runs against the raw video frames; there is no PTZ to drive
   (the video isn't steerable), so the pointing-command telemetry field
   stays at (0, 0). The **3D View** tab shows an explicit "3D view
   unavailable" message in this mode instead of a fake scene, since there
   is no real camera-model geometry to plot.
4. Ground-truth tracking error isn't computed in this mode (no simulator
   ground truth exists for a real video) -- `avg_tracking_error_px` /
   `max_tracking_error_px` in the log will be `null`; acquisition time,
   FPS, and lock-retention rate are still measured.

## 6. The 3D view

Both the desktop GUI's **3D View** tab and the web control page's live
3D panel draw the same real geometry, computed the same way (verified
byte-identical between the Python/OpenGL and JavaScript/Three.js
implementations):

- **Blue cone**: the camera's actual pan/tilt pointing direction this
  frame, derived from the simulator's own camera-model state (not a
  cosmetic animation).
- **Green dot + trail**: the simulator's real ground-truth target
  position.
- **Yellow dot**: the tracker's own belief (its `predicted_px` output,
  converted back to an absolute angle) -- the visual gap between yellow
  and green is the actual tracking error.
- Cone colour follows lock state (red/yellow/green, same convention as
  the 2D video overlay).
- Positions are drawn at a fixed display range purely so an angle has
  somewhere to be plotted -- this simulator is 2D and does not model true
  3D range; the panel/page both note this explicitly.
- In raw-video mode, the 3D view is unavailable (Section 5) rather than
  fabricated.

## 7. Reading the dashboard and the generated performance log

Dashboard plots and metric cards update every frame while running, colour-
coded against the Section 10 hard performance targets (green = meets the
threshold, red = doesn't). On **Stop**, three files are written to
`logs/run_<timestamp>.*`:

- `.json` / `.csv`: the run summary -- `simulation_duration_sec`, `fps`,
  `acquisition_time_sec`, `avg_tracking_error_px`, `max_tracking_error_px`,
  `lock_retention_rate`, `processing_time_per_frame_ms`, `rmse_px`,
  `re_acquisition_count`, `re_acquisition_times_sec`, `target_loss_events`,
  plus the link-budget additions `avg/max_angular_error_urad`,
  `avg/max_pointing_loss_db`, `handoff_ready_rate`,
  `time_to_handoff_ready_sec`.
- `_frames.jsonl`: the real per-frame trace (one JSON object per line)
  used by both 3D views -- detected/predicted position, lock state, real
  camera pan/tilt, ground truth. Absent for raw-video runs (no camera
  geometry to record).

## 8. The web dashboard and live control

Run `python web/dashboard_server.py`, then open:

- **`http://127.0.0.1:8420/`** -- browse every past run (from either the
  desktop app or the web control page below), see its metrics, and open
  a full 3D replay of any run that has a `_frames.jsonl`.
- **`http://127.0.0.1:8420/control`** -- a second, independent front-end
  onto the same real engine as the desktop GUI: the identical 62-parameter
  form (Section 3), an input-source selector with drag-and-drop `.mp4`
  upload, Start/Stop, live tracking-error/FPS charts, and the live 3D view
  streamed over a WebSocket as the run actually happens. Only one run can
  be live at a time across the whole server (starting a second one while
  one is active is rejected) -- this matches "one simulation engine," not
  two independent ones that could disagree.

Both UIs are genuinely two front-ends on one engine: a run started from
`/control` behaves identically to one started from the desktop app (same
`TrackingRunner`, same config resolution), and either one's results are
browsable from `http://127.0.0.1:8420/`.

## 9. Troubleshooting

- **FPS below 20**: Poisson and Gaussian noise are the more expensive
  disturbances; turbulence is expensive by design (~10 FPS alone, when
  enabled) and meant as an offline/demo feature, not something to leave
  on during a benchmarked run.
- **Acquisition never completes**: the target may have spawned far from
  the camera's starting boresight. The system searches outward from the
  centre first (fast for a nearby target), then falls back to a full-
  screen raster sweep after ~3s of no detection -- a raster's full-
  coverage sweep can take up to ~100s at the default 5 deg/s slew rate
  over the default 2000x2000 screen. Widen the Target tab's initial-
  location setting or raise PTZ speed if you need faster worst-case
  acquisition.
- **"No file selected" on Start in video mode**: click Browse (desktop)
  or upload a file (web) first.
- **Web `/control` says "a run is already active"**: only one live run
  is allowed per server process; press Stop first, or check
  `/api/control/status` to see what's running.
- **GUI window doesn't appear**: check the terminal for an exception (a
  missing dependency, or an invalid `.mp4` path, raises a dialog and logs
  to the status bar rather than crashing silently).
- **Optional CNN false-positive filter** (`perception/cnn_filter.py`,
  Section 8.4 of the spec): install `torch` separately to use it --
  everything else, including the packaged exe, works without it, and the
  filter degrades to classical-only if `torch` or a trained model file
  isn't present. Deliberately excluded from the PyInstaller build (its
  full weight is 700MB+) since it's off by default.
