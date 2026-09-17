import pytest

from rc_bridge.analysis.moving_loads import AxleTrain
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.export.midas_mct import export_midas_mct
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.workflow.project_continuous import GlobalBeamPointLoad, ProjectContinuousLoadCase
from rc_bridge.workflow.verification_export import (
    build_moving_train_snapshot_verification_model,
    build_project_continuous_verification_model,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Two Span Verification Bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 12.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )


def _load_case() -> ProjectContinuousLoadCase:
    return ProjectContinuousLoadCase(
        ei_kn_m2_by_span=(1.0e6, 1.2e6),
        udl_kn_m_by_span=(20.0, 25.0),
        point_loads=(
            GlobalBeamPointLoad(100.0, 5.0, "span 1 axle"),
            GlobalBeamPointLoad(80.0, 14.0, "span 2 axle"),
        ),
        name="verification service load",
    )


def test_continuous_verification_model_reproduces_geometry_stiffness_and_load_positions() -> None:
    model = build_project_continuous_verification_model(
        _project(),
        _load_case(),
        analysis_area_m2_by_span=(0.45, 0.45),
    )

    assert [node.x_m for node in model.nodes] == pytest.approx([0.0, 10.0, 22.0])
    assert [(beam.node_i, beam.node_j) for beam in model.beams] == [(1, 2), (2, 3)]
    assert [item.restraint_code for item in model.supports] == ["111100", "011000", "011000"]

    e_kn_m2 = model.materials[0].elastic_modulus_kn_m2
    assert e_kn_m2 * model.sections[0].iy_m4 == pytest.approx(1.0e6)
    assert e_kn_m2 * model.sections[1].iy_m4 == pytest.approx(1.2e6)

    loads = model.load_cases[0]
    assert [item.magnitude_kn_m for item in loads.uniform_loads] == pytest.approx([-20.0, -25.0])
    assert loads.point_loads[0].member_id == 1
    assert loads.point_loads[0].distance_from_i_m == pytest.approx(5.0)
    assert loads.point_loads[0].magnitude_kn == pytest.approx(-100.0)
    assert loads.point_loads[1].member_id == 2
    assert loads.point_loads[1].distance_from_i_m == pytest.approx(4.0)
    assert loads.point_loads[1].magnitude_kn == pytest.approx(-80.0)


def test_verification_export_refuses_to_invent_section_area() -> None:
    with pytest.raises(ValueError, match="No artificial section area"):
        build_project_continuous_verification_model(_project(), _load_case())


def test_staad_export_contains_complete_analysis_skeleton() -> None:
    model = build_project_continuous_verification_model(
        _project(),
        _load_case(),
        analysis_area_m2_by_span=(0.45, 0.45),
    )
    text = export_staad_std(model)

    assert "STAAD SPACE" in text
    assert "UNIT METER KNS" in text
    assert "JOINT COORDINATES" in text
    assert "MEMBER INCIDENCES" in text
    assert "MEMBER PROPERTY" in text
    assert "DEFINE MATERIAL START" in text
    assert "SUPPORTS" in text
    assert "1 FIXED BUT FY MX MY MZ" not in text
    assert "1 FIXED BUT MY MZ" in text
    assert "LOAD 1 LOADTYPE None TITLE verification_service_load" in text
    assert "1 UNI GZ -20" in text
    assert "1 CON GZ -100 5" in text
    assert "2 CON GZ -80 4" in text
    assert "PERFORM ANALYSIS" in text
    assert "PRINT SUPPORT REACTION ALL" in text
    assert "PRINT MEMBER FORCES ALL" in text
    assert "PRINT JOINT DISPLACEMENTS ALL" in text
    assert text.rstrip().endswith("FINISH")


def test_midas_export_contains_complete_analysis_skeleton() -> None:
    model = build_project_continuous_verification_model(
        _project(),
        _load_case(),
        analysis_area_m2_by_span=(0.45, 0.45),
    )
    text = export_midas_mct(model)

    for command in (
        "*UNIT",
        "*NODE",
        "*MATERIAL",
        "*SECTION",
        "*ELEMENT",
        "*CONSTRAINT",
        "*STLDCASE",
        "*USE-STLD",
        "*BEAMLOAD",
        "*ENDDATA",
    ):
        assert command in text
    assert "1, 111100" in text
    assert "1, BEAM, UNILOAD, GZ, NO, 0, -20, 10, -20" in text
    assert "1, BEAM, CONLOAD, GZ, NO, 5, -100" in text
    assert "2, BEAM, CONLOAD, GZ, NO, 4, -80" in text


def test_moving_train_snapshot_freezes_exact_axle_position() -> None:
    model = build_moving_train_snapshot_verification_model(
        _project(),
        train=AxleTrain(
            axle_loads_kn=(120.0, 120.0),
            axle_offsets_m=(0.0, 1.2),
            label="two axle verification vehicle",
        ),
        lead_position_m=11.0,
        ei_kn_m2_by_span=(1.0e6, 1.2e6),
        analysis_area_m2_by_span=(0.45, 0.45),
    )

    loads = model.load_cases[0].point_loads
    assert len(loads) == 2
    assert loads[0].member_id == 2
    assert loads[0].distance_from_i_m == pytest.approx(1.0)
    assert loads[1].member_id == 1
    assert loads[1].distance_from_i_m == pytest.approx(9.8)
    assert model.metadata["lead_position_m"] == "11"
    assert model.metadata["snapshot_type"] == "static_axle_position_from_internal_moving_load_solver"
