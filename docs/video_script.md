# Demo video script: FSOC Coarse Alignment Console

A **demo-first** video for problem statement 26169, about **4 to 5 minutes**.
Almost the whole video is the screen recording of the software working.
The narration is short and describes only what is on screen, with no slides
and no theory sections.

Each shot lists what you **click**, what you **say** (one or two lines),
and an optional **caption** to put on screen while editing. Where the
script says a number in [brackets], say the number that actually appears.

---

## Before you record

- [ ] Start the console: `python web/dashboard_server.py`, then open `http://127.0.0.1:8420/`.
- [ ] Browser full screen (F11), zoom 100%, 1920 × 1080. Close other tabs and turn off notifications.
- [ ] Record at 1080p, 30 fps or more. OBS Studio: "Display capture" plus microphone.
- [ ] Do one clean run beforehand, so Overview and Runs already have data.
- [ ] Run one comparison beforehand: Default vs. the example plugins, 4 scenarios, 1 repeat, 10 s. On camera you open the saved result instead of waiting.
- [ ] Keep `data/sample_videos/test.mp4` (or your own beacon video) ready in a File Explorer window.
- [ ] In New run, click **Reset to defaults**.
- [ ] Rehearse the click path once. Move the mouse slowly, and pause half a second before each click so viewers can follow.

**Editing tips**
- Cut dead time (page loads, waiting). Speed up long waits 2× to 4× instead of cutting them, so it stays honest.
- Zoom in during editing on small things: the crosshair on the beacon, numbers turning green, the Check results.
- Light background music at low volume, under the voice.

---

## Shot 1: Opening (0:00 to 0:15)

**Click:** nothing. Overview page, the scope animation searches, finds the beacon and turns green.

**Say:**
> "Two satellites want to talk by laser. First, one has to find the other and
> keep it in view. This is our software doing exactly that."

**Caption:** *SIH 2026, PS 26169: Virtual camera tracking for FSOC coarse alignment*

---

## Shot 2: Build a scenario (0:15 to 1:00)

**Click:**
1. **New run** in the sidebar.
2. Step 1: point at **Simulated scene** and the scenario buttons.
3. **Next** to Scene and camera: hover over resolution 640 × 480, FOV 4° × 3°, 30 Hz and pan speed 5°/s.
4. **Next** to Beacon: click through the motion buttons one by one (Straight line, Circular, Figure-8, Random walk, Spiral, Sinusoidal, User-defined). Stop on **Figure-8**.
5. **Next** to Disturbances: switch on **Gaussian noise**, set Atmosphere to **Fog**, switch on **Camera jitter**. Watch the camera preview on the right change after each one.

**Say:**
> "Every setting from the problem statement is here, already at the suggested
> values. Seven motion paths for the beacon. Now we add noise, fog and camera
> shake, and the preview on the right shows the actual frame the tracker will
> get."

**Caption:** *Preview = a real rendered frame, not a mock-up*

---

## Shot 3: Live tracking (1:00 to 1:50)

**Click:**
1. **Start run**. The Live page opens.
2. Let the **Camera** view run for about 10 seconds. Mouse near the green crosshair.
3. Click **Whole screen**. Let it run for 5 seconds.
4. Click **3D gimbal**. Drag once to orbit.
5. Move the mouse down the right column: Lock state, then the spec rows.

**Say:**
> "It locks on almost instantly. The green crosshair is our tracker, the dashed
> box is where the beacon really is. Here's the camera chasing it across the
> whole screen, and the gimbal pointing in 3D. On the right, ISRO's targets
> are scored live: locked in about [0.2] seconds, error about [1 to 2]
> pixels, no target loss, well above 20 frames per second."

**Caption:** *Targets: acquisition ≤ 2 s, error ≤ 10 px, loss < 5%, ≥ 20 FPS*

**Click:** **Stop and save**.

---

## Shot 4: The automatic report (1:50 to 2:15)

