import pytest

from rc_bridge.design.eurocode_demand import check_flexure_rectangular
from rc_bridge.design.eurocode_support_flexure import (
    check_negative_bending_rectangular_support,
)


def test_negative_support_check_matches_rectangular_magnitude_kernel() -> None:
    support = check_negative_bending_rectangular_support(
        design_moment_knm=-500.0,
        compression_width_m=0.30,
        effective_depth_m=1.05,
        provided_top_steel_area_mm2=5000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    positive_kernel = check_flexure_rectangular(
        med_knm=500.0,
        width_m=0.30,
        effective_depth_m=1.05,
        provided_steel_area_mm2=5000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert support.resistance_magnitude_knm == pytest.approx(
        positive_kernel.resistance_knm
    )
    assert support.signed_resistance_knm == pytest.approx(
        -positive_kernel.resistance_knm
    )
    assert support.required_top_steel_area_mm2 == pytest.approx(
        positive_kernel.required_steel_area_mm2
    )
    assert support.g_hogging_knm == pytest.approx(
        positive_kernel.g_flexure_knm
    )


def test_negative_support_check_flags_insufficient_top_steel() -> None:
    result = check_negative_bending_rectangular_support(
        design_moment_knm=-1200.0,
        compression_width_m=0.30,
        effective_depth_m=1.05,
        provided_top_steel_area_mm2=2500.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert result.utilization > 1.0
    assert result.g_hogging_knm < 0.0
    assert result.passes is False
    assert result.required_top_steel_area_mm2 > result.provided_top_steel_area_mm2


def test_negative_support_check_rejects_positive_moment() -> None:
    with pytest.raises(ValueError, match="non-positive"):
        check_negative_bending_rectangular_support(
            design_moment_knm=100.0,
            compression_width_m=0.30,
            effective_depth_m=1.05,
            provided_top_steel_area_mm2=5000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        )
