import pytest

from rc_bridge.analysis.girder_effects import GirderEffect
from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    parse_grillage_effects_csv,
)
from rc_bridge.research.grillage_benchmark import (
    GrillageBenchmarkTolerances,
    benchmark_girder_effects_against_grillage,
)
from rc_bridge.research.verification import SolverProfile


def _imported_grillage():
    return parse_grillage_effects_csv(
        "girder_index,moment_knm,shear_kn\n"
        "1,300.0,120.0\n"
        "2,250.0,100.0\n",
        metadata=GrillageImportMetadata(
            source_software="Midas Civil",
            model_name="verification model",
            load_case="LM1 characteristic envelope",
        ),
        expected_girder_count=2,
    )


def test_internal_girder_effects_can_be_benchmarked_against_imported_grillage() -> None:
    calculated = (
        GirderEffect(1, 297.0, 119.0, 0.55, "validated analytical distribution"),
        GirderEffect(2, 253.0, 101.0, 0.45, "validated analytical distribution"),
    )
    report = benchmark_girder_effects_against_grillage(
        calculated,
        _imported_grillage(),
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        tolerances=GrillageBenchmarkTolerances(
            moment_relative_tolerance=0.02,
            shear_relative_tolerance=0.02,
        ),
    )

    assert report.passes is True
    assert report.solver_profile == SolverProfile.EUROCODE_CONTINUOUS
    assert report.source_name == "Midas Civil grillage model"
    assert report.source_reference == "verification model / LM1 characteristic envelope"
    assert len(report.comparisons) == 4
    assert report.failed_target_names == ()
    assert "validated analytical distribution" in report.notes


def test_grillage_benchmark_reports_each_failed_girder_quantity() -> None:
    calculated = (
        GirderEffect(1, 280.0, 119.0, 0.55, "candidate distribution"),
        GirderEffect(2, 253.0, 112.0, 0.45, "candidate distribution"),
    )
    report = benchmark_girder_effects_against_grillage(
        calculated,
        _imported_grillage(),
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        tolerances=GrillageBenchmarkTolerances(
            moment_relative_tolerance=0.02,
            shear_relative_tolerance=0.02,
        ),
    )

    assert report.passes is False
    assert report.failed_target_names == (
        "girder 1 moment",
        "girder 2 shear",
    )


def test_grillage_benchmark_requires_matching_girder_count() -> None:
    with pytest.raises(ValueError, match="girder counts must match"):
        benchmark_girder_effects_against_grillage(
            (GirderEffect(1, 300.0, 120.0, 1.0, "candidate"),),
            _imported_grillage(),
            solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
            tolerances=GrillageBenchmarkTolerances(
                moment_relative_tolerance=0.02,
                shear_relative_tolerance=0.02,
            ),
        )
