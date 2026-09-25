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


@dataclass
class StructuredJitterModel:
    """Jitter with a resonance peak in its power spectral density, driven
    by white noise through a per-axis damped-oscillator (second-order
    resonant) filter, instead of independent uniform-random per-frame
    displacement.

    Real spacecraft jitter is not spectrally flat: reaction wheels,
    cryocoolers and other rotating/reciprocating mechanisms impose
    narrow-band vibration at their spin/operating frequency. Modeling
    that (even simplified to a single dominant resonance) is what
    distinguishes "structured platform jitter" from generic noise, and
    is closer to what a real ADCS/pointing engineer would simulate.

    Discrete-time damped oscillator per axis:
        x[n] = 2*rho*cos(2*pi*f0*dt)*x[n-1] - rho^2*x[n-2] + w[n]
    driven by white noise w[n], with rho<1 controlling the resonance
    peak's sharpness (closer to 1 = narrower peak at f0) and the output
    scaled to stay within max_px.
    """
    max_px: float = 20.0
    resonance_hz: float = 8.0
    damping: float = 0.985
    _x_hist: Tuple[float, float] = (0.0, 0.0)  # x[n-1], x[n-2] for the pan axis
    _y_hist: Tuple[float, float] = (0.0, 0.0)  # for the tilt axis
    _scale_estimate: float = 1.0

    def _step_axis(self, hist: Tuple[float, float], dt: float, rng: np.random.Generator) -> Tuple[float, Tuple[float, float]]:
        theta = 2 * math.pi * self.resonance_hz * dt
        x_prev1, x_prev2 = hist
        w = rng.normal(0, 1.0)
        x_new = 2 * self.damping * math.cos(theta) * x_prev1 - self.damping ** 2 * x_prev2 + w
        return x_new, (x_new, x_prev1)

    def step(self, dt: float, rng: Optional[np.random.Generator] = None) -> Tuple[int, int]:
        rng = rng or np.random.default_rng()
        x_new, self._x_hist = self._step_axis(self._x_hist, dt, rng)
        y_new, self._y_hist = self._step_axis(self._y_hist, dt, rng)
        # The resonant filter's steady-state output amplitude isn't fixed
        # analytically here (it depends on damping/frequency/dt); track a
        # running estimate of its typical magnitude and rescale so the
        # displacement stays within +-max_px, matching the spec's jitter
        # amplitude bound regardless of the resonance parameters chosen.
        self._scale_estimate = 0.99 * self._scale_estimate + 0.01 * (abs(x_new) + abs(y_new) + 1e-6)
        norm = self.max_px / max(self._scale_estimate * 3.0, 1e-6)
        dx = int(np.clip(x_new * norm, -self.max_px, self.max_px))
        dy = int(np.clip(y_new * norm, -self.max_px, self.max_px))
        return dx, dy


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


