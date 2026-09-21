import pytest

from rc_bridge.research.code_reference_benchmarks import (
    JRC_BEAM_LINK_SPACING,
    JRC_EC2_SLAB_SHEAR,
    JRC_LM1_CHARACTERISTIC_VALUES,
    JRC_RECTANGULAR_FLEXURE,
    JRC_ROAD_BRIDGE_COMBINATION_FACTORS,
    eurocode_v1_published_reference_benchmarks,
    jrc_beam_link_spacing_benchmark,
    jrc_ec2_slab_shear_benchmark,
    jrc_lm1_characteristic_values_benchmark,
    jrc_rectangular_flexure_benchmark,
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
        JRC_ROAD_BRIDGE_COMBINATION_FACTORS,
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

    assert len(reports) == 5
    assert all(report.passes for report in reports)
    assert {report.source_name for report in reports} == {
        JRC_LM1_CHARACTERISTIC_VALUES.source_name,
        JRC_ROAD_BRIDGE_COMBINATION_FACTORS.source_name,
        JRC_EC2_SLAB_SHEAR.source_name,
        JRC_RECTANGULAR_FLEXURE.source_name,
        JRC_BEAM_LINK_SPACING.source_name,
    }
