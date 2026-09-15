import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.link_budget import (compute_fried_parameter, fried_parameter_pixel_equivalent,
                                    is_handoff_ready, pointing_loss_db, px_error_to_angular_error)
from simulator.orbital import (geo_ground_residual_rate_deg_s, leo_ground_peak_angular_rate_deg_s,
                                leo_leo_crosslink_angular_rate_deg_s, orbital_velocity_ms)


def test_leo_orbital_velocity_matches_known_value():
    # A 500km-altitude circular LEO orbit has a well-known velocity of
    # ~7.6 km/s -- sanity-checks the vis-viva implementation.
    v = orbital_velocity_ms(500)
    assert 7500 < v < 7700


def test_leo_ground_peak_rate_within_ptz_budget():
    # A ground station's peak LEO-pass tracking rate should be well
    # within the spec's 5-10 deg/s PTZ speed range, or the scenario would
    # be untrackable by construction.
    rate = leo_ground_peak_angular_rate_deg_s(500)
    assert 0 < rate < 5.0


def test_geo_residual_rate_negligible_compared_to_leo():
    geo_rate = geo_ground_residual_rate_deg_s()
    leo_rate = leo_ground_peak_angular_rate_deg_s(500)
    assert geo_rate < leo_rate / 1000


def test_crosslink_rate_positive_and_scales_with_range():
    close = leo_leo_crosslink_angular_rate_deg_s(500, 500, 30)
    far = leo_leo_crosslink_angular_rate_deg_s(500, 2000, 30)
    assert close > far > 0  # same relative velocity, angular rate falls off with range


def test_angular_error_conversion():
    # 4deg FOV over 640px -> ~0.00625 deg/px -> ~109 urad/px
    urad = px_error_to_angular_error(1.0, fov_deg=4.0, resolution_px=640)
    assert 100 < urad < 120


def test_pointing_loss_zero_at_zero_error():
    assert pointing_loss_db(0.0, 20.0) == 0.0


def test_pointing_loss_increases_with_error_and_is_clamped():
    small = pointing_loss_db(5.0, 20.0)
    large = pointing_loss_db(500.0, 20.0)
    assert 0 < small < large
    assert large <= 60.0  # clamped ceiling


def test_handoff_ready_thresholds():
    assert is_handoff_ready(100.0, capture_range_urad=500.0) is True
    assert is_handoff_ready(600.0, capture_range_urad=500.0) is False


def test_fried_parameter_positive_and_pixel_conversion():
    r0_m = compute_fried_parameter(wavelength_nm=1550, zenith_deg=0)
    assert r0_m > 0
    r0_px = fried_parameter_pixel_equivalent(r0_m, 1550, pixel_scale_deg=4.0 / 640)
    assert r0_px > 0


def test_fried_parameter_degrades_at_higher_zenith_angle():
    # Longer slant path through the atmosphere at higher zenith angle ->
    # more integrated turbulence -> smaller (worse) r0.
    r0_zenith = compute_fried_parameter(zenith_deg=0.0)
    r0_slant = compute_fried_parameter(zenith_deg=60.0)
    assert r0_slant < r0_zenith
