from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.research.lm1_benchmark_reporting import (
    LM1BenchmarkReportingPackage,
    build_lm1_external_benchmark_reporting_package,
)
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_external_adapters import (
    compare_lm1_midas_member_force_table_case,
    compare_lm1_staad_anl_case,
)
from rc_bridge.research.lm1_grillage_benchmark import (
    GrillageEnvelopeTolerance,
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
)


@dataclass(frozen=True)
class LM1ExternalBenchmarkWorkflowResult:
    """Complete source-specific external comparison plus engineering report bundle."""

    suite_report: LM1ExternalBenchmarkSuiteReport
    reporting_package: LM1BenchmarkReportingPackage

    @property
    def passes(self) -> bool:
        return self.suite_report.passes


def _assemble_suite_report(
    suite: LM1GoverningBenchmarkSuite,
    *,
    case_reports: tuple[LM1ExternalGrillageBenchmarkReport, ...],
    supplied_case_ids: set[int],
    source_name: str,
    tolerance: GrillageEnvelopeTolerance,
) -> LM1ExternalBenchmarkSuiteReport:
    expected_case_ids = {case.case_id for case in suite.cases}
    return LM1ExternalBenchmarkSuiteReport(
        source_name=source_name,
        case_reports=tuple(sorted(case_reports, key=lambda item: item.case_id)),
        missing_case_ids=tuple(sorted(expected_case_ids - supplied_case_ids)),
        unexpected_case_ids=tuple(sorted(supplied_case_ids - expected_case_ids)),
        tolerance=tolerance,
    )


def run_lm1_staad_benchmark_workflow(
    suite: LM1GoverningBenchmarkSuite,
    *,
    staad_anl_by_case_id: dict[int, str],
    tolerance: GrillageEnvelopeTolerance | None = None,
    source_name: str = "STAAD.Pro",
    report_title: str = "LM1 Grillage STAAD.Pro Benchmark Verification",
) -> LM1ExternalBenchmarkWorkflowResult:
    """Compare all supplied STAAD ANL governing cases and build the final report bundle."""
    if not source_name.strip():
        raise ValueError("STAAD benchmark source_name cannot be empty.")
    policy = tolerance or GrillageEnvelopeTolerance()
    cases_by_id = {case.case_id: case for case in suite.cases}
    supplied_ids = set(staad_anl_by_case_id)

    reports = tuple(
        compare_lm1_staad_anl_case(
            cases_by_id[case_id],
            staad_anl_text=staad_anl_by_case_id[case_id],
            tolerance=policy,
            source_name=source_name,
        )
        for case_id in sorted(set(cases_by_id) & supplied_ids)
    )
    suite_report = _assemble_suite_report(
        suite,
        case_reports=reports,
        supplied_case_ids=supplied_ids,
        source_name=source_name,
        tolerance=policy,
    )
    reporting = build_lm1_external_benchmark_reporting_package(
        suite,
        suite_report,
        title=report_title,
    )
    return LM1ExternalBenchmarkWorkflowResult(
        suite_report=suite_report,
        reporting_package=reporting,
    )


def run_lm1_midas_benchmark_workflow(
    suite: LM1GoverningBenchmarkSuite,
    *,
    member_force_tables_by_case_id: dict[int, str],
    tolerance: GrillageEnvelopeTolerance | None = None,
    source_name: str = "MIDAS Civil",
    report_title: str = "LM1 Grillage MIDAS Civil Benchmark Verification",
    delimiter: str = ",",
    vertical_shear_column: str = "Shear-z",
    vertical_bending_column: str = "Moment-y",
    torsion_column: str = "Torsion",
) -> LM1ExternalBenchmarkWorkflowResult:
    """Compare all supplied MIDAS governing cases and build the final report bundle."""
    if not source_name.strip():
        raise ValueError("MIDAS benchmark source_name cannot be empty.")
    policy = tolerance or GrillageEnvelopeTolerance()
    cases_by_id = {case.case_id: case for case in suite.cases}
    supplied_ids = set(member_force_tables_by_case_id)

    reports = tuple(
        compare_lm1_midas_member_force_table_case(
            cases_by_id[case_id],
            member_force_table=member_force_tables_by_case_id[case_id],
            tolerance=policy,
            source_name=source_name,
            delimiter=delimiter,
            vertical_shear_column=vertical_shear_column,
            vertical_bending_column=vertical_bending_column,
            torsion_column=torsion_column,
        )
        for case_id in sorted(set(cases_by_id) & supplied_ids)
    )
    suite_report = _assemble_suite_report(
        suite,
        case_reports=reports,
        supplied_case_ids=supplied_ids,
        source_name=source_name,
        tolerance=policy,
    )
    reporting = build_lm1_external_benchmark_reporting_package(
        suite,
        suite_report,
        title=report_title,
    )
    return LM1ExternalBenchmarkWorkflowResult(
        suite_report=suite_report,
        reporting_package=reporting,
    )
