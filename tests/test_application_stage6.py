import json

import pytest

from rc_bridge.application.dashboard import CapabilityState, build_application_dashboard
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
    EurocodeApplicationBasis,
    UnitDisplay,
)
from rc_bridge.application.project_editor import (
    ProjectBasicFields,
    application_default_project,
)
from rc_bridge.application.project_io import (
    dumps_project_document,
    loads_project_document,
)
from rc_bridge.application.session import BridgeApplicationSession


def test_application_preferences_round_trip_in_project_document() -> None:
    project = application_default_project()
    preferences = ApplicationPreferences(
        units=UnitDisplay.DRAWING_MILLIMETRES,
        eurocode=EurocodeApplicationBasis(
            gamma_g_unfavourable=1.30,
            gamma_g_favourable=1.0,
            gamma_q_traffic=1.45,
            psi1_traffic=0.70,
            psi2_traffic=0.20,
            crack_limit_mm=0.25,
            deflection_limit_span_ratio=900.0,
        ),
        analysis=AnalysisApplicationSettings(
            grid_spacing_m=0.75,
            traffic_step_m=0.25,
            max_exhaustive_tandem_combinations=2500,
        ),
    )

    document = loads_project_document(
        dumps_project_document(
            project,
            application_preferences=preferences,
        )
    )

    assert document.project == project
    assert document.application_preferences == preferences
    assert document.application_preferences.units is UnitDisplay.DRAWING_MILLIMETRES


def test_document_checksum_covers_application_preferences() -> None:
    payload = json.loads(
        dumps_project_document(
            application_default_project(),
            application_preferences=ApplicationPreferences(
                units=UnitDisplay.DRAWING_MILLIMETRES
            ),
        )
    )
    payload["application_preferences"]["analysis"]["traffic_step_m"] = 9.0

    try:
        loads_project_document(json.dumps(payload))
    except ValueError as exc:
        assert "document checksum" in str(exc)
    else:
        raise AssertionError("Tampered application preferences must fail checksum validation.")


def test_application_dashboard_keeps_verification_and_research_gates_visible() -> None:
    dashboard = build_application_dashboard(
        application_default_project(),
        has_native_lm1_analysis=True,
    )
    states = {item.state for item in dashboard.capabilities}

    assert CapabilityState.READY in states
    assert CapabilityState.VERIFICATION_REQUIRED in states
    assert CapabilityState.RESEARCH_LOCKED in states


def test_expanded_project_editor_round_trips_deck_and_material_inputs() -> None:
    project = application_default_project()
    fields = ProjectBasicFields.from_project(project)
    edited = ProjectBasicFields(
        **{
            **fields.__dict__,
            "precast_false_slab_depth_m": 0.080,
            "in_situ_slab_depth_m": 0.180,
            "false_slab_composite_participation": True,
            "concrete_density_kn_m3": 24.5,
            "elastic_modulus_mpa": 34000.0,
        }
    ).apply(project)

    assert edited.geometry.deck_structural_depth_m == pytest.approx(0.260)
    assert edited.geometry.deck_construction.false_slab_composite_participation
    assert edited.materials.concrete_density_kn_m3 == 24.5
    assert edited.materials.elastic_modulus_mpa == 34000.0


def test_session_persists_preferences_and_writes_pdf(tmp_path) -> None:
    session = BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=7.5,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            )
        ),
    )
    path = session.save(tmp_path / "stage6.json")
    opened = BridgeApplicationSession.open(path)

    assert opened.preferences == session.preferences

    result = opened.run_native_lm1()
    pdf = opened.write_last_lm1_pdf_report(tmp_path / "report.pdf")

    assert result.evaluated_case_count > 0
    assert pdf.exists()
    assert pdf.read_bytes().startswith(b"%PDF")
