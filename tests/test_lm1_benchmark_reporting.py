from types import SimpleNamespace

from rc_bridge.research.lm1_benchmark_reporting import (
    build_lm1_external_benchmark_reporting_package,
)
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    GrillageEnvelopeComponentComparison,
    GrillageEnvelopeTolerance,
    LM1ExternalGrillageBenchmarkReport,
)


def _suite(*case_ids: int):
    cases = tuple(
        SimpleNamespace(
            case_id=case_id,
            governing_usage_csv=(
                "girder_index,governing_component\n"
                f"{case_id},M\n"
                f"{case_id + 1},V\n"
            ),
        )
        for case_id in case_ids
    )
    return SimpleNamespace(cases=cases)


def _comparison(
    *,
    girder: int,
    component: str,
    native: float,
    external: float,
    passes: bool,
) -> GrillageEnvelopeComponentComparison:
    difference = abs(native - external)
    scale = max(abs(native), abs(external))
    relative = None if scale <= 1.0e-12 else difference / scale
    return GrillageEnvelopeComponentComparison(
        girder_index=girder,
        component=component,
        native_value=native,
        external_value=external,
        absolute_difference=difference,
        relative_difference=relative,
        passes=passes,
    )


def test_reporting_package_contains_engineering_summary_and_machine_files() -> None:
    case_report = LM1ExternalGrillageBenchmarkReport(
        case_id=2,
        source_name="MIDAS Civil",
        comparisons=(
            _comparison(
                girder=2,
                component="M",
                native=1000.0,
                external=990.0,
                passes=True,
            ),
            _comparison(
                girder=3,
                component="V",
                native=250.0,
                external=247.5,
                passes=True,
            ),
        ),
    )
    suite_report = LM1ExternalBenchmarkSuiteReport(
        source_name="MIDAS Civil",
        case_reports=(case_report,),
        missing_case_ids=(),
        unexpected_case_ids=(),
        tolerance=GrillageEnvelopeTolerance(
            relative_tolerance=0.015,
            absolute_moment_knm=0.2,
            absolute_shear_kn=0.3,
            absolute_torsion_knm=0.4,
        ),
    )

    package = build_lm1_external_benchmark_reporting_package(
        _suite(2),
        suite_report,
    )

    assert "**Overall status:** PASS" in package.summary_markdown
    assert "**Benchmark completeness:** COMPLETE" in package.summary_markdown
    assert "G2:M" in package.summary_markdown
    assert "G3:V" in package.summary_markdown
    assert "<= 1.5%" in package.summary_markdown
    assert "case_id,status,governing_usage" in package.case_summary_csv
    assert "2,PASS,G2:M;G3:V" in package.case_summary_csv
    assert "relative_difference_percent" in package.component_comparisons_csv
    assert '"overall_status": "PASS"' in package.manifest_json

    files = package.files("midas_lm1")
    assert set(files) == {
        "midas_lm1_summary.md",
        "midas_lm1_cases.csv",
        "midas_lm1_comparisons.csv",
        "midas_lm1_manifest.json",
    }


def test_reporting_package_surfaces_failures_missing_and_unexpected_cases() -> None:
    failed_report = LM1ExternalGrillageBenchmarkReport(
        case_id=1,
        source_name="STAAD.Pro",
        comparisons=(
            _comparison(
                girder=1,
                component="T",
                native=25.0,
                external=30.0,
                passes=False,
            ),
        ),
    )
    suite_report = LM1ExternalBenchmarkSuiteReport(
        source_name="STAAD.Pro",
        case_reports=(failed_report,),
        missing_case_ids=(3,),
        unexpected_case_ids=(99,),
    )

    package = build_lm1_external_benchmark_reporting_package(
        _suite(1, 3),
        suite_report,
    )

    assert "**Overall status:** FAIL" in package.summary_markdown
    assert "**Benchmark completeness:** INCOMPLETE" in package.summary_markdown
    assert "**Missing required cases:** 3" in package.summary_markdown
    assert "**Unexpected supplied cases:** 99" in package.summary_markdown
    assert "| 1 | G1:M, G2:V | FAIL | G1:T |" in package.summary_markdown
    assert "3,MISSING" in package.case_summary_csv
    assert "99,UNEXPECTED" in package.case_summary_csv
    assert '"failed_case_ids": [' in package.manifest_json
    assert '"missing_case_ids": [' in package.manifest_json


def test_reporting_package_rejects_case_reports_outside_suite() -> None:
    case_report = LM1ExternalGrillageBenchmarkReport(
        case_id=7,
        source_name="MIDAS Civil",
        comparisons=(
            _comparison(
                girder=1,
                component="M",
                native=1.0,
                external=1.0,
                passes=True,
            ),
        ),
    )
    suite_report = LM1ExternalBenchmarkSuiteReport(
        source_name="MIDAS Civil",
        case_reports=(case_report,),
        missing_case_ids=(),
        unexpected_case_ids=(),
    )

    try:
        build_lm1_external_benchmark_reporting_package(_suite(2), suite_report)
    except ValueError as exc:
        assert "non-suite case IDs: 7" in str(exc)
    else:
        raise AssertionError("Expected reporting package to reject non-suite case ID.")
