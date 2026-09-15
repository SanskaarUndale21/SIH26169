# Technical Report -- Outline

Fill in with real numbers from `tests/benchmark_matrix.py` output before
submission. Target length: 10-15 pages.

1. **Problem understanding** -- FSOC, PAT, coarse vs. fine alignment
   (summarize `26169.pdf` background section).
2. **System architecture** -- three-module split (Simulator / Perception+
   Tracking / Control+GUI), the `Frame`/`Telemetry` interface diagram,
   why the split matters for Benchmark-2 (video bypasses Simulator
   entirely, same Perception+Tracking code path).
3. **Simulator design**
   - Target motion models (straight line, circular, figure-8, random walk,
     spiral) -- equations from `simulator/target_motion.py`.
   - Camera model -- linear small-angle FOV-to-pixel mapping, PTZ speed
     clamp (`simulator/camera_model.py`).
   - Disturbance models -- noise (salt & pepper, Gaussian, Poisson),
     jitter, atmospheric presets, platform motion
     (`simulator/disturbances.py`).
   - Kolmogorov turbulence phase-screen model (if enabled) -- PSD
     equation, FFT synthesis, beam-wander warp + scintillation.
4. **Detection method** -- DoG/matched filter, robust median/MAD adaptive
   threshold, connected-component filtering, intensity-weighted
   centroiding math (`perception/detector.py`).
5. **Tracking method** -- IMM: model set (CV/CT/random-walk sharing a
   common 5-state for tractable mixing), mixing/update/combination steps,
   why IMM over a single Kalman filter, and the finite-difference
   velocity/turn-rate seeding used to cut post-lock convergence lag
   (`perception/imm_tracker.py`, `perception/pipeline.py`).
6. **Control method** -- PID design, anti-windup, actuator speed-clamp
   interaction (`control/pid_controller.py`).
7. **Re-acquisition strategy** -- lock-state machine, outward spiral
   search vs. raster fallback (`perception/lock_state.py`,
   `control/search_driver.py`).
8. **AI methods used, if any** -- Section 8.4 CNN false-positive filter
   scope/limitations, if implemented.
9. **Test methodology** -- Section 12 matrix: 4 motions x 10 disturbance
   conditions, methodology and pass/fail thresholds.
10. **Performance analysis** -- paste `tests/benchmark_matrix.py` summary
    table; discuss which combinations pass/fail Section 10 and why.
11. **Innovation/novelty summary** -- turbulence physics model, IMM,
    velocity/turn-rate-informed search and track seeding.
12. **Future improvements** -- e.g. adaptive process-noise scheduling,
    multi-target data association, learned false-positive filter hardening.
