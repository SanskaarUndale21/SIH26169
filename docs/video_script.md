# Demo video script: FSOC Coarse Alignment Test Bench

A **demo-first** video for problem statement 26169, about **5 minutes**.
Following the ISRO mentors' guidance, it leads with the **test bench**
(engineers plug in and compare their own algorithms), then shows the
on-board-computer pointing cue with multi-pass learning, the learned
detector, and our reference tracker.

Each shot lists what you **click**, what you **say** (one or two lines),
and an optional **caption** to put on screen while editing. Where the
script says a number in [brackets], say the number that actually appears.

---

## Before you record

- [ ] Start the console: double-click `start.bat`, or run `python web/dashboard_server.py` and open `http://127.0.0.1:8420/`.
- [ ] Browser full screen (F11), zoom 100%, 1920 × 1080. Close other tabs and turn off notifications. Close heavy apps so the tracker holds 30 FPS.
- [ ] Record at 1080p, 30 fps or more. OBS Studio: "Display capture" plus microphone.
- [ ] Run these beforehand so you open saved results on camera instead of waiting:
  - [ ] One clean run, so Overview has data.
  - [ ] A **comparison**: Default vs. the example plugins vs. a set using the **Learned CNN detector**, with scenarios Spec defaults, Heavy sensor noise, Fog and shake, Moving platform; 1 repeat, 10 s.
  - [ ] A **multi-pass** experiment: Compare, Multi-pass learning tab, Inter-satellite, 8 passes.
- [ ] Keep `data/sample_videos/test.mp4` ready in a File Explorer window.
- [ ] Rehearse the click path once. Move the mouse slowly, and pause half a second before each click.

**Editing tips**
- Speed up waiting 2× to 4× instead of cutting it, so it stays honest.
- Zoom in during editing on small things: the crosshair, numbers turning green, the Check results, the table rows.
- Light background music at low volume, under the voice.

---

## Shot 1: Opening (0:00 to 0:15)

**Click:** nothing. Overview page, "Test your pointing algorithm. No hardware.", with the scope finding the beacon and turning green.

**Say:**
> "Before two satellites can talk by laser, one must find the other and hold
> it in view. This is a test bench for exactly that: bring your own
> algorithm, test it here, no hardware needed."

**Caption:** *SIH 2026, PS 26169: virtual camera test bench for FSOC coarse alignment*

---

## Shot 2: Plug in your own algorithm (0:15 to 1:10)

**Click:**
1. **Test your algorithm**. Pause on "How your code plugs in" for 2 seconds.
2. In the list, click **Learned CNN detector (experimental)**, then **Alpha-beta filter (example)**. Scroll their parameters and code.
3. **Write a new algorithm**, choose **Tracker**, **Open template**.
4. Change `0.5` to `0.3`. Click **Check**. The results appear for two scenarios.
5. **Save**.

**Say:**
> "Every stage is swappable: the detector, the tracker, and the gimbal
> controller. Built in you get classical baselines and a learned CNN detector.
> Write your own right here as one Python class, press Check, and within
> seconds it's run through two scenarios and scored. Save it, and it's
> available everywhere."

**Caption:** *One Python class per stage. Checked in seconds.*

---

## Shot 3: Head-to-head comparison (1:10 to 1:55)

**Click:**
1. **Compare**. Show the algorithm sets and the ticked scenarios. Point at **Your video** as a scenario option.
2. Scroll to **Past comparisons**, open the one you ran beforehand.
3. Scroll through the summary table (point at **Centroid accuracy**, the sub-pixel row), the bar chart, and the per-scenario matrix.

**Say:**
> "Compare races algorithm sets on exactly the same beacon paths and noise,
> using shared random seeds, and scores every run against ISRO's targets.
> Detection accuracy is sub-pixel, about [0.4] pixels. And you can include
> your own recorded video as a test case."

**Caption:** *Same scenarios, same seeds, fair comparison*

