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

    assert len(model.nodes) == 25
    assert len(model.beams) == 32
    assert len(model.supports) == 9
    assert len(model.sections) == 3

    coordinates = {(node.x_m, node.y_m) for node in model.nodes}
    assert (0.0, -2.5) in coordinates
    assert (0.0, -2.0) in coordinates
    assert (16.0, 0.0) in coordinates
    assert (22.0, 2.0) in coordinates
    assert (22.0, 2.5) in coordinates

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

    first_support = next(item for item in model.supports if item.node_id == 2)
    opposite_fixed = next(item for item in model.supports if item.node_id == 4)
    assert first_support.ux and first_support.uy and first_support.uz
    assert opposite_fixed.ux and not opposite_fixed.uy and opposite_fixed.uz


def test_point_load_inserts_exact_x_station_and_exact_transverse_position() -> None:
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

    assert any(node.x_m == pytest.approx(2.5) for node in model.nodes)
    case = model.load_cases[0]
    assert case.nodal_loads == ()
    assert len(case.point_loads) == 1
    load = case.point_loads[0]
    assert load.magnitude_kn == pytest.approx(-100.0)
    assert load.distance_from_i_m == pytest.approx(1.0)

    member = next(beam for beam in model.beams if beam.member_id == load.member_id)
    nodes = {node.node_id: node for node in model.nodes}
    node_i = nodes[member.node_i]
    node_j = nodes[member.node_j]
    assert node_i.x_m == pytest.approx(2.5)
    assert node_j.x_m == pytest.approx(2.5)
    assert node_i.y_m == pytest.approx(-2.0)
    assert node_j.y_m == pytest.approx(0.0)


def test_wheel_load_on_girder_line_is_exported_as_exact_nodal_load() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0, 16.0),
        load_case=GrillageVerificationLoadCase(
            name="girder-line wheel",
            point_loads=(GrillagePointLoad(x_m=5.0, y_m=0.0, magnitude_kn=75.0),),
        ),
    )

    case = model.load_cases[0]
    assert case.point_loads == ()
    assert len(case.nodal_loads) == 1
    load = case.nodal_loads[0]
    node = next(node for node in model.nodes if node.node_id == load.node_id)
    assert node.x_m == pytest.approx(5.0)
    assert node.y_m == pytest.approx(0.0)
    assert load.fz_kn == pytest.approx(-75.0)


def test_deck_overhang_point_load_is_carried_by_transverse_cantilever() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0, 16.0),
        load_case=GrillageVerificationLoadCase(
            name="overhang wheel",
            point_loads=(GrillagePointLoad(x_m=5.0, y_m=2.4, magnitude_kn=50.0),),
        ),
    )

    load = model.load_cases[0].point_loads[0]
    member = next(beam for beam in model.beams if beam.member_id == load.member_id)
    nodes = {node.node_id: node for node in model.nodes}
    assert nodes[member.node_i].y_m == pytest.approx(2.0)
    assert nodes[member.node_j].y_m == pytest.approx(2.5)
    assert load.distance_from_i_m == pytest.approx(0.4)
    assert load.magnitude_kn == pytest.approx(-50.0)


def test_point_load_outside_physical_deck_width_is_rejected() -> None:
    with pytest.raises(ValueError, match="outside the physical deck width"):
        build_project_grillage_verification_model(
            _project(),
            longitudinal_sections_by_span=(_section("Span 1"), _section("Span 2")),
            transverse_section=_section("Transverse"),
            transverse_stations_m=(5.0, 16.0),
            load_case=GrillageVerificationLoadCase(
                name="invalid wheel",
                point_loads=(GrillagePointLoad(x_m=5.0, y_m=2.6, magnitude_kn=50.0),),
            ),
        )


def test_grillage_regenerates_for_eight_editable_girders() -> None:
    project = ProjectInput(
        name="Eight Girder Bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=8,
            girder_spacing_m=1.40,
        ),
    )
    model = build_project_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(_section("Span 1"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0, 10.0),
        load_case=GrillageVerificationLoadCase(name="geometry only"),
    )

    y_coordinates = sorted({node.y_m for node in model.nodes})
    assert len(y_coordinates) == 10
    assert y_coordinates[0] == pytest.approx(-5.5)
    assert y_coordinates[-1] == pytest.approx(5.5)
    assert project.geometry.nominal_edge_overhang_m == pytest.approx(0.60)
    assert model.metadata["girder_count"] == "8"
    assert model.metadata["girder_spacing_m"] == "1.4"


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
