from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
)


@dataclass(frozen=True)
class LM1BenchmarkReportingPackage:
    """Human- and machine-readable reporting bundle for one external LM1 benchmark."""

    summary_markdown: str
    case_summary_csv: str
    component_comparisons_csv: str
    manifest_json: str

    def files(self, stem: str = "lm1_external_benchmark") -> dict[str, str]:
        if not stem.strip():
            raise ValueError("LM1 benchmark report file stem cannot be empty.")
        return {
            f"{stem}_summary.md": self.summary_markdown,
            f"{stem}_cases.csv": self.case_summary_csv,
            f"{stem}_comparisons.csv": self.component_comparisons_csv,
            f"{stem}_manifest.json": self.manifest_json,
        }


def _governing_usage_by_case(
    suite: LM1GoverningBenchmarkSuite,
) -> dict[int, tuple[str, ...]]:
    usage: dict[int, tuple[str, ...]] = {}
    for case in suite.cases:
        stream = io.StringIO(case.governing_usage_csv)
        reader = csv.DictReader(stream)
        labels: list[str] = []
        for row in reader:
            girder = str(row.get("girder_index", "")).strip()
            component = str(row.get("governing_component", "")).strip()
            if girder and component:
                labels.append(f"G{girder}:{component}")
        usage[case.case_id] = tuple(labels)
    return usage


def _failed_component_labels(report: LM1ExternalGrillageBenchmarkReport) -> tuple[str, ...]:
    return tuple(
        f"G{item.girder_index}:{item.component}"
        for item in report.comparisons
        if not item.passes
    )


def _max_relative_percent(report: LM1ExternalGrillageBenchmarkReport) -> float | None:
    values = [
        float(item.relative_difference) * 100.0
        for item in report.comparisons
        if item.relative_difference is not None
    ]
    return max(values) if values else None


def _max_absolute_difference(
    report: LM1ExternalGrillageBenchmarkReport,
    component: str,
) -> float:
    values = [
        float(item.absolute_difference)
        for item in report.comparisons
        if item.component == component
    ]
    return max(values, default=0.0)


def _format_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4g}%"


def _case_summary_csv(
    suite: LM1GoverningBenchmarkSuite,
    report: LM1ExternalBenchmarkSuiteReport,
) -> str:
    usage = _governing_usage_by_case(suite)
    reports_by_id = {item.case_id: item for item in report.case_reports}
    expected_ids = {case.case_id for case in suite.cases}

    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "case_id",
            "status",
            "governing_usage",
            "comparison_count",
            "failed_components",
            "max_relative_difference_percent",
            "max_abs_moment_knm",
            "max_abs_shear_kn",
            "max_abs_torsion_knm",
        ]
    )
    for case_id in sorted(expected_ids):
        case_report = reports_by_id.get(case_id)
        if case_report is None:
            writer.writerow(
                [
                    case_id,
                    "MISSING",
                    ";".join(usage.get(case_id, ())),
                    0,
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue
        writer.writerow(
            [
                case_id,
                "PASS" if case_report.passes else "FAIL",
                ";".join(usage.get(case_id, ())),
                len(case_report.comparisons),
                ";".join(_failed_component_labels(case_report)),
                ""
                if _max_relative_percent(case_report) is None
                else format(_max_relative_percent(case_report), ".12g"),
                format(_max_absolute_difference(case_report, "M"), ".12g"),
                format(_max_absolute_difference(case_report, "V"), ".12g"),
                format(_max_absolute_difference(case_report, "T"), ".12g"),
            ]
        )

    for case_id in report.unexpected_case_ids:
        writer.writerow([case_id, "UNEXPECTED", "", 0, "", "", "", "", ""])
    return stream.getvalue()


def _component_comparisons_csv(report: LM1ExternalBenchmarkSuiteReport) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "case_id",
            "source_name",
            "girder_index",
            "component",
            "native_value",
            "external_value",
            "absolute_difference",
            "relative_difference_percent",
            "status",
        ]
    )
    for case_report in sorted(report.case_reports, key=lambda item: item.case_id):
        for item in case_report.comparisons:
            writer.writerow(
                [
                    case_report.case_id,
                    report.source_name,
                    item.girder_index,
                    item.component,
                    format(float(item.native_value), ".17g"),
                    format(float(item.external_value), ".17g"),
                    format(float(item.absolute_difference), ".17g"),
                    ""
                    if item.relative_difference is None
                    else format(float(item.relative_difference) * 100.0, ".12g"),
                    "PASS" if item.passes else "FAIL",
                ]
            )
    return stream.getvalue()