---

## Shot 4: On-board computer cue and multi-pass learning (1:55 to 2:55)

**Click:**
1. **New run**, step 3 **Beacon**: switch on **Use the on-board computer's pointing cue**. Point at the uncertainty setting.
2. Step 1: click the **Inter-satellite, cued** scenario. **Start run**.
3. On Live, click **Whole screen**: the purple dashed ring is the predicted area; the camera slews there and locks. Stop and save.
4. **Compare**, **Multi-pass learning** tab. Show the saved experiment: headline, chart, table.

**Say:**
> "On orbit, the satellite's computer tells the camera roughly where the
> other terminal is. The camera slews to that prediction and scans around
> it, so a beacon anywhere in the sky is found in about [2] seconds.
> For inter-satellite links that prediction carries an error that repeats
> every pass. Here the terminal learns it: after each pass the cue gets
> corrected. With the raw cue, [2] passes never found the beacon; with
> learning, every pass did, and the cue error fell from about [4] degrees to
> about [1]."

**Caption:** *Learns the prediction error across passes*

---

## Shot 5: Live tracking under disturbances (2:55 to 3:45)

**Click:**
1. **New run**, click the **Heavy sensor noise** scenario, then step 4 **Disturbances**: add **Fog** and **Camera jitter**. Watch the preview change.
2. **Start run**. Let the **Camera** view run about 10 seconds, mouse near the crosshair.
3. **3D gimbal**, drag once to orbit.
4. Move down the right column: lock state, then the spec rows.

**Say:**
> "Every parameter from the problem statement is here, with seven motion
> paths and every disturbance. Under noise, fog and shake the reference
> tracker still locks in about [0.2] seconds, holds about [1 to 2] pixels
> of error, loses nothing, and runs above 20 frames per second."

**Caption:** *Targets: acquisition ≤ 2 s, error ≤ 10 px, loss < 5%, ≥ 20 FPS*

Click **Stop and save**.

---

## Shot 6: Report and video input (3:45 to 4:25)

**Click:**
1. **Open report**. Scroll: scorecard, error chart, performance log (point at centroid accuracy), downloads, 3D replay for 3 seconds.
2. **New run**, **Video file**, drop `test.mp4`, **Start run**. Let it lock, then cut.

**Say:**
> "Every run writes its performance report automatically, with a frame-by-frame
> centroid log and a 3D replay. And for Benchmark 2, a recorded video goes
> straight into the same pipeline."

---

## Shot 7: Close (4:25 to 4:45)

**Click:**
1. **Spec check**. Scroll quickly through the green rows.
2. Cut back to the Overview scope locking green.

**Say:**
> "Every requirement in the problem statement, mapped and met. A test bench
> for the next generation of optical pointing algorithms. Thank you."

**Caption:** *[Team name], [College name]*

Hold the final frame for 2 seconds.

---

## YouTube details

**Title:** FSOC Coarse Alignment Test Bench: Plug In, Compare, Track | SIH 2026 PS 26169

**Description:**
```
A software test bench for the coarse pointing stage of free-space optical
communication terminals, built for Smart India Hackathon 2026, problem
statement 26169 (ISRO, Department of Space).

Plug in your own beacon detector, tracker or gimbal controller as a Python
class and compare it against built-in classical and learned (CNN) algorithms
on identical simulated scenarios: noise, fog, jitter, platform motion and
on-board-computer pointing cues, with learning of the cue error across
passes. Every run is scored against the problem statement's targets.

Chapters
0:00 Opening
0:15 Plug in your own algorithm
1:10 Head-to-head comparison
1:55 On-board computer cue and multi-pass learning
2:55 Live tracking under disturbances
3:45 Report and video input
4:25 Spec check
```

**Visibility:** Unlisted unless the team wants it public.

**Thumbnail:** the Multi-pass learning chart, or the Live page with the crosshair on the beacon, plus the text "Bring your own algorithm".
