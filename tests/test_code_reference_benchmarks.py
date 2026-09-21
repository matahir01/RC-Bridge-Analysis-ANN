import pytest

from rc_bridge.design.eurocode_fatigue import concrete_compression_fatigue_check
from rc_bridge.research.code_reference_benchmarks import (
    JRC_BEAM_LINK_SPACING,
    JRC_CONCRETE_FATIGUE,
    JRC_EC2_SLAB_SHEAR,
    JRC_LM1_CHARACTERISTIC_VALUES,
    JRC_LM1_LANE_SUBDIVISION,
    JRC_RECTANGULAR_FLEXURE,
    JRC_REINFORCEMENT_FATIGUE,
    JRC_ROAD_BRIDGE_COMBINATION_FACTORS,
    eurocode_v1_published_reference_benchmarks,
    jrc_beam_link_spacing_benchmark,
    jrc_concrete_fatigue_benchmark,
    jrc_ec2_slab_shear_benchmark,
    jrc_lm1_characteristic_values_benchmark,
    jrc_lm1_lane_subdivision_benchmark,
    jrc_rectangular_flexure_benchmark,
    jrc_reinforcement_fatigue_benchmark,
    jrc_road_bridge_combination_factors_benchmark,
)
from rc_bridge.research.verification import SolverProfile


def test_jrc_lm1_characteristic_values_reference_case_passes() -> None:
    report = jrc_lm1_characteristic_values_benchmark()

    assert report.source_name == JRC_LM1_CHARACTERISTIC_VALUES.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    assert len(report.comparisons) == 10
    values = {item.target.name: item.calculated_value for item in report.comparisons}
    assert values["LM1 lane 1 tandem axle load"] == pytest.approx(300.0)
    assert values["LM1 lane 1 UDL"] == pytest.approx(9.0)
    assert values["LM1 lane 2 tandem axle load"] == pytest.approx(200.0)
    assert values["LM1 lane 3 tandem axle load"] == pytest.approx(100.0)
    assert values["LM1 remaining-area UDL"] == pytest.approx(2.5)
    assert values["LM1 tandem axle spacing"] == pytest.approx(1.2)


def test_jrc_lm1_lane_subdivision_reference_cases_pass() -> None:
    report = jrc_lm1_lane_subdivision_benchmark()

    assert report.source_name == JRC_LM1_LANE_SUBDIVISION.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    assert len(report.comparisons) == 12
    values = {item.target.name: item.calculated_value for item in report.comparisons}
    assert values["w=5 m lane count"] == pytest.approx(1.0)
    assert values["w=5.8 m lane width"] == pytest.approx(2.9)
    assert values["w=7 m lane count"] == pytest.approx(2.0)
    assert values["w=7 m remaining width"] == pytest.approx(1.0)
    assert values["w=10 m lane count"] == pytest.approx(3.0)


def test_jrc_reinforcement_fatigue_reference_case_passes() -> None:
    report = jrc_reinforcement_fatigue_benchmark()

    assert report.source_name == JRC_REINFORCEMENT_FATIGUE.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    values = {item.target.name: item.calculated_value for item in report.comparisons}
    assert values["reinforcement equivalent stress range"] == pytest.approx(78.32)
    assert values["reinforcement design fatigue resistance"] == pytest.approx(
        141.3043478
    )


def test_jrc_concrete_fatigue_reference_case_matches_strength_range_and_fail_status() -> None:
    report = jrc_concrete_fatigue_benchmark()

    assert report.source_name == JRC_CONCRETE_FATIGUE.source_name
    assert report.passes is True
    assert report.failed_target_names == ()

    low = concrete_compression_fatigue_check(
        sigma_c_max_mpa=11.9,
        sigma_c_min_mpa=3.5,
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=0.85,
        k1=0.85,
        beta_cc_t0=1.10,
    )
    high = concrete_compression_fatigue_check(
        sigma_c_max_mpa=11.9,
        sigma_c_min_mpa=3.5,
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=0.85,
        k1=0.85,
        beta_cc_t0=1.20,
    )
    assert low.fcd_fat_mpa == pytest.approx(15.9479833)
    assert high.fcd_fat_mpa == pytest.approx(17.3978)
    assert low.passes is False
    assert high.passes is False


