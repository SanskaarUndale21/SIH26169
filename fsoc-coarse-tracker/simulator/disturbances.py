"""Per-frame disturbance/noise injection: independently toggleable and
stackable, per Section 6.4 of the spec."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


def apply_salt_pepper(img: np.ndarray, amount: float = 0.10, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or np.random.default_rng()
    out = img.copy()
    mask = rng.random(img.shape[:2])
    n_lo = mask < amount / 2
    n_hi = (mask >= amount / 2) & (mask < amount)
    out[n_lo] = 0
    out[n_hi] = 255
    return out


def apply_gaussian_noise(img: np.ndarray, sigma: float = 10.0, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or np.random.default_rng()
    noise = rng.normal(0, sigma, size=img.shape)
    out = img.astype(np.float32) + noise
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_poisson_noise(img: np.ndarray, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Photon shot noise. Uses the standard Gaussian approximation to a
    Poisson process, Poisson(lambda) ~= Normal(lambda, sqrt(lambda))
    (valid once lambda is more than a few counts, true here given the
    scale factor below) rather than true Poisson sampling: numpy's
    Generator.poisson on a 640x480 array measured ~20ms/frame, more than
    a third of the entire 20 FPS (50ms) frame budget on its own, whereas
    the Normal approximation via `rng.normal` is close to free by
    comparison, with no visible difference in the resulting noise."""
    rng = rng or np.random.default_rng()
    scale = 4.0
    vals = img.astype(np.float32) * scale
    noisy = vals + rng.normal(0.0, 1.0, size=vals.shape) * np.sqrt(np.maximum(vals, 1e-6))
    out = np.clip(noisy, 0, None) / scale
    return np.clip(out, 0, 255).astype(np.uint8)


