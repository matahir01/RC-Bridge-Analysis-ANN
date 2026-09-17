import csv
import io

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.research.lm1_external_adapters import (
    compare_lm1_midas_member_force_table_case,
)
from rc_bridge.research.lm1_grillage_benchmark import (
    build_lm1_governing_benchmark_suite,
    compare_lm1_external_grillage_case,
    external_grillage_envelope_from_normalized_results,
)
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import run_project_native_lm1_grillage_search


def _project() -> ProjectInput:
    return ProjectInput(
        name="LM1 external benchmark",
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=8,
            girder_spacing_m=1.40,
        ),
    )


def _longitudinal() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.025,
        iy_m4=0.05,
        iz_m4=0.08,
    )


def _transverse() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.012,
        iy_m4=0.018,
        iz_m4=0.025,
    )


def _search():
    return run_project_native_lm1_grillage_search(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=15.0,
    )


def _scale_moments(text: str, factor: float) -> str:
    reader = csv.DictReader(io.StringIO(text))
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in reader:
        if row["result_type"] == "member_end_force" and row["component"] == "M_VERTICAL":
            row["value"] = format(float(row["value"]) * factor, ".17g")
        writer.writerow(row)
    return stream.getvalue()


def _midas_member_force_table(case) -> str:
    reader = csv.DictReader(io.StringIO(case.native_expected_results_csv))
    values: dict[tuple[str, str], dict[str, str]] = {}
    for row in reader:
        if row["result_type"] != "member_end_force":
            continue
        key = (row["object_id"], row["position_m"])
        values.setdefault(key, {})[row["component"]] = row["value"]

    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["Elem", "Part", "Load", "Shear-z", "Moment-y", "Torsion"])
    load_case = case.case.model.load_cases[0].name
    for (member_id, end), components in sorted(
        values.items(),
        key=lambda item: (int(item[0][0]), item[0][1]),
    ):
        writer.writerow(
            [
                member_id,
                end,
                load_case,
                components["V_VERTICAL"],
                components["M_VERTICAL"],
                components["T"],
            ]
        )
    return stream.getvalue()


def test_governing_search_builds_one_external_package_per_unique_governing_case() -> None:
    search = _search()
    suite = build_lm1_governing_benchmark_suite(search)

    assert tuple(case.case_id for case in suite.cases) == search.governing_case_ids
    assert suite.cases
    for case in suite.cases:
        files = case.files()
        assert any(name.endswith(".mct") for name in files)
        assert any(name.endswith(".std") for name in files)
        assert any(name.endswith("_native_expected_results.csv") for name in files)
        assert any(name.endswith("_native_expected_girder_envelope.csv") for name in files)
        assert any(name.endswith("_governing_usage.csv") for name in files)


def test_native_normalized_result_round_trip_reproduces_per_girder_envelope() -> None:
    suite = build_lm1_governing_benchmark_suite(_search())
    case = suite.cases[0]

    external = external_grillage_envelope_from_normalized_results(
        case.case.model,
        case.native_expected_results_csv,
        source_name="native round trip",
    )
    native = case.case.girder_envelope.envelope

    assert external.girder_count == native.girder_count
    for girder_index in range(1, native.girder_count + 1):
        assert external.effect_for_girder(girder_index) == native.effect_for_girder(girder_index)


def test_external_benchmark_report_passes_exact_round_trip_and_detects_moment_error() -> None:
    suite = build_lm1_governing_benchmark_suite(_search())
    case = suite.cases[0]

    exact = compare_lm1_external_grillage_case(
        case,
        external_results_csv=case.native_expected_results_csv,
        source_name="native round trip",
    )
    assert exact.passes

    changed = compare_lm1_external_grillage_case(
        case,
        external_results_csv=_scale_moments(case.native_expected_results_csv, 1.25),
        source_name="perturbed external solver",
    )
    assert not changed.passes
    assert any(item.endswith(" M") for item in changed.failed_components)


def test_midas_member_force_adapter_round_trips_native_member_results() -> None:
    suite = build_lm1_governing_benchmark_suite(_search())
    case = suite.cases[0]

    report = compare_lm1_midas_member_force_table_case(
        case,
        member_force_table=_midas_member_force_table(case),
        source_name="MIDAS-format native round trip",
    )

    assert report.passes
