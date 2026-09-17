import pytest

from rc_bridge.research.benchmarking import (
    BenchmarkTarget,
    build_independent_benchmark_report,
    compare_benchmark_value,
)
from rc_bridge.research.verification import SolverProfile


def test_relative_tolerance_benchmark_passes_and_reports_error() -> None:
    target = BenchmarkTarget(
        name="internal support moment",
        reference_value=-250.0,
        unit="kN m",
        relative_tolerance=0.01,
        location="support 2",
    )
    result = compare_benchmark_value(target, calculated_value=-248.0)

    assert result.signed_error == pytest.approx(2.0)
    assert result.absolute_error == pytest.approx(2.0)
    assert result.relative_error == pytest.approx(0.008)
    assert result.allowable_absolute_error == pytest.approx(2.5)
    assert result.passes is True


def test_absolute_tolerance_handles_near_zero_reference() -> None:
    target = BenchmarkTarget(
        name="support vertical displacement",
        reference_value=0.0,
        unit="mm",
        relative_tolerance=0.01,
        absolute_tolerance=0.05,
    )
    result = compare_benchmark_value(target, calculated_value=0.03)

    assert result.relative_error is None
    assert result.allowable_absolute_error == pytest.approx(0.05)
    assert result.passes is True


def test_benchmark_report_collects_failures_without_unlocking_solver() -> None:
    report = build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        source_name="external structural model",
        source_reference="benchmark-case-A",
        observations=(
            (
                BenchmarkTarget(
                    name="midspan sagging moment",
                    reference_value=140.0,
                    unit="kN m",
                    relative_tolerance=0.02,
                ),
                141.0,
            ),
            (
                BenchmarkTarget(
                    name="midspan deflection",
                    reference_value=-5.0,
                    unit="mm",
                    relative_tolerance=0.02,
                    absolute_tolerance=0.05,
                ),
                -5.25,
            ),
        ),
    )

    assert report.solver_profile == SolverProfile.EUROCODE_CONTINUOUS
    assert report.passes is False
    assert report.failed_target_names == ("midspan deflection",)
    assert report.maximum_relative_error == pytest.approx(0.05)


def test_benchmark_target_requires_traceable_tolerance() -> None:
    with pytest.raises(ValueError, match="tolerance"):
        BenchmarkTarget(
            name="reaction",
            reference_value=100.0,
            unit="kN",
        )
