import pytest

from rc_bridge.design.eurocode_detailing import beam_detailing_requirements
from rc_bridge.design.eurocode_fatigue import (
    concrete_compression_fatigue_check,
    concrete_design_fatigue_strength_mpa,
    reinforcement_fatigue_check,
)


def test_reinforcement_fatigue_equivalent_stress_range_check() -> None:
    result = reinforcement_fatigue_check(
        reference_stress_range_mpa=88.0,
        lambda_s=0.89,
        phi_fat=1.0,
        characteristic_fatigue_strength_mpa=162.5,
        gamma_s_fat=1.15,
    )
    assert result.equivalent_stress_range_mpa == pytest.approx(78.32)
    assert result.design_fatigue_resistance_mpa == pytest.approx(141.304347826)
    assert result.utilization < 1.0
    assert result.g_fatigue_mpa > 0.0
    assert result.passes


def test_reinforcement_fatigue_local_dynamic_factor_can_govern() -> None:
    base = reinforcement_fatigue_check(
        reference_stress_range_mpa=88.0,
        lambda_s=0.89,
        phi_fat=1.0,
        characteristic_fatigue_strength_mpa=162.5,
    )
    near_joint = reinforcement_fatigue_check(
        reference_stress_range_mpa=88.0,
        lambda_s=0.89,
        phi_fat=1.30,
        characteristic_fatigue_strength_mpa=162.5,
    )
    assert near_joint.equivalent_stress_range_mpa == pytest.approx(
        base.equivalent_stress_range_mpa * 1.30
    )
    assert near_joint.utilization > base.utilization


def test_concrete_compression_fatigue_check_uses_en1992_2_relation() -> None:
    fcd_fat = concrete_design_fatigue_strength_mpa(
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=1.0,
        k1=0.85,
        beta_cc_t0=1.10,
    )
    result = concrete_compression_fatigue_check(
        sigma_c_max_mpa=10.0,
        sigma_c_min_mpa=3.0,
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=1.0,
        k1=0.85,
        beta_cc_t0=1.10,
    )
    assert result.fcd_fat_mpa == pytest.approx(fcd_fat)
    assert result.demand_ratio == pytest.approx(10.0 / fcd_fat)
    assert result.allowable_ratio == pytest.approx(0.5 + 0.45 * 3.0 / fcd_fat)
    assert result.utilization == pytest.approx(
        result.demand_ratio / result.allowable_ratio
    )


def test_beam_detailing_requirements_for_c35_45_b500() -> None:
    result = beam_detailing_requirements(
        fctm_mpa=3.209962441695238,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        tension_zone_width_m=0.30,
        web_width_m=0.30,
        effective_depth_m=1.10,
        concrete_area_m2=0.50,
        provided_longitudinal_steel_mm2=6500.0,
        design_required_asw_per_s_mm2_per_m=420.0,
    )

    assert result.longitudinal.minimum_tension_steel_mm2 == pytest.approx(550.829554995)
    assert result.longitudinal.maximum_longitudinal_steel_mm2 == pytest.approx(20000.0)
    assert result.longitudinal.satisfies_minimum
    assert result.longitudinal.satisfies_maximum

    assert result.shear.minimum_rho_w == pytest.approx(0.000946572765296)
    assert result.shear.minimum_asw_per_s_mm2_per_m == pytest.approx(283.971829589)
    assert result.shear.governing_required_asw_per_s_mm2_per_m == pytest.approx(420.0)
    assert result.shear.maximum_longitudinal_link_spacing_mm == pytest.approx(825.0)
    assert result.shear.maximum_transverse_leg_spacing_mm == pytest.approx(600.0)


def test_minimum_shear_reinforcement_can_govern_design_requirement() -> None:
    result = beam_detailing_requirements(
        fctm_mpa=3.2,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        tension_zone_width_m=0.30,
        web_width_m=0.30,
        effective_depth_m=1.10,
        concrete_area_m2=0.50,
        provided_longitudinal_steel_mm2=6500.0,
        design_required_asw_per_s_mm2_per_m=100.0,
    )
    assert result.shear.governing_required_asw_per_s_mm2_per_m == pytest.approx(
        result.shear.minimum_asw_per_s_mm2_per_m
    )
