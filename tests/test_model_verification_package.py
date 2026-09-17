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
)


def _section(name: str) -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name=name,
        area_m2=0.50,
        torsion_constant_m4=0.04,
        iy_m4=0.03,
        iz_m4=0.08,
    )


def _lm1_model():
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
    return build_project_lm1_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(7.5,),
        lane_placements=(
            LM1LaneVerificationPlacement(1, -3.5, -0.5, full_span, 5.0),
            LM1LaneVerificationPlacement(2, -0.5, 2.5, full_span, 8.0),
        ),
        remaining_area_placements=(
            LM1RemainingAreaVerificationPlacement(2.5, 3.5, full_span),
        ),
    )


def test_model_verification_package_contains_midas_staad_manifest_and_exact_loads() -> None:
    package = build_model_verification_export_package(_lm1_model())
    files = package.files("lm1_8_girder_check")

    assert set(files) == {
        "lm1_8_girder_check.mct",
        "lm1_8_girder_check.std",
        "lm1_8_girder_check_manifest.json",
        "lm1_8_girder_check_exported_loads.csv",
    }
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
