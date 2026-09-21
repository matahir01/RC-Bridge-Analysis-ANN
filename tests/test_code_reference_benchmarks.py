import pytest

from rc_bridge.research.code_reference_benchmarks import (
    JRC_BEAM_LINK_SPACING,
    JRC_RECTANGULAR_FLEXURE,
    eurocode_v1_published_reference_benchmarks,
    jrc_beam_link_spacing_benchmark,
    jrc_rectangular_flexure_benchmark,
)
from rc_bridge.research.verification import SolverProfile


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
    assert steel.calculated_value == pytest.approx(932.833, abs=0.01)
    assert resistance.target.reference_value == pytest.approx(62.78)
    assert resistance.calculated_value == pytest.approx(62.790, abs=0.001)


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
    for evidence in (JRC_RECTANGULAR_FLEXURE, JRC_BEAM_LINK_SPACING):
        assert evidence.source_name
        assert evidence.source_reference
        assert evidence.source_url.startswith("https://")
        assert "only" in evidence.scope.lower()

    assert "rectangular" in JRC_RECTANGULAR_FLEXURE.scope.lower()
    assert "spacing" in JRC_BEAM_LINK_SPACING.scope.lower()


def test_published_reference_suite_contains_both_independent_reports() -> None:
    reports = eurocode_v1_published_reference_benchmarks()

    assert len(reports) == 2
    assert all(report.passes for report in reports)
    assert {report.source_name for report in reports} == {
        JRC_RECTANGULAR_FLEXURE.source_name,
        JRC_BEAM_LINK_SPACING.source_name,
    }
