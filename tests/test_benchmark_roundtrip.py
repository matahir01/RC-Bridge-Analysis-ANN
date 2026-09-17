import csv
import io

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.research.benchmark_roundtrip import (
    evaluate_continuous_line_campaign,
    evaluate_midas_line_benchmark,
    evaluate_staad_line_benchmark,
)
from rc_bridge.research.benchmark_suite import build_standard_continuous_line_benchmark_suite
from rc_bridge.research.verification_campaign import (
    BenchmarkCaseReview,
    BenchmarkTolerance,
    ExternalBenchmarkPolicy,
)


def _suite():
    project = ProjectInput(
        name="Round trip benchmark",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )
    return build_standard_continuous_line_benchmark_suite(
        project,
        ei_kn_m2_by_span=(1.0e6, 1.0e6),
        analysis_area_m2_by_span=(0.45, 0.45),
    )


def _policy() -> ExternalBenchmarkPolicy:
    return ExternalBenchmarkPolicy(
        tolerances_by_component={
            "FZ": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=1.0e-6),
            "DZ": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=1.0e-9),
            "RY": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=1.0e-9),
        }
    )


def _review() -> BenchmarkCaseReview:
    return BenchmarkCaseReview(
        geometry_equivalent=True,
        boundary_conditions_equivalent=True,
        loading_equivalent=True,
        result_axes_verified=True,
    )


def _expected_by_node(package):
    rows = list(csv.DictReader(io.StringIO(package.external_expected_results_csv)))
    values: dict[int, dict[str, float]] = {}
    for row in rows:
        values.setdefault(int(row["object_id"]), {})[row["component"]] = float(row["value"])
    return values


def _midas_tables(package) -> tuple[str, str]:
    values = _expected_by_node(package)
    load_name = package.verification_model.load_cases[0].name
    reaction = io.StringIO()
    reaction_writer = csv.writer(reaction, lineterminator="\n")
    reaction_writer.writerow(["Node", "Load", "FZ"])
    displacement = io.StringIO()
    displacement_writer = csv.writer(displacement, lineterminator="\n")
    displacement_writer.writerow(["Node", "Load", "DZ", "RY"])
    for node_id, node_values in sorted(values.items()):
        reaction_writer.writerow([node_id, load_name, node_values["FZ"]])
        displacement_writer.writerow(
            [node_id, load_name, node_values["DZ"], node_values["RY"]]
        )
    return reaction.getvalue(), displacement.getvalue()


def _staad_anl(package) -> str:
    values = _expected_by_node(package)
    lines = [
        "JOINT DISPLACEMENT (CM RADIANS) STRUCTURE TYPE = SPACE",
        "JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN",
    ]
    for node_id, node_values in sorted(values.items()):
        lines.append(
            f"{node_id} 1 0 0 {node_values['DZ'] * 100.0:.17g} 0 "
            f"{node_values['RY']:.17g} 0"
        )
    lines.extend(
        [
            "************** END OF LATEST ANALYSIS RESULT **************",
            "SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE",
            "JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z",
        ]
    )
    for node_id, node_values in sorted(values.items()):
        lines.append(f"{node_id} 1 0 0 {node_values['FZ']:.17g} 0 0 0")
    lines.append("************** END OF LATEST ANALYSIS RESULT **************")
    for beam in package.verification_model.beams:
        lines.extend(
            [
                "MEMBER END FORCES STRUCTURE TYPE = SPACE",
                "ALL UNITS ARE -- KNS METE (GLOBAL)",
                "MEMBER LOAD JT FX FY FZ MX MY MZ",
                f"{beam.member_id} 1 {beam.node_i} 0 0 0 0 0 0",
                f"{beam.node_j} 0 0 0 0 0 0",
                "************** END OF LATEST ANALYSIS RESULT **************",
            ]
        )
    return "\n".join(lines) + "\n"


def test_staad_roundtrip_evaluator_accepts_matching_normalized_result_subset() -> None:
    package = _suite().packages[0]
    report = evaluate_staad_line_benchmark(
        package,
        anl_text=_staad_anl(package),
        policy=_policy(),
        review=_review(),
        source_reference="synthetic plumbing fixture",
    )

    assert report.numerical_passes
    assert report.accepted_evidence
    assert report.source_name == "STAAD.Pro"


def test_midas_roundtrip_evaluator_accepts_matching_global_tables() -> None:
    package = _suite().packages[1]
    reaction, displacement = _midas_tables(package)
    report = evaluate_midas_line_benchmark(
        package,
        reaction_table=reaction,
        displacement_table=displacement,
        policy=_policy(),
        review=_review(),
        source_reference="synthetic plumbing fixture",
    )

    assert report.numerical_passes
    assert report.accepted_evidence
    assert report.source_name == "MIDAS Civil"


def test_all_four_case_reports_complete_default_continuous_campaign() -> None:
    reports = []
    for package in _suite().packages:
        reaction, displacement = _midas_tables(package)
        reports.append(
            evaluate_midas_line_benchmark(
                package,
                reaction_table=reaction,
                displacement_table=displacement,
                policy=_policy(),
                review=_review(),
                source_reference="synthetic plumbing fixture only",
            )
        )

    campaign = evaluate_continuous_line_campaign(tuple(reports))
    assert campaign.passes
    assert campaign.failed_case_ids == ()
