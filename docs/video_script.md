# Demo video script: FSOC Coarse Alignment Console

Problem statement 26169 (ISRO, Department of Space) asks for an optional 3 to 5
minute demo video. This script runs about **5 minutes** and covers the
problem, the solution, a live demo and the algorithm test bench.

Each scene lists what is **on screen**, what you **say**, and **notes** for
the recording. Read the narration at a calm pace. Where the script says
"about", say the number that actually appears on screen.

---

## Before you record

**Setup**
- [ ] Start the web console: `python web/dashboard_server.py`, then open `http://127.0.0.1:8420/`.
- [ ] Browser full screen (F11), zoom 100%, window at 1920 × 1080. Close other tabs and turn off notifications.
- [ ] Record at 1080p, 30 fps or more. OBS Studio works well: one "Display capture" plus your microphone.
- [ ] Have a test video ready: `data/sample_videos/test.mp4`, or one of your own `.mp4` files with a moving bright spot.

**Warm-up so every page has content**
- [ ] Do one clean run beforehand, so Overview and Runs already have data.
- [ ] Run one comparison beforehand: Default vs. the example plugins, 4 scenarios, 1 repeat, 10 s. On camera you open its saved result instead of waiting for it.
- [ ] In New run, click **Reset to defaults** so the recording starts from the spec values.

**Fallbacks and audio**
- [ ] Optional: build the desktop app so you can show it for 5 seconds.
- [ ] Practise the whole flow once. Cut any pause longer than 2 seconds while editing.
- [ ] Record the voice separately if your room is noisy, then lay it over the screen recording.

---

## Scene 1: Hook (0:00 to 0:20)

**On screen:** Overview page. The round scope animation spirals, finds the
amber beacon and turns green: "Locked in 1.x s".

**Say:**
> "An optical laser link between two satellites is narrower than a pencil beam
> over hundreds of kilometres. Before any data can flow, one terminal has to
> find the other and keep it in view. This is our software for that first
> step: coarse alignment."

**Notes:** Let the animation play one full cycle before you start speaking. It
is the visual hook.

---

## Scene 2: The problem (0:20 to 0:50)

**On screen:** Stay on Overview and scroll slowly down to "What happens every frame".

**Say:**
> "Free-space optical communication promises gigabit links with no spectrum
> licence, but pointing, acquisition and tracking is hard. Coarse alignment
> has to observe the scene, detect the remote beacon, estimate where it is,
> and keep steering the camera so it never leaves the field of view.
> Testing this on real hardware needs expensive cameras and gimbals. ISRO
> asked for a software platform instead, and that's what we built."

**Notes:** Pause the scroll on the four steps: Observe, Acquire, Estimate, Point.

---

## Scene 3: How it works (0:50 to 1:30)

**On screen:** The four steps stay visible. Optionally cut to a simple
architecture slide: Simulator → Perception and tracking → Control → Metrics.

**Say:**
> "Every frame goes through four stages.
> **Observe:** a virtual 640 by 480 monochrome camera with a 4 by 3 degree field
> of view renders a 2000 by 2000 pixel scene at 30 hertz, with noise, weather,
> jitter and platform shake added in.
> **Acquire:** a difference-of-Gaussians detector finds point-like spots above
> the local noise floor, and a spot must persist for several frames before
> we trust it.
> **Estimate:** an interacting multiple-model filter blends straight, turning
> and erratic motion models, so it keeps predicting even when a frame is missed.
> **Point:** a PID loop drives pan and tilt within the 5 degrees per second
> limit, and if the beacon is lost, a spiral and then raster search sweeps
> until it's found again."

**Notes:** This is the technical core the judges score, so speak clearly and
don't rush it.

---

## Scene 4: Setting up a run (1:30 to 2:10)

**On screen:** Click **New run**.
1. Step 1, Source: keep **Simulated scene**. Point at the scenario buttons.
2. Step 3, Beacon: click through the motion options (Straight line, Circular, Figure-8, Random walk, Spiral, Sinusoidal, User-defined). Settle on **Figure-8**.
3. Step 4, Disturbances: turn on **Gaussian noise** and set Atmosphere to **Fog**. The camera preview on the right updates live.

**Say:**
> "Every parameter from the problem statement is here, starting at the
> suggested values. The beacon can move on all four required paths plus
> spiral, sinusoidal and a user-drawn path. Disturbances cover salt and
> pepper, Gaussian and Poisson noise, camera jitter, haze, fog, rain, low
> light, turbulence and platform motion, and they can be stacked.
> On the right is a real frame from the simulator with these settings, so
> you see exactly what the tracker will see, plus the beacon's path across
> the whole screen."

**Notes:** Hover over the 4× close-up inset in the preview for a second. It
shows the noise around the beacon clearly.

---

## Scene 5: Live tracking (2:10 to 3:00)

