# Testing your own algorithm

This software is also a test bench. You can replace any of the three stages of
the coarse-alignment loop with your own Python code. Your version then runs
on the same virtual camera, beacon paths, disturbances and scoring as the
built-in algorithms, so the comparison is fair.

## The three stages

Every camera frame goes through these stages in order:

| Stage | You implement | Input | Output |
|---|---|---|---|
| Detector | `detect(image)` | 8-bit monochrome frame (numpy array) | list of `Detection(x, y, score)` |
| Tracker | `update(dt, measurement)` | seconds since last frame, chosen detection `(x, y)` or `None` if missed | estimated position `(x, y)`, or `None` with no track yet |
| Controller | `compute(err_x_deg, err_y_deg, dt)` | offset of the estimate from the image centre, in degrees (positive = right/down) | `(pan_rate, tilt_rate)` in deg/s |

These parts are shared by every algorithm and stay unchanged when you swap
one stage:

- Picking the detection nearest the current estimate (a 60 px gate).
- The searching → acquiring → locked → re-acquiring state machine.
- The spiral-then-raster search when nothing is seen.
- The gimbal speed limits.
- Every metric.

Pixel coordinates have their origin at the top left, with x to the right and y down.

## Writing one

1. Open **Algorithms** in the web console and click **Write a new algorithm**.
   Pick the stage and a name, and a working template opens in the editor.
   You can also copy a file from `user_algorithms/` and edit it in any editor.
2. Subclass `Detector`, `Tracker` or `Controller` from `algorithms.api`.
   One file can hold several classes.
3. Declare tunable parameters in `params`. They show up as sliders on the
   New run and Compare pages:

   ```python
   params = {"k": {"default": 6.0, "min": 1.0, "max": 20.0, "step": 0.5, "help": "Threshold in sigmas"}}
   ```

   Read them as `self.p["k"]`. A plain `{"k": 6.0}` also works.
4. Put one-time setup in `setup()`. `self.ctx` holds the following:
   - `frame_width` and `frame_height`
   - `fov_deg` (`None` for video input) and `px_per_deg`
   - `target_size_px`
   - `max_pan_deg_s` and `max_tilt_deg_s`
   - `frame_rate_hz`
   - the full `config`
5. Controllers can implement `reset()`. It is called when the beacon is lost
   and the search takes over. Trackers can implement `confidence(detected)`,
   which returns a value from 0 to 1.

Working examples ship in `user_algorithms/`:

- `example_matched_filter.py`: a detector.
- `example_alpha_beta.py`: a tracker.
- `example_pd_deadband.py`: a controller.

The built-in algorithms are written against the same API, in `algorithms/builtin.py`.

## Checking it

**Check** on the editor loads your file on its own and runs each class through
6 simulated seconds of two scenarios: spec defaults and heavy sensor noise. The
other two stages stay at their defaults. For each scenario it reports:

- Acquisition time
- Tracking error
- Target loss
- Algorithm-only processing speed

If your code crashes or returns something malformed, you get the traceback
and a plain message such as "Tracker 'X' must return (x, y) or None".
A file that fails to import is listed at the top of the Algorithms page with
its error. It does not break the rest of the app.

## Using it

- **One run:** on **New run**, go to the **Algorithms** step, pick your algorithm and set its parameters.
  The Live page, run report and logs all record which algorithms ran.
- **Comparison:** open **Compare** and set up two to four algorithm sets. Tick
  scenarios and choose the number of repeats and the run length, then run.
  Each repeat uses one random seed shared by every set, so the beacon path,
  noise and disturbances are identical across sets. Results show each set's
  pass rate against the problem statement's targets, along with the means and
  worst cases, a per-scenario error chart and a per-scenario pass matrix.
  Averages only cover runs that locked on, so the table says so when a set
  failed to lock in some runs. Results are saved as `logs/bench_<time>.json`.
- **Desktop app:** the **Algorithms** tab in the config panel lists every
  plugin. Plugin-specific parameters take their default values there; use the
  web console to change them.
- **Scripted runs:** set `algorithms:` in `config/default_config.yaml`, or
  call `algorithms.benchmark.run_single()` / `BenchJob` from Python.

## Notes

- Files are re-imported whenever they change, so you don't need to restart.
- "Processing speed" in comparisons is 1000 / processing time per frame. It
  measures only detection, tracking and control. The loop FPS also includes
  the simulator rendering the scene and its noise, which is the same for every
  algorithm.
- Plugins run as normal Python inside the console's process with full access
  to the machine. The console only listens on 127.0.0.1, so only run code you
  trust.
