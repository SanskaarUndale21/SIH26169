"""Named test scenarios, shared by the web console's quick-start buttons
and the algorithm benchmark, so "Heavy sensor noise" means the same
thing everywhere. Each scenario is a set of overrides on top of the
spec defaults, keyed like the parameter schema ("a/b/c": value)."""

SCENARIOS = [
    {"id": "default", "title": "Spec defaults", "desc": "Straight line, clear sky, no noise", "values": {}},
    {"id": "noise", "title": "Heavy sensor noise", "desc": "Salt and pepper 10%, Gaussian σ 20, Poisson", "values": {
        "disturbances/noise/salt_pepper/enabled": True, "disturbances/noise/salt_pepper/amount": 0.10,
        "disturbances/noise/gaussian/enabled": True, "disturbances/noise/gaussian/sigma": 20,
        "disturbances/noise/poisson/enabled": True}},
    {"id": "weather", "title": "Fog and shake", "desc": "Fog, camera jitter ±10 px, circular path", "values": {
        "disturbances/atmosphere/mode": "fog", "disturbances/jitter/enabled": True,
        "disturbances/jitter/max_px": 10, "target/motion": "circular"}},
    {"id": "platform", "title": "Moving platform", "desc": "Figure of 8 beacon, circular platform drift", "values": {
        "target/motion": "figure8", "disturbances/platform_motion/enabled": True,
        "disturbances/platform_motion/mode": "circular", "disturbances/platform_motion/max_px_frame": 5}},
    {"id": "night", "title": "Low light, random walk", "desc": "Dim scene, erratic beacon, Gaussian σ 10", "values": {
        "disturbances/atmosphere/mode": "low_light", "target/motion": "random",
        "disturbances/noise/gaussian/enabled": True, "disturbances/noise/gaussian/sigma": 10}},
    {"id": "fast", "title": "Fast weave", "desc": "Sinusoidal path at 120 px/s, small 6 px beacon", "values": {
        "target/motion": "sinusoidal", "target/motion_params/sinusoidal/speed_px_s": 120,
        "target/size_px/0": 6, "target/size_px/1": 6}},
    {"id": "leo", "title": "LEO crosslink", "desc": "Orbit-derived motion between two satellites", "values": {
        "scenario_preset": "leo_leo_crosslink"}},
]

BY_ID = {s["id"]: s for s in SCENARIOS}
