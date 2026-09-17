import pytest

from rc_bridge.analysis.grillage_solver import solve_vertical_grillage
from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNodalLoad,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)

_E_KN_M2 = 30.0e6
_EI_KN_M2 = 1.0e6
_IY_M4 = _EI_KN_M2 / _E_KN_M2


def _section() -> VerificationSection:
    return VerificationSection(
        section_id=1,
        name="Benchmark",
        area_m2=0.45,
        torsion_constant_m4=0.01,
        iy_m4=_IY_M4,
        iz_m4=0.05,
    )


def _line_model(*, along_y: bool = False, udl_kn_m: float | None = None) -> VerificationModel:
    if along_y:
        nodes = (
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 0.0, 5.0, 0.0),
            VerificationNode(3, 0.0, 10.0, 0.0),
        )
        first_support = VerificationSupport(1, uz=True, ry=True)
    else:
        nodes = (
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 5.0, 0.0, 0.0),
            VerificationNode(3, 10.0, 0.0, 0.0),
        )
        first_support = VerificationSupport(1, uz=True, rx=True)

    uniform_loads = ()
    nodal_loads = (VerificationNodalLoad(node_id=2, fz_kn=-100.0),)
    if udl_kn_m is not None:
        uniform_loads = (
            VerificationUniformLoad(1, "GZ", -udl_kn_m),
            VerificationUniformLoad(2, "GZ", -udl_kn_m),
        )
        nodal_loads = ()

    return VerificationModel(
        name="simple grillage beam",
        nodes=nodes,
        materials=(VerificationMaterial(1, "Concrete", _E_KN_M2),),
        sections=(_section(),),
        beams=(
            VerificationBeam(1, 1, 2, 1, 1),
            VerificationBeam(2, 2, 3, 1, 1),
        ),
        supports=(first_support, VerificationSupport(3, uz=True)),
        load_cases=(
            VerificationLoadCase(
                1,
                "BENCH",
                uniform_loads=uniform_loads,
                nodal_loads=nodal_loads,
            ),
        ),
    )


def test_grillage_line_beam_matches_central_point_load_closed_form() -> None:
    result = solve_vertical_grillage(_line_model())
    nodes = {item.node_id: item for item in result.nodes}

    expected_midspan = -(100.0 * 10.0**3) / (48.0 * _EI_KN_M2)
    assert nodes[1].vertical_reaction_kn == pytest.approx(50.0)
    assert nodes[3].vertical_reaction_kn == pytest.approx(50.0)
    assert nodes[2].vertical_displacement_m == pytest.approx(expected_midspan)
    assert result.total_applied_vertical_load_kn == pytest.approx(-100.0)
    assert result.total_vertical_reaction_kn == pytest.approx(100.0)
    assert result.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1.0e-9)


def test_grillage_line_beam_matches_full_udl_closed_form() -> None:
    result = solve_vertical_grillage(_line_model(udl_kn_m=20.0))
    nodes = {item.node_id: item for item in result.nodes}

    expected_midspan = -(5.0 * 20.0 * 10.0**4) / (384.0 * _EI_KN_M2)
    assert nodes[1].vertical_reaction_kn == pytest.approx(100.0)
    assert nodes[3].vertical_reaction_kn == pytest.approx(100.0)
    assert nodes[2].vertical_displacement_m == pytest.approx(expected_midspan)
    assert result.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1.0e-9)


def test_grillage_beam_rotated_to_global_y_has_same_vertical_response() -> None:
    result = solve_vertical_grillage(_line_model(along_y=True))
    nodes = {item.node_id: item for item in result.nodes}

    expected_midspan = -(100.0 * 10.0**3) / (48.0 * _EI_KN_M2)
    assert nodes[1].vertical_reaction_kn == pytest.approx(50.0)
    assert nodes[3].vertical_reaction_kn == pytest.approx(50.0)
    assert nodes[2].vertical_displacement_m == pytest.approx(expected_midspan)


def test_grillage_solver_rejects_unrestrained_mechanism() -> None:
    model = _line_model()
    unrestrained = VerificationModel(
        name=model.name,
        nodes=model.nodes,
        materials=model.materials,
        sections=model.sections,
        beams=model.beams,
        supports=(),
        load_cases=model.load_cases,
    )
    with pytest.raises(ValueError, match="no restraints"):
        solve_vertical_grillage(unrestrained)


def test_project_grillage_pressure_load_preserves_vertical_equilibrium_and_symmetry() -> None:
    project = ProjectInput(
        name="symmetric grillage",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0],
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
        ),
    )
    section = GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.02,
        iy_m4=0.04,
        iz_m4=0.05,
    )
    transverse = GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.01,
        iy_m4=0.015,
        iz_m4=0.02,
    )
    model = build_project_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(section,),
        transverse_section=transverse,
        transverse_stations_m=(5.0,),
        load_case=GrillageVerificationLoadCase(
            name="full deck pressure",
            area_loads=(
                GrillageAreaLoad(
                    0.0,
                    10.0,
                    -2.5,
                    2.5,
                    pressure_kn_m2=2.0,
                ),
            ),
        ),
    )

    result = solve_vertical_grillage(model)
    reactions = [item.vertical_reaction_kn for item in result.nodes if item.vertical_reaction_kn]

    assert result.total_applied_vertical_load_kn == pytest.approx(-100.0)
    assert result.total_vertical_reaction_kn == pytest.approx(100.0)
    assert result.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1.0e-8)
    assert len(reactions) == 6
    assert reactions[0] == pytest.approx(reactions[-1])
    assert reactions[1] == pytest.approx(reactions[-2])
    assert reactions[2] == pytest.approx(reactions[-3])