def test_jrc_road_bridge_combination_reference_case_passes() -> None:
    report = jrc_road_bridge_combination_factors_benchmark()

    assert report.source_name == JRC_ROAD_BRIDGE_COMBINATION_FACTORS.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    values = {item.target.name: item.calculated_value for item in report.comparisons}
    assert values["road-traffic ULS partial factor gamma_Q"] == pytest.approx(1.35)
    assert values["published 1200 kN traffic design force"] == pytest.approx(1620.0)
    assert values["LM1 frequent tandem factor"] == pytest.approx(0.75)
    assert values["LM1 frequent UDL factor"] == pytest.approx(0.40)


def test_jrc_ec2_slab_shear_reference_case_passes() -> None:
    report = jrc_ec2_slab_shear_benchmark()

    assert report.source_name == JRC_EC2_SLAB_SHEAR.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    values = {item.target.name: item.calculated_value for item in report.comparisons}
    assert values["EC2 shear size-effect factor k"] == pytest.approx(1.745356)
    assert values["EC2 longitudinal reinforcement ratio rho_l"] == pytest.approx(
        0.005133333
    )
    assert values["EC2 minimum shear stress v_min"] == pytest.approx(0.477450, abs=1e-6)
    assert values["EC2 governing concrete shear stress"] == pytest.approx(
        0.548556, abs=1e-6
    )
    assert values["EC2 concrete shear resistance V_Rd,c"] == pytest.approx(
        197.480221, abs=1e-6
    )


def test_jrc_rectangular_flexure_reference_case_passes() -> None:
    report = jrc_rectangular_flexure_benchmark()

    assert report.solver_profile is SolverProfile.EUROCODE_1G
    assert report.source_name == JRC_RECTANGULAR_FLEXURE.source_name
    assert report.source_reference == JRC_RECTANGULAR_FLEXURE.source_reference
    assert report.passes is True
    assert report.failed_target_names == ()

    steel = next(
        item
        for item in report.comparisons
        if item.target.name == "required rectangular tension steel"
    )
    resistance = next(
        item
        for item in report.comparisons
        if item.target.name == "moment resistance using published steel area"
    )
    assert steel.target.reference_value == pytest.approx(933.0)
    assert steel.absolute_error < 0.5
    assert steel.calculated_value == pytest.approx(932.685, abs=0.01)
    assert resistance.target.reference_value == pytest.approx(62.78)
    assert resistance.absolute_error < resistance.allowable_absolute_error


def test_jrc_beam_link_spacing_reference_case_passes_published_rounding() -> None:
    report = jrc_beam_link_spacing_benchmark()

    assert report.solver_profile is SolverProfile.EUROCODE_1G
    assert report.source_name == JRC_BEAM_LINK_SPACING.source_name
    assert report.passes is True
    assert report.failed_target_names == ()
    assert len(report.comparisons) == 2
    assert all(item.target.reference_value == pytest.approx(266.0) for item in report.comparisons)
    assert all(item.calculated_value == pytest.approx(265.5) for item in report.comparisons)
    assert all(item.absolute_error == pytest.approx(0.5) for item in report.comparisons)


def test_published_reference_metadata_is_traceable_and_scope_limited() -> None:
    for evidence in (
        JRC_LM1_CHARACTERISTIC_VALUES,
        JRC_LM1_LANE_SUBDIVISION,
        JRC_ROAD_BRIDGE_COMBINATION_FACTORS,
        JRC_REINFORCEMENT_FATIGUE,
        JRC_CONCRETE_FATIGUE,
        JRC_EC2_SLAB_SHEAR,
        JRC_RECTANGULAR_FLEXURE,
        JRC_BEAM_LINK_SPACING,
    ):
        assert evidence.source_name
        assert evidence.source_reference
        assert evidence.source_url.startswith("https://")
        assert "only" in evidence.scope.lower()

    assert "rectangular" in JRC_RECTANGULAR_FLEXURE.scope.lower()
    assert "spacing" in JRC_BEAM_LINK_SPACING.scope.lower()


def test_published_reference_suite_contains_all_independent_reports() -> None:
    reports = eurocode_v1_published_reference_benchmarks()

    assert len(reports) == 8
    assert all(report.passes for report in reports)
    assert {report.source_name for report in reports} == {
        JRC_LM1_CHARACTERISTIC_VALUES.source_name,
        JRC_LM1_LANE_SUBDIVISION.source_name,
        JRC_ROAD_BRIDGE_COMBINATION_FACTORS.source_name,
        JRC_REINFORCEMENT_FATIGUE.source_name,
        JRC_CONCRETE_FATIGUE.source_name,
        JRC_EC2_SLAB_SHEAR.source_name,
        JRC_RECTANGULAR_FLEXURE.source_name,
        JRC_BEAM_LINK_SPACING.source_name,
    }