**On screen:** Click **Start run**. The Live page opens.
1. **Camera** view: the green crosshair sits on the beacon while the scene moves.
2. Switch to **Whole screen**: the camera's view box follows the beacon across the 2000 × 2000 screen.
3. Switch to **3D gimbal**: the pointing cone moves. Drag to orbit once.
4. Point at the right column: lock state, then the spec numbers turning green.

**Say:**
> "This is the live camera feed. The green crosshair is our tracker's
> estimate, the dashed box is the true beacon position from the simulator,
> and the centre marks show where the camera is pointing.
> The whole-screen view shows the camera chasing the beacon across the scene,
> and the 3D view shows the gimbal's actual pan and tilt.
> On the right, every performance target from the problem statement is
> scored live. We locked on in about [0.2] seconds against a limit of 2,
> average error is about [1 to 2] pixels against a limit of 10, target loss
> is zero, and processing is well above 20 frames per second."

Click **Stop and save**.

**Notes:** Let it run at least 20 seconds before stopping, so the error chart
fills in.

---

## Scene 6: Report and performance log (3:00 to 3:25)

**On screen:** Click **Open report**. Scroll through the scorecard, the error
chart with the green lock ribbon, the performance log and the Scenario table.
Hover over the download buttons.

**Say:**
> "Every run produces a performance report automatically: duration, frame
> rate, acquisition and re-acquisition time, average, maximum and RMS error,
> lock retention and processing time. It downloads as JSON or CSV, together
> with a per-frame centroid log for the benchmark comparison, and there's a
> 3D replay of the whole run."

---

## Scene 7: Real video input, Benchmark 2 (3:25 to 3:50)

**On screen:** New run → Source → **Video file**. Drop the `.mp4` and start.
The Live page shows the video with detections on it. Stop, then show the
report's **Centroid log (CSV)** button.

**Say:**
> "For Benchmark 2, the camera is bypassed completely. Any 30 frames per
> second video goes straight into the same detection and tracking pipeline,
> and the per-frame centroid log is ready to compare against the reference
> values."

**Notes:** If time is short, cut this scene to 10 seconds: drop the file,
show the live feed, cut away.

---

## Scene 8: Test your own algorithm (3:50 to 4:40)

**On screen:**
1. Click **Algorithms**. Show the "How your code plugs in" panel, then click **Alpha-beta filter (example)** to show its parameters and code.
2. Click **Write a new algorithm**, choose **Tracker**, **Open template**, then **Check**. Results appear for two scenarios.
3. Click **Compare** and open the comparison you ran beforehand from **Past comparisons**. Show the summary table, the bar chart and the per-scenario matrix.

**Say:**
> "The problem statement describes this as a platform for developing and
> learning tracking algorithms, so we made every stage swappable. A
> researcher writes a detector, tracker or pointing controller as one Python
> class, right here in the browser or as an uploaded file.
> Check runs it on two scenarios straight away and reports acquisition,
> error, loss and speed, or a clear message if the code breaks.
> Compare then races algorithm sets on exactly the same beacon paths and
> noise, using shared random seeds, and scores every run against ISRO's
> targets, so the difference you see comes only from the algorithm."

**Notes:** This is your most distinctive feature, so give it room. If a set
shows "only 3 of 4 runs locked", point at it: it shows the comparison is
honest.

---

## Scene 9: Spec check and close (4:40 to 5:00)

**On screen:** Click **Spec check**. Scroll slowly through the sections, then
cut to the Overview animation to finish.

**Say:**
> "Spec check maps every line of the problem statement to what the system
> does and the latest measured results. We also deliver a standalone desktop
> application, the documented source code, a technical report and a user
> manual.
> A complete coarse-alignment system, and a test bench for the next one.
> Thank you."

**Notes:** End on the scope locking green. Hold it for 2 seconds of silence.

---

## Optional 5-second insert: desktop app

Between Scenes 6 and 7, cut to the desktop application running the same
scenario. Say: *"The same engine also runs as a standalone desktop
application."*

---

## YouTube details

**Title:** FSOC Coarse Alignment: AI-Assisted Virtual Camera Tracking | SIH 2026 PS 26169

**Description:**
```
Software coarse-alignment system for free-space optical communication terminals,
built for Smart India Hackathon 2026, problem statement 26169 (ISRO, Department of Space).

A virtual pan-tilt camera detects, acquires and tracks a moving optical beacon
under noise, fog, jitter and platform motion, scored live against ISRO's
performance targets. Includes real video input (Benchmark 2), automatic
performance logs, and a test bench to plug in and compare your own algorithms.

Chapters
0:00 Why pointing matters
0:20 The coarse alignment problem
0:50 How it works
1:30 Setting up a scenario
2:10 Live tracking
3:00 Performance report
3:25 Real video input
3:50 Test your own algorithm
4:40 Spec check
```

**Visibility:** set it to **Unlisted** unless your team wants it public. Unlisted can still be shared by link with the evaluators.

**Thumbnail:** a screenshot of the Overview scope locked green, with the text "Find the beacon. Hold the lock."
