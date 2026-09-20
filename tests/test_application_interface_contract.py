from types import SimpleNamespace

import pytest

from rc_bridge.application.interface_contract import (
    APPLICATION_INTERFACE_VERSION,
    ENGINE_INTERFACE_VERSION,
    FROZEN_ENGINE_ENTRYPOINTS,
    FROZEN_SESSION_OPERATIONS,
    FROZEN_SESSION_STATE,
    build_application_view_snapshot,
    validate_application_interface,
    validate_engine_interface,
)
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession


def _session() -> BridgeApplicationSession:
    return BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            )
        ),
    )


def test_frozen_engine_and_application_interfaces_resolve() -> None:
    assert ENGINE_INTERFACE_VERSION == "1.0"
    assert APPLICATION_INTERFACE_VERSION == "1.0"
    assert FROZEN_ENGINE_ENTRYPOINTS
    validate_engine_interface()

    session = _session()
    validate_application_interface(session)
    assert all(callable(getattr(session, name)) for name in FROZEN_SESSION_OPERATIONS)
    assert all(hasattr(session, name) for name in FROZEN_SESSION_STATE)


def test_incompatible_application_session_fails_early() -> None:
    with pytest.raises(TypeError, match="does not satisfy desktop interface"):
        validate_application_interface(object())


def test_presentation_snapshot_tracks_engine_workflow_without_exposing_gui_state() -> None:
    session = _session()

    initial = build_application_view_snapshot(session)

    assert initial.interface_version == APPLICATION_INTERFACE_VERSION
    assert initial.project_name == session.project.name
    assert initial.calculation_trace_available is False
    assert next(stage for stage in initial.stages if stage.key == "project").state == "complete"
    assert next(stage for stage in initial.stages if stage.key == "analysis").state == "pending"

    session.run_native_lm1()
    analysed = build_application_view_snapshot(session)

    assert analysed.calculation_trace_available is True
    assert next(stage for stage in analysed.stages if stage.key == "analysis").state == "complete"
    assert analysed.last_operation == "Native Lm1"
    assert "Completed in" in analysed.last_operation_detail


def test_snapshot_reflects_external_verification_boundary() -> None:
    session = _session()
    snapshot = build_application_view_snapshot(session)

    verification = next(stage for stage in snapshot.stages if stage.key == "verification")

    assert verification.state == "pending"
    assert "No external Stage-5 result import yet" in verification.detail


def test_snapshot_never_marks_external_verification_complete_from_envelope_only() -> None:
    session = _session()
    session.last_verification_import = SimpleNamespace(
        source_name="STAAD.Pro",
        result_sets=(object(), object()),
        requested_result_ids=(1, 2),
        import_complete=True,
        detailed_comparisons_pass=False,
        envelope_comparison_passes=True,
        numerical_agreement_passes=False,
    )

    snapshot = build_application_view_snapshot(session)
    verification = next(stage for stage in snapshot.stages if stage.key == "verification")

    assert verification.state == "review"
    assert "detailed numerical agreement FAIL / REVIEW" in verification.detail
    assert "engineering envelope PASS" in verification.detail
    assert "Engineering acceptance PENDING REVIEW" in verification.detail



def test_snapshot_marks_verification_complete_only_after_engineering_acceptance() -> None:
    session = _session()
    session.last_verification_import = SimpleNamespace(
        source_name="STAAD.Pro",
        result_sets=(object(), object()),
        requested_result_ids=(1, 2),
        import_complete=True,
        detailed_comparisons_pass=True,
        envelope_comparison_passes=True,
        combination_envelope_comparison_passes=True,
        numerical_agreement_passes=True,
        engineering_accepted=True,
        engineering_acceptance_status="ACCEPTED",
        engineering_review=None,
    )

    snapshot = build_application_view_snapshot(session)
    verification = next(stage for stage in snapshot.stages if stage.key == "verification")

    assert verification.state == "complete"
    assert "overall numerical PASS" in verification.detail
    assert "Engineering acceptance ACCEPTED" in verification.detail