def apply_atmosphere(img: np.ndarray, mode: str = "clear", rng: Optional[np.random.Generator] = None,
                     strength: float = 1.0) -> np.ndarray:
    """strength scales the preset's contrast loss and brightness shift
    (the spec's "user-defined reduction in contrast and brightness"):
    0 = clear, 1 = the preset as listed, 2 = twice as severe."""
    contrast, brightness = ATMOSPHERE_PRESETS.get(mode, (1.0, 0))
    contrast = max(0.05, 1.0 - (1.0 - contrast) * strength)
    brightness = brightness * strength
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
    stacking on top of intentional PTZ commands (Section 6.4 last bullet).

    step() returns the boresight displacement for ONE frame in camera
    pixels, matching the spec's "+-20 pixels/frame" unit; SimulatorEngine
    converts it to world pixels through the camera's own px-per-degree
    scale. (An earlier revision multiplied by dt, which silently shrank
    the drift ~30x below its labelled px/frame value.)"""
    mode: str = "linear"
    max_px_frame: float = 20.0
    angle_deg: float = 15.0
    period_s: float = 6.0
    t: float = 0.0
    _phase: float = field(default_factory=lambda: 0.0)

    def step(self, dt: float) -> Tuple[float, float]:
        self.t += dt
        m = self.max_px_frame
        w = 2 * math.pi / self.period_s
        if self.mode == "linear":
            dx = m * math.cos(math.radians(self.angle_deg))
            dy = m * math.sin(math.radians(self.angle_deg))
        elif self.mode == "circular":
            dx = m * math.cos(w * self.t)
            dy = m * math.sin(w * self.t)
        elif self.mode == "random":
            dx = np.random.uniform(-m, m)
            dy = np.random.uniform(-m, m)
        elif self.mode == "spiral":
            # growing-then-resetting radius: amplitude ramps 0 -> max over 3 periods
            r = m * ((self.t / (3 * self.period_s)) % 1.0)
            dx = r * math.cos(w * self.t)
            dy = r * math.sin(w * self.t)
        elif self.mode == "figure8":
            dx = m * math.sin(w * self.t)
            dy = m * math.sin(2 * w * self.t)
        else:
            dx = dy = 0.0
        return dx, dy

    @classmethod
    def from_disturbance_config(cls, cfg: "DisturbanceConfig") -> Optional["PlatformMotionDrift"]:
        if not cfg.platform_motion:
            return None
        return cls(mode=cfg.platform_motion_mode, max_px_frame=cfg.platform_motion_max_px_frame)


@dataclass
class DisturbanceConfig:
    salt_pepper: bool = False
    salt_pepper_amount: float = 0.10
    gaussian: bool = False
    gaussian_sigma: float = 10.0
    poisson: bool = False
    jitter: bool = False
    jitter_max_px: int = 20
    jitter_structured: bool = False       # resonant (structured PSD) jitter instead of uniform random
    jitter_resonance_hz: float = 8.0
    atmosphere_mode: str = "clear"
    turbulence: bool = False
    turbulence_r0: float = 0.05
    turbulence_physical: bool = False     # derive r0 from Hufnagel-Valley Cn2 instead of using turbulence_r0 directly
    turbulence_wavelength_nm: float = 1550.0
    turbulence_altitude_m: float = 20000.0
    turbulence_zenith_deg: float = 0.0
    atmosphere_strength: float = 1.0      # 0 = no effect, 1 = preset, up to 2 = twice as severe
    platform_motion: bool = False
    platform_motion_mode: str = "linear"
    platform_motion_max_px_frame: float = 5.0

    @classmethod
    def from_config(cls, cfg: dict) -> "DisturbanceConfig":
        d = cfg.get("disturbances", {})
        noise = d.get("noise", {})
        jitter_cfg = d.get("jitter", {})
        turb_cfg = d.get("turbulence", {})
        pm_cfg = d.get("platform_motion", {})
        return cls(
            salt_pepper=noise.get("salt_pepper", {}).get("enabled", False),
            salt_pepper_amount=noise.get("salt_pepper", {}).get("amount", 0.10),
            gaussian=noise.get("gaussian", {}).get("enabled", False),
            gaussian_sigma=noise.get("gaussian", {}).get("sigma", 10.0),
            poisson=noise.get("poisson", {}).get("enabled", False),
            jitter=jitter_cfg.get("enabled", False),
            jitter_max_px=jitter_cfg.get("max_px", 20),
            jitter_structured=jitter_cfg.get("structured", False),
            jitter_resonance_hz=jitter_cfg.get("resonance_hz", 8.0),
            atmosphere_mode=d.get("atmosphere", {}).get("mode", "clear"),
            turbulence=turb_cfg.get("enabled", False),
            turbulence_r0=turb_cfg.get("r0", 0.05),
            turbulence_physical=turb_cfg.get("physical", False),
            turbulence_wavelength_nm=turb_cfg.get("wavelength_nm", 1550.0),
            turbulence_altitude_m=turb_cfg.get("altitude_m", 20000.0),
            turbulence_zenith_deg=turb_cfg.get("zenith_deg", 0.0),
            atmosphere_strength=d.get("atmosphere", {}).get("strength", 1.0),
            platform_motion=pm_cfg.get("enabled", False),
            platform_motion_mode=pm_cfg.get("mode", "linear"),
            platform_motion_max_px_frame=pm_cfg.get("max_px_frame", 5.0),
        )

    def resolved_turbulence_r0(self) -> float:
        """r0 (in the pixel-space units apply_turbulence expects) to
        actually use: either the raw config value, or -- if
        turbulence_physical is set -- derived from a real Hufnagel-Valley
        Cn2 integration via simulator/link_budget.py, so the turbulence
        strength traces back to real atmospheric-optics inputs instead of
        being an arbitrary number."""
        if not self.turbulence_physical:
            return self.turbulence_r0
        from simulator.link_budget import compute_fried_parameter, fried_parameter_pixel_equivalent
        r0_m = compute_fried_parameter(
            wavelength_nm=self.turbulence_wavelength_nm,
            zenith_deg=self.turbulence_zenith_deg,
            path_altitude_m=self.turbulence_altitude_m,
        )
        # Camera's angular resolution (deg/px); matches the 4deg/640px
        # default -- an approximation when a different FOV/resolution is
        # configured, since DisturbanceConfig doesn't carry camera state.
        pixel_scale_deg = 4.0 / 640.0
        return fried_parameter_pixel_equivalent(r0_m, self.turbulence_wavelength_nm, pixel_scale_deg)


def apply_disturbances(img: np.ndarray, cfg: DisturbanceConfig,
                        rng: Optional[np.random.Generator] = None,
                        jitter_model: Optional["StructuredJitterModel"] = None,
                        dt: float = 1 / 30.0) -> Tuple[np.ndarray, dict]:
    """Apply all enabled disturbances in a fixed, documented order:
    atmosphere -> turbulence -> noise -> jitter. Returns the processed
    image and a dict of applied jitter offsets (for diagnostics).

    `jitter_model`: pass a persistent StructuredJitterModel instance (one
    per SimulatorEngine, since it's stateful across frames) to use
    structured (resonant-PSD) jitter instead of independent uniform
    random displacement -- only takes effect when
    cfg.jitter_structured is also set.
    """
    rng = rng or np.random.default_rng()
    out = img
    info = {}
    if cfg.atmosphere_mode != "clear":
        out = apply_atmosphere(out, cfg.atmosphere_mode, rng, strength=cfg.atmosphere_strength)
    if cfg.turbulence:
        out = apply_turbulence(out, cfg.resolved_turbulence_r0(), rng=rng)
    if cfg.salt_pepper:
        out = apply_salt_pepper(out, cfg.salt_pepper_amount, rng)
    if cfg.gaussian:
        out = apply_gaussian_noise(out, cfg.gaussian_sigma, rng)
    if cfg.poisson:
        out = apply_poisson_noise(out, rng)
    if cfg.jitter:
        if cfg.jitter_structured and jitter_model is not None:
            dx, dy = jitter_model.step(dt, rng)
            out = _shift(out, dx, dy)
        else:
            out, (dx, dy) = apply_jitter(out, cfg.jitter_max_px, rng)
        info["jitter_dx"], info["jitter_dy"] = dx, dy
    return out, info
