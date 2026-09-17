from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.research.lm1_grillage_benchmark import (
    GrillageEnvelopeTolerance,
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
    compare_lm1_external_grillage_case,
)


@dataclass(frozen=True)
class LM1ExternalBenchmarkSuiteReport:
    """Aggregate comparison status for a governing LM1 benchmark suite."""

    source_name: str
    case_reports: tuple[LM1ExternalGrillageBenchmarkReport, ...]
    missing_case_ids: tuple[int, ...]
    unexpected_case_ids: tuple[int, ...]

    @property
    def passes(self) -> bool:
        return (
            bool(self.case_reports)
            and not self.missing_case_ids
            and not self.unexpected_case_ids
            and all(report.passes for report in self.case_reports)
        )

    @property
    def failed_case_ids(self) -> tuple[int, ...]:
        return tuple(report.case_id for report in self.case_reports if not report.passes)


def compare_lm1_external_grillage_suite(
    suite: LM1GoverningBenchmarkSuite,
    *,
    external_results_by_case_id: dict[int, str],
    source_name: str,
    tolerance: GrillageEnvelopeTolerance | None = None,
) -> LM1ExternalBenchmarkSuiteReport:
    """Compare all governing native LM1 cases against one external solver export set.

    ``external_results_by_case_id`` contains normalized external-result CSV text keyed
    by the governing case ID. Missing and unexpected case IDs are retained explicitly
    so a partially executed MIDAS/STAAD benchmark cannot accidentally be reported as
    complete.
    """
    if not source_name.strip():
        raise ValueError("External benchmark source_name cannot be empty.")

    cases_by_id = {case.case_id: case for case in suite.cases}
    expected_ids = set(cases_by_id)
    supplied_ids = set(external_results_by_case_id)
    missing = tuple(sorted(expected_ids - supplied_ids))
    unexpected = tuple(sorted(supplied_ids - expected_ids))

    reports = tuple(
        compare_lm1_external_grillage_case(
            cases_by_id[case_id],
            external_results_csv=external_results_by_case_id[case_id],
            source_name=source_name,
            tolerance=tolerance,
        )
        for case_id in sorted(expected_ids & supplied_ids)
    )
    return LM1ExternalBenchmarkSuiteReport(
        source_name=source_name,
        case_reports=reports,
        missing_case_ids=missing,
        unexpected_case_ids=unexpected,
    )
