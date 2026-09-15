"""Translates coarse-pointing error into what it actually costs the FSOC
link, and derives the atmospheric turbulence strength (Fried parameter)
from physical inputs instead of an arbitrary config number.

This is what turns "we hit 3px average error" into "we hit 3px = X dB of
pointing loss, against a Y dB budget" -- the actual reason coarse
alignment accuracy matters, and the piece a real FSOC link-budget review
would ask about.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class LinkBudgetConfig:
    beam_divergence_urad: float = 20.0   # 1/e^2 half-angle divergence of the laser beam
    fine_stage_capture_range_urad: float = 500.0  # angular error below which fine-pointing can take over
    wavelength_nm: float = 1550.0
    range_km: float = 1000.0

    @classmethod
    def from_config(cls, cfg: dict) -> "LinkBudgetConfig":
        d = cfg.get("link_budget", {})
        return cls(
            beam_divergence_urad=d.get("beam_divergence_urad", 20.0),
            fine_stage_capture_range_urad=d.get("fine_stage_capture_range_urad", 500.0),
            wavelength_nm=d.get("wavelength_nm", 1550.0),
            range_km=d.get("range_km", 1000.0),
        )


def px_error_to_angular_error(px_error: float, fov_deg: float, resolution_px: int) -> float:
    """Converts a pixel tracking error to an angular pointing error in
    microradians, using the camera's own FOV-to-pixel scale (the coarse
    camera and the laser are assumed co-boresighted, so a pixel of
    residual tracking error is a pixel of residual laser pointing error)."""
    rad_per_px = math.radians(fov_deg) / resolution_px
    return px_error * rad_per_px * 1e6  # -> microradians


def pointing_loss_db(angular_error_urad: float, beam_divergence_urad: float,
                      max_loss_db: float = 60.0) -> float:
    """Gaussian-beam pointing loss in dB for a boresight offset of
    angular_error against a beam of 1/e^2 half-angle divergence
    beam_divergence (same units). Standard result for a Gaussian beam:
    fractional power captured ~ exp(-2*(theta/theta_div)^2); expressed as
    a (positive) dB loss: L_dB = 8.686 * (theta/theta_div)^2.

    Clamped at max_loss_db (default 60dB, already an enormous loss any
    real link would call "down"): this is the small-error-regime formula,
    and beyond a few multiples of the divergence its raw value keeps
    growing without bound in a way that isn't physically meaningful --
    coarse pointing this far off is simply "no signal," which is exactly
    what a maxed-out `handoff_ready=False` already communicates. The
    clamp keeps the reported number in a sane "this is very bad" range
    instead of an eye-catching-but-meaningless four-digit dB figure.
    """
    if beam_divergence_urad <= 0:
        return 0.0
    ratio = angular_error_urad / beam_divergence_urad
    return min(8.686 * ratio ** 2, max_loss_db)


def is_handoff_ready(angular_error_urad: float, capture_range_urad: float) -> bool:
    """Whether the current coarse-pointing error is inside the fine-
    pointing stage's angular capture range -- i.e. coarse alignment has
    done its job and the fine stage could take over (Section 1's "before
    fine pointing mechanism can take over" handoff criterion)."""
    return angular_error_urad <= capture_range_urad


# ---------------------------------------------------------------------------
# Physically-derived atmospheric turbulence strength (Fried parameter r0)
# ---------------------------------------------------------------------------

def hufnagel_valley_cn2(h_m: float, wind_speed_ms: float = 21.0, cn2_ground: float = 1.7e-14) -> float:
    """Hufnagel-Valley 5/7 refractive-index structure constant Cn^2(h)
    (m^-2/3) at altitude h (m). The standard model used throughout
    atmospheric-optics literature for a vertical/slant turbulence
    profile; `wind_speed_ms` (rms high-altitude wind, default 21 m/s) and
    `cn2_ground` (ground-level turbulence strength, default 1.7e-14, a
    typical daytime value) are its two physical parameters."""
    v, A = wind_speed_ms, cn2_ground
    term1 = 0.00594 * (v / 27.0) ** 2 * (1e-5 * h_m) ** 10 * math.exp(-h_m / 1000.0)
    term2 = 2.7e-16 * math.exp(-h_m / 1500.0)
    term3 = A * math.exp(-h_m / 100.0)
    return term1 + term2 + term3


def compute_fried_parameter(wavelength_nm: float = 1550.0, zenith_deg: float = 0.0,
                             wind_speed_ms: float = 21.0, cn2_ground: float = 1.7e-14,
                             path_altitude_m: float = 20000.0, n_steps: int = 200) -> float:
    """Fried parameter r0 (m) for a slant path from the ground to
    path_altitude_m at zenith angle zenith_deg, integrating the
    Hufnagel-Valley Cn^2 profile:

        r0 = [0.423 * k^2 * sec(zeta) * integral_0^H Cn2(h) dh]^(-3/5)

    where k = 2*pi/wavelength. This replaces picking r0 by hand in
    simulator/disturbances.py's turbulence model with a value derived
    from real physical inputs (wavelength, altitude, zenith angle, wind,
    ground turbulence) -- the standard approach in atmospheric-optics
    literature rather than an arbitrary tuning knob."""
    wavelength_m = wavelength_nm * 1e-9
    k = 2 * math.pi / wavelength_m
    sec_zenith = 1.0 / max(math.cos(math.radians(zenith_deg)), 1e-3)

    # Trapezoidal integration of Cn2(h) from 0 to path_altitude_m.
    hs = [path_altitude_m * i / n_steps for i in range(n_steps + 1)]
    vals = [hufnagel_valley_cn2(h, wind_speed_ms, cn2_ground) for h in hs]
    dh = path_altitude_m / n_steps
    integral = dh * (sum(vals) - 0.5 * vals[0] - 0.5 * vals[-1])

    inner = 0.423 * k ** 2 * sec_zenith * integral
    if inner <= 0:
        return 1.0  # degenerate case: effectively no turbulence
    return inner ** (-3.0 / 5.0)


def fried_parameter_pixel_equivalent(r0_m: float, wavelength_nm: float, pixel_scale_deg: float) -> float:
    """Converts a physical Fried parameter (metres, at the receiving
    aperture) into the pixel-space r0 that
    simulator/disturbances.py's kolmogorov_phase_screen actually consumes
    (its Kolmogorov PSD is formulated directly in cycles/pixel, not
    metres at a pupil -- it approximates the *effect* of turbulence as a
    pixel-space phase screen rather than physically propagating a wave
    through an aperture).

    Standard relation: the atmospheric seeing disk (full-width, ~the
    angular blur turbulence imposes) is angular_seeing ~= wavelength / r0.
    We treat that angular size, expressed in pixels via the camera's own
    deg/pixel scale, as the equivalent pixel-space r0 -- i.e. "how many
    pixels does one coherence length span". This is a documented
    approximation (see the technical report), not a rigorous aperture
    propagation, but it ties the phase screen's strength to a physically
    meaningful r0 instead of an arbitrary tuning constant.
    """
    wavelength_m = wavelength_nm * 1e-9
    seeing_rad = wavelength_m / max(r0_m, 1e-6)
    pixel_scale_rad = math.radians(pixel_scale_deg)
    r0_px = seeing_rad / max(pixel_scale_rad, 1e-12)
    return max(r0_px, 0.5)
