import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)


def _section(name: str) -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name=name,
        area_m2=0.50,
        torsion_constant_m4=0.04,
        iy_m4=0.03,
        iz_m4=0.08,
    )


def _project() -> ProjectInput:
    return ProjectInput(
        name="Area Load Grillage",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0],
            deck_width_m=5.0,
            carriageway_width_m=4.0,
            girder_count=3,
            girder_spacing_m=2.0,
        ),
    )


def test_uniform_area_patch_preserves_total_force_and_centroid() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0,),
        load_case=GrillageVerificationLoadCase(
            name="lane pressure",
            area_loads=(
                GrillageAreaLoad(
                    x_start_m=2.0,
                    x_end_m=8.0,
                    y_start_m=-1.0,
                    y_end_m=1.0,
                    pressure_kn_m2=10.0,
                    label="verification patch",
                ),
            ),
        ),
    )

    loads = model.load_cases[0].nodal_loads
    total_downward_kn = sum(-load.fz_kn for load in loads)
    assert total_downward_kn == pytest.approx(120.0)

    nodes = {node.node_id: node for node in model.nodes}
    resultant_x = sum(nodes[load.node_id].x_m * -load.fz_kn for load in loads) / total_downward_kn
    resultant_y = sum(nodes[load.node_id].y_m * -load.fz_kn for load in loads) / total_downward_kn
    assert resultant_x == pytest.approx(5.0)
    assert resultant_y == pytest.approx(0.0)

    x_coordinates = {node.x_m for node in model.nodes}
    y_coordinates = {node.y_m for node in model.nodes}
    assert 2.0 in x_coordinates
    assert 8.0 in x_coordinates
    assert -1.0 in y_coordinates
    assert 1.0 in y_coordinates


def test_area_patch_may_extend_into_deck_overhang_but_not_outside_deck() -> None:
    model = build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(5.0,),
        load_case=GrillageVerificationLoadCase(
            name="overhang pressure",
            area_loads=(
                GrillageAreaLoad(
                    x_start_m=0.0,
                    x_end_m=5.0,
                    y_start_m=2.0,
                    y_end_m=2.5,
                    pressure_kn_m2=5.0,
                ),
            ),
        ),
    )
    assert sum(-load.fz_kn for load in model.load_cases[0].nodal_loads) == pytest.approx(12.5)

    with pytest.raises(ValueError, match="outside the physical deck width"):
        build_project_grillage_verification_model(
            _project(),
            longitudinal_sections_by_span=(_section("Longitudinal"),),
            transverse_section=_section("Transverse"),
            transverse_stations_m=(5.0,),
            load_case=GrillageVerificationLoadCase(
                name="invalid pressure",
                area_loads=(
                    GrillageAreaLoad(
                        x_start_m=0.0,
                        x_end_m=5.0,
                        y_start_m=2.0,
                        y_end_m=2.6,
                        pressure_kn_m2=5.0,
                    ),
                ),
            ),
        )