**Click:**
1. **Open report** on the green banner.
2. Scroll slowly: scorecard, error chart with the lock ribbon, performance log, scenario.
3. Hover over the three download buttons.
4. Scroll to the **3D replay** and press **Play** for 3 seconds.

**Say:**
> "Every run writes its performance report automatically, with a
> frame-by-frame centroid log to download and a full 3D replay."

---

## Shot 5: Real video input (2:15 to 2:40)

**Click:**
1. **New run**, then Step 1: **Video file**.
2. Drag `test.mp4` from File Explorer onto the drop area.
3. **Start run**. The Live page shows the video with the tracker on the beacon.
4. When it finishes, **Open report**, then point at **Centroid log (CSV)**.

**Say:**
> "Benchmark 2: we skip the virtual camera and feed a recorded video
> straight in. Same tracker, same report, same centroid log."

**Caption:** *Benchmark 2: .mp4 input*

---

## Shot 6: Plug in your own algorithm (2:40 to 3:40)

**Click:**
1. **Algorithms** in the sidebar. Pause on the "How your code plugs in" panel for 2 seconds.
2. Click **Alpha-beta filter (example)**. Scroll through its parameters and code.
3. **Write a new algorithm**, choose **Tracker**, then **Open template**.
4. In the editor, change the default `0.5` to `0.3`. Click **Check**. The two result rows appear.
5. **Save**.

**Say:**
> "It's also a test bench. Any stage (detector, tracker or pointing
> controller) can be swapped for your own Python class. Write one right
> here, hit Check, and it's tested on two scenarios in a few seconds. Save it,
> and it's available everywhere."

**Caption:** *Researchers test their own algorithms, no hardware needed*

---

## Shot 7: Head-to-head comparison (3:40 to 4:25)

**Click:**
1. **Compare** in the sidebar. Show the algorithm sets and the ticked scenarios.
2. Scroll to **Past comparisons** and open the one you ran beforehand.
3. Scroll through the summary table, the bar chart and the per-scenario matrix. Mouse on the "best" labels.

**Say:**
> "Compare races algorithm sets on exactly the same beacon paths and noise,
> using shared random seeds, and scores every run against ISRO's targets. So
> the difference you see is purely the algorithm."

**Caption:** *Same scenarios, same seeds, fair comparison*

---

## Shot 8: Close (4:25 to 4:45)

**Click:**
1. **Spec check**. Scroll quickly through the green "Met" rows.
2. Cut back to the Overview scope locking green.

**Say:**
> "Every requirement in the problem statement, mapped and met. A complete
> coarse-alignment system, and a test bench for the next one. Thank you."

**Caption:** *[Team name], [College name]*

Hold the final frame for 2 seconds.

---

## Optional extra shot (5 s): desktop app

After Shot 4, cut to the desktop application running the same scenario.

**Say:** *"The same engine also runs as a standalone desktop app."*

---

## YouTube details

**Title:** FSOC Coarse Alignment Demo: Virtual Camera Beacon Tracking | SIH 2026 PS 26169

**Description:**
```
Live demo of our software coarse-alignment system for free-space optical
communication terminals, built for Smart India Hackathon 2026, problem
statement 26169 (ISRO, Department of Space).

A virtual pan-tilt camera detects and tracks a moving optical beacon under
noise, fog, jitter and platform motion, scored live against the performance
targets. Also shown: real video input (Benchmark 2), the automatic
performance report, and a test bench to plug in and compare your own algorithms.

Chapters
0:00 Opening
0:15 Building a scenario
1:00 Live tracking
1:50 Automatic report
2:15 Real video input
2:40 Plug in your own algorithm
3:40 Algorithm comparison
4:25 Spec check
```

**Visibility:** Unlisted, unless the team wants it public. Unlisted can still be shared by link.

**Thumbnail:** the Live page with the green crosshair on the beacon, plus the text "Locked in 0.2 s".
