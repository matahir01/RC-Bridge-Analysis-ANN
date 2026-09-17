import pytest
from rc_bridge.design.eurocode_serviceability import (
    ec2_tension_stiffening_zeta,
    interpolate_service_deformation,
    uncracked_t_section_sls,
)


def test_uncracked_t_section_sls_properties_are_positive() -> None:
    result = uncracked_t_section_sls(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        modular_ratio=6.0,
        fct_eff_mpa=3.2,
    )
    assert result.transformed_area_mm2 > 0.0
    assert 0.0 < result.neutral_axis_from_top_mm < 1200.0
    assert result.second_moment_mm4 > 0.0
    assert result.cracking_moment_knm > 0.0


def test_tension_stiffening_is_zero_before_cracking() -> None:
    assert ec2_tension_stiffening_zeta(100.0, 150.0) == pytest.approx(0.0)


def test_tension_stiffening_matches_ec2_interpolation_form() -> None:
    zeta = ec2_tension_stiffening_zeta(300.0, 150.0, beta=0.5)
    assert zeta == pytest.approx(0.875)


def test_deformation_interpolation_uses_state_weights() -> None:
    value = interpolate_service_deformation(10.0, 30.0, 0.25)
    assert value == pytest.approx(15.0)
