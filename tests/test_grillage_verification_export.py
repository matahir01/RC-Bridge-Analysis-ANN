import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.export.midas_mct import export_midas_mct
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.workflow.grillage_verification_export import (
    GrillagePointLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Grillage Verification Bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 12.0],
            deck_width_m=5.0,
            carriageway_width_m=4.0,
            girder_count=3,
            girder_spacing_m=2.0,
            support_system=SupportSystem.CONTINUOUS,
        ),
    )


def _section(name: str, scale: float = 1.0) -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name=name,
        area_m2=0.50 * scale,
        torsion_constant_m4=0.04 * scale,
        iy_m4=0.03 * scale,
        iz_m4=0.08 * scale,
    )


def test_full_grillage_geometry_supports_sections_and_line_loads() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2", 1.2)),
        transverse_section=_section("Transverse", 0.4),
        transverse_stations_m=(5.0, 16.0),
        load_case=GrillageVerificationLoadCase(
            name="dead load",
            longitudinal_udl_kn_m_by_girder=(10.0, 20.0, 30.0),
        ),
    )

    assert len(model.nodes) == 15
    assert len(model.beams) == 22
    assert len(model.supports) == 9
    assert len(model.sections) == 3

    coordinates = {(node.x_m, node.y_m) for node in model.nodes}
    assert (0.0, -2.0) in coordinates
    assert (16.0, 0.0) in coordinates
    assert (22.0, 2.0) in coordinates

    longitudinal = model.beams[:12]
    assert [beam.section_id for beam in longitudinal[:6]] == [1] * 6
    assert [beam.section_id for beam in longitudinal[6:]] == [2] * 6
    assert all(beam.section_id == 3 for beam in model.beams[12:])

    case = model.load_cases[0]
    assert len(case.uniform_loads) == 12
    magnitudes = [load.magnitude_kn_m for load in case.uniform_loads]
    assert magnitudes.count(-10.0) == 4
    assert magnitudes.count(-20.0) == 4
    assert magnitudes.count(-30.0) == 4

    first_support = next(item for item in model.supports if item.node_id == 1)
    opposite_anchor = next(item for item in model.supports if item.node_id == 3)
    assert first_support.ux and first_support.uy and first_support.uz
    assert opposite_anchor.ux and not opposite_anchor.uy and opposite_anchor.uz


def test_point_load_bilinear_mapping_preserves_force_and_position() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0, 16.0),
        load_case=GrillageVerificationLoadCase(
            name="wheel snapshot",
            point_loads=(GrillagePointLoad(x_m=2.5, y_m=-1.0, magnitude_kn=100.0),),
        ),
    )

    loads = model.load_cases[0].nodal_loads
    assert len(loads) == 4
    assert sum(load.fz_kn for load in loads) == pytest.approx(-100.0)
    assert sorted(load.fz_kn for load in loads) == pytest.approx([-25.0] * 4)

    nodes = {node.node_id: node for node in model.nodes}
    resultant_x = sum(nodes[load.node_id].x_m * -load.fz_kn for load in loads) / 100.0
    resultant_y = sum(nodes[load.node_id].y_m * -load.fz_kn for load in loads) / 100.0
    assert resultant_x == pytest.approx(2.5)
    assert resultant_y == pytest.approx(-1.0)


def test_grillage_model_exports_through_existing_midas_and_staad_writers() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0, 16.0),
        load_case=GrillageVerificationLoadCase(name="empty verification case"),
    )

    midas = export_midas_mct(model)
    staad = export_staad_std(model)
    assert "*NODE" in midas
    assert "*ELEMENT" in midas
    assert "*CONSTRAINT" in midas
    assert "JOINT COORDINATES" in staad
    assert "MEMBER INCIDENCES" in staad
    assert "SUPPORTS" in staad


def test_point_load_outside_exterior_girder_lines_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside the grillage node envelope"):
        build_project_grillage_verification_model(
            _project(),
            longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
            transverse_section=_section("Transverse"),
            transverse_stations_m=(5.0, 16.0),
            load_case=GrillageVerificationLoadCase(
                name="invalid wheel",
                point_loads=(GrillagePointLoad(x_m=5.0, y_m=2.4, magnitude_kn=50.0),),
            ),
        )
