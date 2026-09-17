from types import SimpleNamespace

from rc_bridge.research import lm1_benchmark_runner as runner
from rc_bridge.research.lm1_grillage_benchmark import LM1ExternalGrillageBenchmarkReport


def _suite(*case_ids: int):
    return SimpleNamespace(cases=tuple(SimpleNamespace(case_id=value) for value in case_ids))


def _report(case_id: int, *, passes: bool) -> LM1ExternalGrillageBenchmarkReport:
    comparison = SimpleNamespace(passes=passes)
    return LM1ExternalGrillageBenchmarkReport(
        case_id=case_id,
        source_name="external",
        comparisons=(comparison,),
    )


def test_suite_runner_requires_complete_case_set(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "compare_lm1_external_grillage_case",
        lambda case, **_: _report(case.case_id, passes=True),
    )
    result = runner.compare_lm1_external_grillage_suite(
        _suite(2, 5),
        external_results_by_case_id={2: "csv", 99: "extra"},
        source_name="MIDAS Civil",
    )

    assert result.missing_case_ids == (5,)
    assert result.unexpected_case_ids == (99,)
    assert result.failed_case_ids == ()
    assert not result.passes


def test_suite_runner_passes_only_when_every_case_passes(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "compare_lm1_external_grillage_case",
        lambda case, **_: _report(case.case_id, passes=case.case_id != 5),
    )
    result = runner.compare_lm1_external_grillage_suite(
        _suite(2, 5),
        external_results_by_case_id={2: "csv", 5: "csv"},
        source_name="STAAD.Pro",
    )

    assert result.missing_case_ids == ()
    assert result.unexpected_case_ids == ()
    assert result.failed_case_ids == (5,)
    assert not result.passes


def test_suite_runner_accepts_complete_passing_set(monkeypatch) -> None:
    monkeypatch.setattr(
        runner,
        "compare_lm1_external_grillage_case",
        lambda case, **_: _report(case.case_id, passes=True),
    )
    result = runner.compare_lm1_external_grillage_suite(
        _suite(1, 3),
        external_results_by_case_id={3: "csv", 1: "csv"},
        source_name="MIDAS Civil",
    )

    assert [report.case_id for report in result.case_reports] == [1, 3]
    assert result.passes
