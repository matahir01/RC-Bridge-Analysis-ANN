import csv
import json
from io import StringIO

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.export.model_verification_package import build_model_verification_export_package
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1LongitudinalRegion,
    LM1RemainingAreaVerificationPlacement,
    build_project_lm1_grillage_verification_model,
    build_project_lm1_grillage_verification_package,
)


def _section(name: str) -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name=name,
        area_m2=0.50,
        torsion_constant_m4=0.04,
        iy_m4=0.03,
        iz_m4=0.08,
    )


def _package_inputs():
    project = ProjectInput(
        name="LM1 Package Bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=8,
            girder_spacing_m=1.40,
        ),
    )
    full_span = (LM1LongitudinalRegion(0.0, 15.0),)
    lanes = (
        LM1LaneVerificationPlacement(1, -3.5, -0.5, full_span, 5.0),
        LM1LaneVerificationPlacement(2, -0.5, 2.5, full_span, 8.0),
    )
    remaining = (
        LM1RemainingAreaVerificationPlacement(2.5, 3.5, full_span),
    )
    return project, lanes, remaining


def _lm1_model():
    project, lanes, remaining = _package_inputs()
    return build_project_lm1_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )


def _expected_file_names(stem: str) -> set[str]:
    return {
        f"{stem}.mct",
        f"{stem}.std",
        f"{stem}_manifest.json",
        f"{stem}_exported_loads.csv",
        f"{stem}_result_requests.csv",
        f"{stem}_external_results_template.csv",
    }


def test_model_verification_package_contains_midas_staad_manifest_and_exact_loads() -> None:
    package = build_model_verification_export_package(_lm1_model())
    files = package.files("lm1_8_girder_check")

    assert set(files) == _expected_file_names("lm1_8_girder_check")
    assert "*NODE" in package.midas_mct
    assert "*ELEMENT" in package.midas_mct
    assert "JOINT COORDINATES" in package.staad_std
    assert "MEMBER INCIDENCES" in package.staad_std

    manifest = json.loads(package.manifest_json)
    assert manifest["package_type"] == "external_model_verification"
    assert manifest["metadata"]["girder_count"] == "8"
    assert manifest["metadata"]["traffic_model"].startswith("EN 1991-2 LM1")
    assert "no fabricated expected grillage results" in manifest["verification_boundary"]
    assert "expected_results_csv" not in manifest["files"]
    assert "result_requests_csv" in manifest["files"]
    assert "external_results_template_csv" in manifest["files"]


def test_one_call_lm1_package_preserves_source_traffic_placement_metadata() -> None:
    project, lanes, remaining = _package_inputs()
    package = build_project_lm1_grillage_verification_package(
        project,
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    manifest = json.loads(package.manifest_json)
    metadata = manifest["metadata"]
    assert metadata["lm1_lane_strips"] == "lane1:-3.5:-0.5|lane2:-0.5:2.5"
    assert metadata["lm1_tandem_lead_positions_m"] == "lane1:5|lane2:8"
    assert metadata["lm1_lane_udl_regions_m"] == "lane1:0-15|lane2:0-15"
    assert metadata["lm1_remaining_strips"] == "remaining1:2.5:3.5"
    assert metadata["lm1_remaining_udl_regions_m"] == "remaining1:0-15"
    assert set(package.files("lm1_snapshot")) == _expected_file_names("lm1_snapshot")


def test_model_verification_load_csv_matches_final_exported_load_objects() -> None:
    model = _lm1_model()
    package = build_model_verification_export_package(model)
    rows = list(csv.DictReader(StringIO(package.exported_loads_csv)))

    case = model.load_cases[0]
    expected_rows = len(case.uniform_loads) + len(case.point_loads) + len(case.nodal_loads)
    assert len(rows) == expected_rows
    assert {row["load_case"] for row in rows} == {case.name}
    assert {row["load_type"] for row in rows}.issubset(
        {"uniform_member_load", "point_member_load", "nodal_load"}
    )

    exported_vertical_force = 0.0
    for row in rows:
        if row["load_type"] == "point_member_load":
            exported_vertical_force += float(row["magnitude_1"])
        elif row["load_type"] == "nodal_load":
            exported_vertical_force += float(row["fz_kn"])

    model_vertical_force = sum(load.magnitude_kn for load in case.point_loads) + sum(
        load.fz_kn for load in case.nodal_loads
    )
    assert exported_vertical_force == model_vertical_force


def test_result_request_map_covers_reactions_displacements_and_member_end_forces() -> None:
    model = _lm1_model()
    package = build_model_verification_export_package(model)
    rows = list(csv.DictReader(StringIO(package.result_requests_csv)))

    reaction_rows = [row for row in rows if row["result_type"] == "support_reaction"]
    displacement_rows = [row for row in rows if row["result_type"] == "node_displacement"]
    member_rows = [row for row in rows if row["result_type"] == "member_end_force"]

    assert len(reaction_rows) == len(model.supports)
    assert len(displacement_rows) == len(model.nodes)
    assert len(member_rows) == len(model.beams) * 2 * 3
    assert {row["semantic_component"] for row in reaction_rows} == {
        "global_vertical_reaction_FZ"
    }
    assert {row["semantic_component"] for row in displacement_rows} == {
        "global_vertical_displacement_DZ"
    }
    assert {row["semantic_component"] for row in member_rows} == {
        "vertical_plane_shear",
        "vertical_plane_bending_moment",
        "member_torsion",
    }
    assert {row["end"] for row in member_rows} == {"I", "J"}


def test_external_results_template_is_normalized_and_ready_for_values() -> None:
    model = _lm1_model()
    package = build_model_verification_export_package(model)
    rows = list(csv.DictReader(StringIO(package.external_results_template_csv)))

    assert rows
    assert set(rows[0]) == {
        "result_type",
        "object_id",
        "span_index",
        "position_m",
        "component",
        "value",
        "unit",
    }
    assert all(row["value"] == "" for row in rows)
    assert any(
        row["result_type"] == "support_reaction" and row["component"] == "FZ"
        for row in rows
    )
    assert any(
        row["result_type"] == "node_displacement" and row["component"] == "DZ"
        for row in rows
    )
    assert {row["component"] for row in rows if row["result_type"] == "member_end_force"} == {
        "V_VERTICAL",
        "M_VERTICAL",
        "T",
    }
