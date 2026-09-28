"""Trains the learned beacon detector and exports it to ONNX.

    pip install torch onnx          # training only; not needed to run the app
    python tools/train_detector.py  # writes algorithms/models/beacon_cnn.onnx

Training data comes from the simulator itself, so labels are exact: frames
are rendered across random beacon sizes (5-20 px, independent width and
height), both shapes, and every disturbance at random strength (salt and
pepper, Gaussian, Poisson, jitter, all five atmospheres with severity up to
2, occasional turbulence). Each frame goes through the same proposal step
the runtime uses (algorithms/learned.py); a proposal within 3 px of the true
beacon is a positive and learns the sub-pixel offset to it, everything else
is a negative. When the beacon is in view but too faint for any proposal, a
jittered positive is added anyway so the network learns low-SNR beacons.
"""
from __future__ import annotations

import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from algorithms.learned import MODEL_PATH, PATCH, patches, propose  # noqa: E402
from simulator.camera_model import CameraModel  # noqa: E402
from simulator.disturbances import DisturbanceConfig  # noqa: E402
from simulator.renderer import SimulatorEngine  # noqa: E402
from simulator.scene import Scene  # noqa: E402

POS_RADIUS = 3.0


def random_config(rng: random.Random) -> dict:
    w, h = rng.randint(5, 20), rng.randint(5, 20)
    if rng.random() < 0.5:
        h = w
    d = {
        "noise": {
            "salt_pepper": {"enabled": rng.random() < 0.35, "amount": rng.uniform(0.02, 0.12)},
            "gaussian": {"enabled": rng.random() < 0.55, "sigma": rng.uniform(2, 25)},
            "poisson": {"enabled": rng.random() < 0.35},
        },
        "jitter": {"enabled": rng.random() < 0.3, "max_px": rng.randint(1, 20)},
        "atmosphere": {"mode": rng.choice(["clear", "clear", "haze", "fog", "rain", "low_light"]),
                       "strength": rng.uniform(0.5, 2.0)},
        "turbulence": {"enabled": rng.random() < 0.05, "r0": rng.uniform(0.03, 0.2)},
    }
    return {
        "screen": {"width": 2000, "height": 2000},
        "target": {"num_targets": rng.choice([1, 1, 1, 2]), "shape": rng.choice(["square", "circle"]),
                   "size_px": [w, h], "initial_location": "random", "motion": "random",
                   "motion_params": {"random": {"speed_px_s": 40, "theta_std_deg": 30}}},
        "disturbances": d,
    }


def make_dataset(n_frames: int, seed: int):
    rng = random.Random(seed)
    X, Y = [], []
    n_pos = 0
    for f in range(n_frames):
        cfg = random_config(rng)
        random.seed(rng.random())
        scene = Scene.from_config(cfg)
        t0 = rng.uniform(0, 30)
        tx, ty = scene.targets[0].position(t0)
        cam = CameraModel(world_x=tx + rng.uniform(-45, 45), world_y=ty + rng.uniform(-35, 35))
        if rng.random() < 0.15:  # beacon out of view: pure negatives
            cam.world_x += 400
        eng = SimulatorEngine(scene, cam, DisturbanceConfig.from_config(cfg), seed=rng.randint(0, 10**9))
        eng.t = t0
        img, gts = eng.render()
        pts = propose(img, max_n=48)
        labels = []
        for x, y in pts:
            near = [(gx - x, gy - y) for gx, gy in gts if math.hypot(gx - x, gy - y) <= POS_RADIUS]
            labels.append((1.0, *min(near, key=lambda d: math.hypot(*d))) if near else (0.0, 0.0, 0.0))
        extra = []
        for gx, gy in gts:
            if 0 <= gx < img.shape[1] and 0 <= gy < img.shape[0] and not any(
                    math.hypot(gx - x, gy - y) <= POS_RADIUS for x, y in pts):
                px, py = int(round(gx + rng.uniform(-2, 2))), int(round(gy + rng.uniform(-2, 2)))
                extra.append((px, py))
                labels.append((1.0, gx - px, gy - py))
        allpts = np.concatenate([pts, np.array(extra, np.int32).reshape(-1, 2)]) if extra else pts
        if len(allpts):
            X.append(patches(img, allpts))
            Y.append(np.array(labels, np.float32))
            n_pos += int(sum(l[0] for l in labels))
        if (f + 1) % 500 == 0:
            print(f"  {f + 1}/{n_frames} frames, {sum(len(y) for y in Y)} patches, {n_pos} positive", flush=True)
    return np.concatenate(X), np.concatenate(Y)


class BeaconNet(nn.Module):
    """~9k parameters. Output: [logit, dx, dy]."""

    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(),
            nn.Conv2d(16, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),     # 12
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),     # 6
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),     # 3
        )
        self.head = nn.Sequential(nn.Flatten(), nn.Linear(32 * 3 * 3, 32), nn.ReLU(), nn.Linear(32, 3))

    def forward(self, x):
        return self.head(self.body(x))


def train(X, Y, epochs=8, seed=0):
    torch.manual_seed(seed)
    n = len(X)
    idx = np.random.default_rng(seed).permutation(n)
    val = idx[: n // 10]
    tr = idx[n // 10:]
    Xt, Yt = torch.from_numpy(X), torch.from_numpy(Y)
    pos_frac = float(Y[tr, 0].mean())
    model = BeaconNet()
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    bce = nn.BCEWithLogitsLoss(pos_weight=torch.tensor((1 - pos_frac) / max(pos_frac, 1e-3)))
    for ep in range(epochs):
        model.train()
        perm = torch.from_numpy(np.random.default_rng(seed + ep).permutation(tr))
        for b in range(0, len(perm), 512):
            j = perm[b:b + 512]
            out = model(Xt[j])
            y = Yt[j]
            loss = bce(out[:, 0], y[:, 0])
            m = y[:, 0] > 0.5
            if m.any():
                loss = loss + 0.5 * nn.functional.smooth_l1_loss(out[m, 1:], y[m, 1:])
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            out = model(Xt[val])
            y = Yt[val]
            pred = out[:, 0] > 0
            tp = int((pred & (y[:, 0] > 0.5)).sum())
            fp = int((pred & (y[:, 0] < 0.5)).sum())
            fn = int((~pred & (y[:, 0] > 0.5)).sum())
            m = y[:, 0] > 0.5
            off = float((out[m, 1:] - y[m, 1:]).norm(dim=1).mean()) if m.any() else float("nan")
        print(f"epoch {ep + 1}: recall {tp / max(tp + fn, 1):.3f}  precision {tp / max(tp + fp, 1):.3f}  "
              f"offset error {off:.3f} px", flush=True)
    return model


def main():
    t = time.time()
    n_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    print(f"generating {n_frames} frames")
    X, Y = make_dataset(n_frames, seed=2026)
    print(f"dataset {len(X)} patches, {int(Y[:, 0].sum())} positive, {time.time() - t:.0f} s")
    model = train(X, Y)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(model, torch.zeros(1, 1, PATCH, PATCH), str(MODEL_PATH), input_names=["patch"],
                      output_names=["out"], dynamic_axes={"patch": {0: "n"}, "out": {0: "n"}},
                      opset_version=13, dynamo=False)
    print(f"wrote {MODEL_PATH} ({MODEL_PATH.stat().st_size / 1024:.0f} KB) in {time.time() - t:.0f} s")


if __name__ == "__main__":
    main()
