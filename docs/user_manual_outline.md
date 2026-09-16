# User Manual -- Outline

1. **Installation** -- `pip install -r requirements.txt`, Python 3.10+,
   `python main.py` to launch.
2. **Application overview** -- three-panel layout: config panel (left),
   video + controls (centre), dashboard (right).
3. **Parameter configuration guide** -- every control in `gui/config_panel.py`
   mapped back to Section 3 of the spec: target motion/shape/size, camera
   FOV, PTZ speed limits, disturbance toggles.
4. **Running a simulation scenario** -- select "Simulator", set parameters,
   press Start; explain lock-state colour coding (red/yellow/green) in the
   video panel overlay.
5. **Loading and running an external video file** -- select "Load video
   file (.mp4)", Browse to a file, press Start; explain that PTZ/camera
   controls are inactive in this mode (Benchmark-2 bypass).
6. **Reading the live dashboard and the performance log** -- tracking-error
   plot with the 10px reference line, FPS plot with the 20 FPS reference
   line, lock-state timeline, and where the auto-generated JSON/CSV log
   lands (`logs/` by default, see `config/default_config.yaml`).
7. **Troubleshooting** -- common issues: no GPU needed; if FPS is below 20,
   check disturbance settings (Poisson noise is the most expensive); if
   acquisition never completes, check target spawn location vs. camera FOV.
