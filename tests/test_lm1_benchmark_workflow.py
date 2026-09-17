from types import SimpleNamespace

from rc_bridge.research import lm1_benchmark_workflow as workflow
from rc_bridge.research.lm1_grillage_benchmark import (
    GrillageEnvelopeComponentComparison,
    GrillageEnvelopeTolerance,
    LM1ExternalGrillageBenchmarkReport,
)


def _suite(*case_ids: int):
    return SimpleNamespace(
        cases=tuple(
            SimpleNamespace(
                case_id=case_id,
                governing_usage_csv=(
                    "girder_index,governing_component\n"
                    f"{case_id},M\n"
                ),
            )
            for case_id in case_ids
        )
    )


def _report(case_id: int, source_name: str) -> LM1ExternalGrillageBenchmarkReport:
    comparison = GrillageEnvelopeComponentComparison(
        girder_index=case_id,
        component="M",
        native_value=100.0,
        external_value=99.0,
        absolute_difference=1.0,
        relative_difference=0.01,
        passes=True,
    )
    return LM1ExternalGrillageBenchmarkReport(
        case_id=case_id,
        source_name=source_name,
        comparisons=(comparison,),
    )


def test_staad_workflow_compares_complete_suite_and_builds_reporting(monkeypatch) -> None:
    calls: list[tuple[int, str]] = []

    def fake_compare(case, *, staad_anl_text, source_name, **_):
        calls.append((case.case_id, staad_anl_text))
        return _report(case.case_id, source_name)

    monkeypatch.setattr(workflow, "compare_lm1_staad_anl_case", fake_compare)

    result = workflow.run_lm1_staad_benchmark_workflow(
        _suite(1, 3),
        staad_anl_by_case_id={3: "anl-3", 1: "anl-1"},
    )

    assert calls == [(1, "anl-1"), (3, "anl-3")]
    assert result.passes
    assert result.suite_report.missing_case_ids == ()
    assert result.suite_report.unexpected_case_ids == ()
    assert "**Overall status:** PASS" in result.reporting_package.summary_markdown
    assert "STAAD.Pro" in result.reporting_package.summary_markdown


def test_midas_workflow_surfaces_missing_and_unexpected_case_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow,
        "compare_lm1_midas_member_force_table_case",
        lambda case, source_name, **_: _report(case.case_id, source_name),
    )

    result = workflow.run_lm1_midas_benchmark_workflow(
        _suite(2, 5),
        member_force_tables_by_case_id={2: "table-2", 99: "extra"},
    )

    assert not result.passes
    assert result.suite_report.missing_case_ids == (5,)
    assert result.suite_report.unexpected_case_ids == (99,)
    assert "**Missing required cases:** 5" in result.reporting_package.summary_markdown
    assert "**Unexpected supplied cases:** 99" in result.reporting_package.summary_markdown


def test_external_workflow_retains_custom_tolerance(monkeypatch) -> None:
    monkeypatch.setattr(
        workflow,
        "compare_lm1_staad_anl_case",
        lambda case, source_name, **_: _report(case.case_id, source_name),
    )
    policy = GrillageEnvelopeTolerance(
        relative_tolerance=0.01,
        absolute_moment_knm=0.25,
        absolute_shear_kn=0.5,
        absolute_torsion_knm=0.75,
    )

    result = workflow.run_lm1_staad_benchmark_workflow(
        _suite(4),
        staad_anl_by_case_id={4: "anl"},
        tolerance=policy,
    )

    assert result.suite_report.tolerance is policy
    assert "<= 1%" in result.reporting_package.summary_markdown
    assert "<= 0.25 kNm" in result.reporting_package.summary_markdown