def _summary_markdown(
    suite: LM1GoverningBenchmarkSuite,
    report: LM1ExternalBenchmarkSuiteReport,
    *,
    title: str,
) -> str:
    usage = _governing_usage_by_case(suite)
    reports_by_id = {item.case_id: item for item in report.case_reports}
    expected_ids = tuple(sorted(case.case_id for case in suite.cases))
    passed_count = sum(item.passes for item in report.case_reports)
    failed_count = len(report.failed_case_ids)
    completeness = "COMPLETE" if not report.missing_case_ids else "INCOMPLETE"
    overall = "PASS" if report.passes else "FAIL"
    tolerance = report.tolerance

    lines = [
        f"# {title}",
        "",
        f"**External solver:** {report.source_name}",
        f"**Overall status:** {overall}",
        f"**Benchmark completeness:** {completeness}",
        (
            f"**Cases:** {len(expected_ids)} required; {len(report.case_reports)} compared; "
            f"{passed_count} passed; {failed_count} failed."
        ),
        "",
        "## Acceptance tolerances",
        "",
        "| Quantity | Acceptance |",
        "| --- | ---: |",
        f"| Relative difference | <= {100.0 * tolerance.relative_tolerance:.4g}% |",
        f"| Absolute moment difference | <= {tolerance.absolute_moment_knm:.6g} kNm |",
        f"| Absolute shear difference | <= {tolerance.absolute_shear_kn:.6g} kN |",
        f"| Absolute torsion difference | <= {tolerance.absolute_torsion_knm:.6g} kNm |",
        "",
        (
            "A component passes when either its relative or component-specific absolute "
            "difference is within the stated tolerance."
        ),
        "",
        "## Governing LM1 case verification",
        "",
        "| Case | Governing use | Status | Failed components | Max relative difference |",
        "| ---: | --- | --- | --- | ---: |",
    ]

    for case_id in expected_ids:
        case_report = reports_by_id.get(case_id)
        governing = ", ".join(usage.get(case_id, ())) or "-"
        if case_report is None:
            lines.append(f"| {case_id} | {governing} | MISSING | - | - |")
            continue
        failed = ", ".join(_failed_component_labels(case_report)) or "-"
        lines.append(
            f"| {case_id} | {governing} | "
            f"{'PASS' if case_report.passes else 'FAIL'} | {failed} | "
            f"{_format_percent(_max_relative_percent(case_report))} |"
        )

    if report.missing_case_ids:
        lines.extend(
            [
                "",
                "**Missing required cases:** "
                + ", ".join(str(value) for value in report.missing_case_ids),
            ]
        )
    if report.unexpected_case_ids:
        lines.extend(
            [
                "",
                "**Unexpected supplied cases:** "
                + ", ".join(str(value) for value in report.unexpected_case_ids),
            ]
        )

    lines.extend(
        [
            "",
            "## Detailed discrepancies",
            "",
        ]
    )
    failed_items = [
        (case_report.case_id, item)
        for case_report in report.case_reports
        for item in case_report.comparisons
        if not item.passes
    ]
    if not failed_items:
        lines.append("No component-level tolerance failures were recorded.")
    else:
        lines.extend(
            [
                "| Case | Girder | Component | Native | External | Absolute diff. | Relative diff. |",
                "| ---: | ---: | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for case_id, item in failed_items:
            lines.append(
                f"| {case_id} | {item.girder_index} | {item.component} | "
                f"{float(item.native_value):.6g} | {float(item.external_value):.6g} | "
                f"{float(item.absolute_difference):.6g} | "
                f"{_format_percent(None if item.relative_difference is None else float(item.relative_difference) * 100.0)} |"
            )

    lines.extend(
        [
            "",
            (
                "This report verifies numerical agreement for the governing LM1 grillage cases "
                "included in the benchmark suite. Model equivalence, loading equivalence, and "
                "result-axis interpretation should also be confirmed before treating an external "
                "comparison as final engineering validation."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_json(
    suite: LM1GoverningBenchmarkSuite,
    report: LM1ExternalBenchmarkSuiteReport,
) -> str:
    expected_ids = tuple(sorted(case.case_id for case in suite.cases))
    payload = {
        "benchmark": "EN 1991-2 LM1 native-versus-external grillage envelope",
        "source_name": report.source_name,
        "overall_status": "PASS" if report.passes else "FAIL",
        "expected_case_ids": expected_ids,
        "compared_case_ids": tuple(sorted(item.case_id for item in report.case_reports)),
        "failed_case_ids": report.failed_case_ids,
        "missing_case_ids": report.missing_case_ids,
        "unexpected_case_ids": report.unexpected_case_ids,
        "tolerance": {
            "relative": report.tolerance.relative_tolerance,
            "absolute_moment_knm": report.tolerance.absolute_moment_knm,
            "absolute_shear_kn": report.tolerance.absolute_shear_kn,
            "absolute_torsion_knm": report.tolerance.absolute_torsion_knm,
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_lm1_external_benchmark_reporting_package(
    suite: LM1GoverningBenchmarkSuite,
    report: LM1ExternalBenchmarkSuiteReport,
    *,
    title: str = "LM1 Grillage External Benchmark Verification",
) -> LM1BenchmarkReportingPackage:
    """Build an auditable summary package for a native-versus-MIDAS/STAAD comparison."""
    if not title.strip():
        raise ValueError("LM1 benchmark report title cannot be empty.")

    expected_ids = [case.case_id for case in suite.cases]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("LM1 benchmark reporting suite contains duplicate case IDs.")

    report_ids = [item.case_id for item in report.case_reports]
    if len(report_ids) != len(set(report_ids)):
        raise ValueError("LM1 benchmark report contains duplicate case reports.")

    expected_set = set(expected_ids)
    compared_set = set(report_ids)
    if not compared_set <= expected_set:
        invalid = ", ".join(str(value) for value in sorted(compared_set - expected_set))
        raise ValueError("LM1 benchmark report contains non-suite case IDs: " + invalid)

    return LM1BenchmarkReportingPackage(
        summary_markdown=_summary_markdown(suite, report, title=title),
        case_summary_csv=_case_summary_csv(suite, report),
        component_comparisons_csv=_component_comparisons_csv(report),
        manifest_json=_manifest_json(suite, report),
    )
