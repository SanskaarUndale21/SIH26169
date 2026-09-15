# User Manual: FSOC Coarse-Alignment Tracker

## 1. Installation

Requires Python 3.10+.

```
pip install -r requirements.txt
python main.py
```

To build a standalone executable (no Python install required to run it):

```
pyinstaller --noconfirm --name fsoc-coarse-tracker --onedir --add-data "config;config" --collect-all pyqtgraph main.py
```

The result is `dist/fsoc-coarse-tracker/fsoc-coarse-tracker.exe`. Run it
directly; it bundles its own Python runtime and dependencies.

(Optional) To use the learned false-positive filter
(`perception/cnn_filter.py`, Section 8.4), install `torch` separately --
everything else works without it, and the filter gracefully disables
itself if `torch` or a trained model file isn't present.

## 2. Application overview

The window has three panels:

- **Left**: configuration panel -- input source, target motion, camera
  FOV, PTZ speed limits, disturbance toggles.
- **Centre**: live video feed with detection/prediction overlay, and
  Start/Stop/Reset controls.
- **Right**: live dashboard -- tracking-error plot (with the 10px
  reference line), FPS plot (with the 20 FPS reference line), lock-state
  timeline, and a live text readout of the current performance metrics.

## 3. Parameter configuration guide

- **Input source**: "Simulator" (virtual scene + PTZ) or "Load video file
  (.mp4)" (bypasses the simulator/PTZ entirely -- the same detector/tracker
  runs against the raw video frames).
- **Target motion**: straight_line, circular, figure8, random, spiral.
- **Target shape/size**: square or circle, 5-20px.
- **Camera FOV**: horizontal/vertical field of view in degrees (default
  4x3).
- **PTZ speed limits**: max pan/tilt slew rate in deg/s (default 5).
- **Disturbances**: salt & pepper / Gaussian / Poisson noise toggles,
  camera jitter, and an atmosphere preset (clear/haze/fog/rain/low_light).

Every parameter not exposed in the GUI (screen size, motion speed/radius/
period, PID gains, IMM process noise, detector thresholds, turbulence) is
in `config/default_config.yaml` with inline comments explaining each
default.

## 4. Running a simulation scenario

1. Select "Simulator".
2. Set target motion, disturbances, and any other parameters.
3. Press **Start**. The video panel shows the live feed with a coloured
   border/marker: **red** = searching, **yellow** = acquiring or
   reacquiring, **green** = locked.
4. Press **Stop** at any point -- the performance log is written
   automatically to `logs/` (JSON + CSV, see Section 6).
5. **Reset** clears the run state without restarting a new one.

## 5. Loading and running an external video file

1. Select "Load video file (.mp4)".
2. Click **Browse...** and pick a `.mp4` file.
3. Press **Start**. The identical detector + IMM tracker + lock-state
   machine runs against the raw video frames; there is no PTZ to drive
   (the video is not steerable), so the pointing-command telemetry field
   stays at (0, 0) and the video panel simply shows the annotated frames.
4. Ground-truth tracking error isn't computed in this mode (no simulator
   ground truth exists for a real video) -- `avg_tracking_error_px` /
   `max_tracking_error_px` in the log will be `null`; acquisition time,
   FPS, and lock-retention rate are still measured.

## 6. Reading the live dashboard and the generated performance log

Dashboard plots update every frame while running. On **Stop**, a log is
written to `logs/run_<timestamp>.json` and `.csv` with exactly these
fields: `simulation_duration_sec`, `fps`, `acquisition_time_sec`,
`avg_tracking_error_px`, `max_tracking_error_px`, `lock_retention_rate`,
`processing_time_per_frame_ms`, plus `rmse_px`, `re_acquisition_count`,
`re_acquisition_times_sec`, `target_loss_events` for your own tuning.

## 7. Troubleshooting

- **FPS below 20**: Poisson and Gaussian noise are the most expensive
  disturbances; turbulence (if enabled via config, not exposed in the GUI)
  is expensive by design (~90ms/frame) and meant as an offline/demo
  feature, not something to leave on during a benchmarked run.
- **Acquisition never completes**: the target may have spawned far from
  the camera's starting boresight. The system searches outward from the
  centre first (fast for a nearby target), then falls back to a full-
  screen raster sweep after ~3s of no detection -- a raster's full-
  coverage sweep can take up to ~100s at the default 5 deg/s slew rate
  over the default 2000x2000 screen. Reduce `target.initial_location`'s
  spawn radius or increase PTZ speed in the config file if you need
  faster worst-case acquisition.
- **"No file selected" on Start in video mode**: click Browse first.
- **GUI window doesn't appear**: check the terminal for an exception (a
  missing dependency, or an invalid `.mp4` path, raises a dialog and logs
  to the status bar rather than crashing silently).
