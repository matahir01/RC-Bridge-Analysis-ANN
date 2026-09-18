import pytest

from rc_bridge.codes.eurocode.fatigue_traffic import (
    fatigue_load_model_3,
    flm3_simple_span_section_moment_range,
)


def test_flm3_vehicle_has_four_axles_and_standard_spacing() -> None:
    vehicle = fatigue_load_model_3()

    assert vehicle.axle_loads_kn == pytest.approx((120.0, 120.0, 120.0, 120.0))
    assert vehicle.axle_offsets_m == pytest.approx((0.0, 1.2, 7.2, 8.4))
    assert vehicle.transverse_wheel_spacing_m == pytest.approx(2.0)


def test_flm3_simple_span_range_scales_with_validated_distribution_factor() -> None:
    full = flm3_simple_span_section_moment_range(
        span_m=15.0,
        section_position_m=7.5,
        movement_steps=401,
    )
    distributed = flm3_simple_span_section_moment_range(
        span_m=15.0,
        section_position_m=7.5,
        longitudinal_distribution_factor=0.28,
        movement_steps=401,
    )

    assert full.moment_range_knm > 0.0
    assert distributed.moment_range_knm == pytest.approx(
        0.28 * full.moment_range_knm,
        rel=1.0e-12,
    )
    assert distributed.minimum_moment_knm == pytest.approx(0.0)


def test_flm3_section_range_is_symmetric_about_simple_span() -> None:
    left = flm3_simple_span_section_moment_range(
        span_m=15.0,
        section_position_m=4.0,
        movement_steps=801,
    )
    right = flm3_simple_span_section_moment_range(
        span_m=15.0,
        section_position_m=11.0,
        movement_steps=801,
    )

    assert left.moment_range_knm == pytest.approx(right.moment_range_knm, rel=2.0e-4)
