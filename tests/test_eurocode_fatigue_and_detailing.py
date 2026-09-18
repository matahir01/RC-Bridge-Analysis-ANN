import pytest

from rc_bridge.design.eurocode_detailing import (
    AnchorageDetailingPolicy,
    LapSplicePolicy,
    anchorage_and_lap_lengths_mm,
    beam_detailing_requirements,
    check_end_anchorage_length,
    check_longitudinal_cage_fit,
    continuous_bar_core_plan,
    nominal_cover_check,
    plan_staggered_lap_splices,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
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


def test_discrete_longitudinal_bar_selection_meets_area_and_spacing() -> None:
    result = select_longitudinal_bar_arrangement(
        required_area_mm2=6200.0,
        web_width_mm=300.0,
        cover_mm=50.0,
        link_diameter_mm=12.0,
    )

    assert result.provided_area_mm2 >= 6200.0
    assert result.layer_count <= 3
    assert sum(result.bars_per_layer) == result.bar_count
    assert result.clear_horizontal_spacing_mm >= max(25.0, result.bar_diameter_mm)
    assert result.fits_web


def test_discrete_vertical_link_selection_meets_area_and_spacing() -> None:
    result = select_vertical_link_arrangement(
        required_asw_per_s_mm2_per_m=420.0,
        web_width_mm=300.0,
        maximum_longitudinal_spacing_mm=300.0,
        maximum_transverse_leg_spacing_mm=200.0,
        cover_mm=50.0,
    )

    assert result.provided_asw_per_s_mm2_per_m >= 420.0
    assert result.spacing_mm <= 300.0
    assert result.satisfies_required_area


def test_anchorage_lap_and_cover_checks_are_explicit() -> None:
    anchorage = anchorage_and_lap_lengths_mm(
        bar_diameter_mm=32.0,
        fyk_mpa=500.0,
        fctd_mpa=1.50,
    )
    cover = nominal_cover_check(
        bar_diameter_mm=32.0,
        durability_minimum_cover_mm=40.0,
        allowance_for_deviation_mm=10.0,
        provided_cover_mm=50.0,
    )

    assert anchorage.design_anchorage_length_mm >= anchorage.minimum_anchorage_length_mm
    assert anchorage.design_lap_length_mm >= 15.0 * 32.0
    assert cover.nominal_cover_mm == pytest.approx(50.0)
    assert cover.satisfies_nominal_cover



def test_drawing_detailing_supports_explicit_anchorage_geometry_and_end_check() -> None:
    policy = AnchorageDetailingPolicy(
        description="project-approved hooked end detail",
        anchorage_alpha_product=0.8,
        lap_alpha_product=1.0,
    )
    anchorage = anchorage_and_lap_lengths_mm(
        bar_diameter_mm=25.0,
        fyk_mpa=500.0,
        fctd_mpa=1.50,
        anchorage_alpha_product=policy.anchorage_alpha_product,
        lap_alpha_product=policy.lap_alpha_product,
    )
    end = check_end_anchorage_length(
        end_name="left",
        detail_description=policy.description,
        required_length_mm=anchorage.design_anchorage_length_mm,
        available_length_mm=anchorage.design_anchorage_length_mm + 75.0,
    )
    assert end.passes
    assert end.reserve_mm == pytest.approx(75.0)


def test_lap_splice_planner_staggers_groups_without_overlapping_lap_zones() -> None:
    policy = LapSplicePolicy(
        maximum_spliced_fraction=0.50,
        minimum_stagger_pitch_mm=600.0,
    )
    plan = plan_staggered_lap_splices(
        total_bar_count=8,
        design_lap_length_mm=900.0,
        policy=policy,
    )
    assert plan.group_bar_counts == (4, 4)
    assert plan.maximum_simultaneous_spliced_fraction == pytest.approx(0.50)
    assert plan.stagger_pitch_mm == pytest.approx(900.0)
    assert plan.total_splice_zone_length_mm == pytest.approx(1800.0)


def test_longitudinal_cage_fit_and_continuous_core_are_explicit() -> None:
    arrangement = select_longitudinal_bar_arrangement(
        required_area_mm2=6200.0,
        web_width_mm=300.0,
        cover_mm=50.0,
        link_diameter_mm=12.0,
    )
    fit = check_longitudinal_cage_fit(
        arrangement=arrangement,
        section_total_depth_mm=1200.0,
        cover_mm=50.0,
        link_diameter_mm=12.0,
    )
    core = continuous_bar_core_plan(
        required_continuous_area_mm2=1200.0,
        bar_diameter_mm=arrangement.bar_diameter_mm,
        governing_arrangement_bar_count=arrangement.bar_count,
    )
    assert fit.passes
    assert core.bar_count >= 2
    assert core.provided_area_mm2 >= 1200.0