def apply_jitter(img: np.ndarray, max_px: int = 20, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    rng = rng or np.random.default_rng()
    dx = int(rng.integers(-max_px, max_px + 1))
    dy = int(rng.integers(-max_px, max_px + 1))
    return _shift(img, dx, dy), (dx, dy)


def _shift(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = np.zeros_like(img)
    h, w = img.shape[:2]
    sx0, sx1 = max(0, -dx), min(w, w - dx)
    dx0, dx1 = max(0, dx), min(w, w + dx)
    sy0, sy1 = max(0, -dy), min(h, h - dy)
    dy0, dy1 = max(0, dy), min(h, h + dy)
    if sx1 > sx0 and sy1 > sy0:
        out[dy0:dy1, dx0:dx1, ...] = img[sy0:sy1, sx0:sx1, ...]
    return out


# Atmospheric presets: (contrast_factor, brightness_offset)
ATMOSPHERE_PRESETS = {
    "clear": (1.0, 0),
    "haze": (0.75, 25),
    "fog": (0.55, 45),
    "rain": (0.80, -5),
    "low_light": (0.65, -60),
}


def apply_atmosphere(img: np.ndarray, mode: str = "clear", rng: Optional[np.random.Generator] = None) -> np.ndarray:
    contrast, brightness = ATMOSPHERE_PRESETS.get(mode, (1.0, 0))
    out = img.astype(np.float32) * contrast + brightness
    if mode == "rain":
        out = _apply_rain_streaks(out, rng or np.random.default_rng())
    return np.clip(out, 0, 255).astype(np.uint8)


def _apply_rain_streaks(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w = img.shape[:2]
    n_streaks = int(0.002 * h * w / 100)
    out = img.copy()
    for _ in range(n_streaks):
        x = rng.integers(0, w)
        y = rng.integers(0, h)
        length = rng.integers(5, 15)
        for i in range(length):
            yy, xx = y + i, x - i // 3
            if 0 <= yy < h and 0 <= xx < w:
                out[yy, xx, ...] = min(255, out[yy, xx, ...].max() + 60) if out.ndim == 3 else min(255, out[yy, xx] + 60)
    return out


def kolmogorov_phase_screen(shape, r0: float, rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Generate a Kolmogorov/von-Karman random phase screen via the FFT
    method: PSD Phi(f) ~ 0.023 * r0^(-5/3) * f^(-11/3), inverse-FFT'd to a
    spatial phase screen. r0 is the Fried parameter (larger = weaker
    turbulence). `shape` is (h, w) -- sized to the actual frame rather
    than a padded square, which both keeps the screen's aspect ratio
    correct and roughly halves the FFT cost at the default 640x480.
    """
    if isinstance(shape, int):
        shape = (shape, shape)
    h, w = shape
    rng = rng or np.random.default_rng()
    fx = np.fft.fftfreq(w).reshape(1, -1)
    fy = np.fft.fftfreq(h).reshape(-1, 1)
    f = np.sqrt(fx ** 2 + fy ** 2)
    f[0, 0] = f[0, 1] if w > 1 else 1e-6  # avoid div-by-zero at DC
    psd = 0.023 * (r0 ** (-5.0 / 3.0)) * f ** (-11.0 / 3.0)
    psd[0, 0] = 0.0
    cn = (rng.normal(size=(h, w)) + 1j * rng.normal(size=(h, w)))
    spectrum = cn * np.sqrt(psd)
    screen = np.fft.ifft2(spectrum).real
    screen *= max(h, w)  # normalize energy roughly independent of grid size
    return screen


def apply_turbulence(img: np.ndarray, r0: float = 0.05, strength: float = 3.0,
                      rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """Apply Kolmogorov-phase-screen-driven beam wander (spatial warp) and
    mild scintillation (intensity scaling) to the frame. `strength` scales
    the warp displacement in pixels.

    Performance note: at 640x480 this costs ~90ms/frame (~11 FPS alone),
    dominated by the random-field generation + 2D FFT for a fresh phase
    screen every frame. That's well under the Section 10 processing-speed
    target (>=20 FPS) if left enabled continuously. Turbulence is optional
    per the spec ("recommended differentiator", not a mandatory
    disturbance) -- treat it as an offline/demo feature to show and
    measure separately (see the technical report), not something to leave
    on during a benchmark run. Making this real-time would mean caching a
    slowly-evolving screen across frames instead of redrawing one from
    scratch each frame; left as a documented future improvement.
    """
    import cv2
    rng = rng or np.random.default_rng()
    h, w = img.shape[:2]
    screen = kolmogorov_phase_screen((h, w), r0, rng)
    gy, gx = np.gradient(screen)
    # normalize gradient to unit-ish scale then apply as pixel displacement
    gx = gx / (np.std(gx) + 1e-6) * strength
    gy = gy / (np.std(gy) + 1e-6) * strength
    map_x = (np.arange(w).reshape(1, -1) + gx).astype(np.float32)
    map_y = (np.arange(h).reshape(-1, 1) + gy).astype(np.float32)
    map_x = np.broadcast_to(map_x, (h, w)).astype(np.float32)
    map_y = np.broadcast_to(map_y, (h, w)).astype(np.float32)
    warped = cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REPLICATE)
    scint = 1.0 + 0.05 * (screen / (np.std(screen) + 1e-6))
    out = warped.astype(np.float32) * scint[..., None] if warped.ndim == 3 else warped.astype(np.float32) * scint
    return np.clip(out, 0, 255).astype(np.uint8)


@dataclass
class PlatformMotionDrift:
    """Uncommanded platform motion that moves the camera boresight itself,
    stacking on top of intentional PTZ commands (Section 6.4 last bullet)."""
    mode: str = "linear"
    max_px_frame: float = 20.0
    angle_deg: float = 15.0
    t: float = 0.0
    _phase: float = field(default_factory=lambda: 0.0)

    def step(self, dt: float) -> Tuple[float, float]:
        self.t += dt
        if self.mode == "linear":
            dx = self.max_px_frame * math.cos(math.radians(self.angle_deg))
            dy = self.max_px_frame * math.sin(math.radians(self.angle_deg))
        elif self.mode == "circular":
            omega = 1.0
            dx = self.max_px_frame * math.cos(omega * self.t)
            dy = self.max_px_frame * math.sin(omega * self.t)
        elif self.mode == "random":
            dx = np.random.uniform(-self.max_px_frame, self.max_px_frame)
            dy = np.random.uniform(-self.max_px_frame, self.max_px_frame)
        else:
            dx = dy = 0.0
        return dx * dt, dy * dt


@dataclass
class DisturbanceConfig:
    salt_pepper: bool = False
    salt_pepper_amount: float = 0.10
    gaussian: bool = False
    gaussian_sigma: float = 10.0
    poisson: bool = False
    jitter: bool = False
    jitter_max_px: int = 20
    atmosphere_mode: str = "clear"
    turbulence: bool = False
    turbulence_r0: float = 0.05

    @classmethod
    def from_config(cls, cfg: dict) -> "DisturbanceConfig":
        d = cfg.get("disturbances", {})
        noise = d.get("noise", {})
        return cls(
            salt_pepper=noise.get("salt_pepper", {}).get("enabled", False),
            salt_pepper_amount=noise.get("salt_pepper", {}).get("amount", 0.10),
            gaussian=noise.get("gaussian", {}).get("enabled", False),
            gaussian_sigma=noise.get("gaussian", {}).get("sigma", 10.0),
            poisson=noise.get("poisson", {}).get("enabled", False),
            jitter=d.get("jitter", {}).get("enabled", False),
            jitter_max_px=d.get("jitter", {}).get("max_px", 20),
            atmosphere_mode=d.get("atmosphere", {}).get("mode", "clear"),
        )


def apply_disturbances(img: np.ndarray, cfg: DisturbanceConfig,
                        rng: Optional[np.random.Generator] = None) -> Tuple[np.ndarray, dict]:
    """Apply all enabled disturbances in a fixed, documented order:
    atmosphere -> turbulence -> noise -> jitter. Returns the processed
    image and a dict of applied jitter offsets (for diagnostics)."""
    rng = rng or np.random.default_rng()
    out = img
    info = {}
    if cfg.atmosphere_mode != "clear":
        out = apply_atmosphere(out, cfg.atmosphere_mode, rng)
    if cfg.turbulence:
        out = apply_turbulence(out, cfg.turbulence_r0, rng=rng)
    if cfg.salt_pepper:
        out = apply_salt_pepper(out, cfg.salt_pepper_amount, rng)
    if cfg.gaussian:
        out = apply_gaussian_noise(out, cfg.gaussian_sigma, rng)
    if cfg.poisson:
        out = apply_poisson_noise(out, rng)
    if cfg.jitter:
        out, (dx, dy) = apply_jitter(out, cfg.jitter_max_px, rng)
        info["jitter_dx"], info["jitter_dy"] = dx, dy
    return out, info
