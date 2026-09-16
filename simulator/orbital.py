"""Derives realistic relative-angular-rate numbers from actual orbital
mechanics, so the "circular"/"straight_line" motion presets used for
space-relevant scenarios are parametrized from real physics (altitude,
orbital velocity, relative geometry) instead of an arbitrary radius and
period picked to look reasonable on screen.

These feed simulator/scenario_presets.py's named scenarios (LEO-LEO
crosslink, LEO-ground downlink, GEO-ground) -- the numbers here are what
justifies calling those scenarios "LEO" or "GEO" rather than just relabeled
generic circular/random motion.
"""
from __future__ import annotations

import math

GM_EARTH = 3.986004418e14   # m^3/s^2, standard gravitational parameter of Earth
R_EARTH_M = 6_371_000.0


def orbital_velocity_ms(altitude_km: float) -> float:
    """Circular-orbit velocity (m/s) at the given altitude above Earth's
    surface (vis-viva for a circular orbit: v = sqrt(GM / r))."""
    r = R_EARTH_M + altitude_km * 1000.0
    return math.sqrt(GM_EARTH / r)


def leo_ground_peak_angular_rate_deg_s(altitude_km: float = 500.0) -> float:
    """Peak angular slew rate (deg/s) a ground station must track a LEO
    satellite at, during an overhead (zenith) pass -- the worst case of
    the pass, where angular rate omega ~= v_orbital / altitude (small-
    angle, closest-approach approximation; a real pass eases in/out from
    the horizon, which is what simulator/target_motion.py's CircularMotion
    approximates when used with this as its peak angular speed)."""
    v = orbital_velocity_ms(altitude_km)
    omega_rad_s = v / (altitude_km * 1000.0)
    return math.degrees(omega_rad_s)


def leo_leo_crosslink_angular_rate_deg_s(altitude_km: float = 500.0, range_km: float = 2000.0,
                                          relative_inclination_deg: float = 30.0) -> float:
    """Angular rate (deg/s) of the line-of-sight direction between two
    LEO satellites in different orbital planes, separated by
    relative_inclination_deg, at the given crosslink range. Relative
    velocity between two same-altitude circular orbits differing by
    inclination di is ~= 2*v*sin(di/2) (isosceles-triangle approximation
    treating both velocity vectors as equal magnitude, differing in
    direction by di); the LOS angular rate is that relative velocity
    component across the line of sight, divided by range."""
    v = orbital_velocity_ms(altitude_km)
    v_rel = 2 * v * math.sin(math.radians(relative_inclination_deg) / 2.0)
    omega_rad_s = v_rel / (range_km * 1000.0)
    return math.degrees(omega_rad_s)


def geo_ground_residual_rate_deg_s(station_keeping_box_deg: float = 0.05, period_hours: float = 24.0) -> float:
    """Residual angular rate (deg/s) of a GEO satellite as seen from a
    ground station, from routine station-keeping drift within a small box
    (station_keeping_box_deg, typically +-0.05 deg for a well-maintained
    GEO slot) over one orbital period -- GEO is nominally stationary
    relative to the ground; this is the small residual motion that
    remains, several orders of magnitude below a LEO pass."""
    period_s = period_hours * 3600.0
    # Treat the drift as a slow back-and-forth traverse of the box once per period.
    return (2 * station_keeping_box_deg) / period_s


PRESET_DESCRIPTIONS = {
    "leo_leo_crosslink": "Two LEO satellites, ~500km altitude, ~2000km crosslink range, "
                          "~30deg relative inclination -- fast, roughly linear relative motion.",
    "leo_ground_downlink": "Ground station tracking a ~500km-altitude LEO satellite through "
                            "an overhead pass -- arcing motion, peak rate at zenith crossing.",
    "geo_ground": "Ground station tracking a GEO satellite -- nominally stationary, only "
                  "slow station-keeping-box residual drift.",
}
