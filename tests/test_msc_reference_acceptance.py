from rc_bridge.application.design_checks import ApplicationDesignSettings
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
    EurocodeApplicationBasis,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.research.acceptance_matrix import (
    AcceptanceState,
    eurocode_simple_span_v1_acceptance_matrix,
)
from rc_bridge.research.msc_profile import evaluate_msc_deterministic_gate


def _msc_acceptance_session() -> BridgeApplicationSession:
    project = application_default_project()
    preferences = ApplicationPreferences(
        eurocode=EurocodeApplicationBasis(
            # Project-defined numerical criterion for g_deflection. This is
            # intentionally not presented as a universal Eurocode bridge limit.
            deflection_limit_span_ratio=1000.0,
        ),
        analysis=AnalysisApplicationSettings(
            grid_spacing_m=15.0,
            traffic_step_m=15.0,
            max_exhaustive_tandem_combinations=20,
        ),
        design=ApplicationDesignSettings(),
    )
    return BridgeApplicationSession(project, preferences=preferences)


def test_15m_application_acceptance_smoke_runs_end_to_end(tmp_path) -> None:
    session = _msc_acceptance_session()
    geometry = session.project.geometry

    assert tuple(float(value) for value in geometry.span_lengths_m) == (15.0,)
    assert float(geometry.deck_width_m) == 11.0
    assert float(geometry.carriageway_width_m) == 7.0
    assert int(geometry.girder_count) == 7
    assert float(geometry.girder_spacing_m) == 1.70
    assert geometry.girder_profile is not None

    gate = evaluate_msc_deterministic_gate(session.project)
    assert gate.ready is True
    gate.require_ready()

    # Exercise real persisted application state rather than an in-memory-only path.
    project_path = session.save(tmp_path / "msc_15m_acceptance.json")
    reopened = BridgeApplicationSession.open(project_path)
    assert reopened.project == session.project
    assert (
        reopened.preferences.eurocode.deflection_limit_span_ratio
        == session.preferences.eurocode.deflection_limit_span_ratio
    )

    search = reopened.run_native_lm1()
    reopened.run_extended_actions()
    design = reopened.run_design_interpretation()
    fatigue = reopened.run_fatigue()

    assert len(search.girders) == 7
    assert len(design.girders) == 7
    assert design.girders
    assert fatigue.search.cases
    assert not fatigue.girders
    assert fatigue.blockers
    assert fatigue.passes is None
    assert any(
        "longitudinal reinforcement fatigue" in blocker
        for blocker in fatigue.blockers
    )

    for girder in design.girders:
        assert girder.design.uls_design.flexure.required_steel_area_mm2 > 0.0
        assert (
            girder.selected_bars.provided_area_mm2
            >= girder.design.uls_design.flexure.required_steel_area_mm2
        )
        assert girder.selected_links.provided_asw_per_s_mm2_per_m > 0.0
        assert girder.design.crack.crack_width_mm >= 0.0
        assert girder.design.deflection.interpolated_deflection_mm >= 0.0
        assert girder.design.deflection.g_deflection_mm is not None

    report = reopened.write_last_lm1_report(tmp_path / "msc_15m_acceptance.html")
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "15 m RC Girder Project" in report_text
    assert "Native LM1" in report_text

    exported = reopened.export_last_lm1_verification(
        tmp_path / "verification",
        base_name="msc_15m_acceptance",
    )
    assert exported.midas_mct.exists()
    assert exported.staad_std.exists()
    assert exported.midas_mct.read_text(encoding="utf-8")
    assert exported.staad_std.read_text(encoding="utf-8")

    # CI does not launch proprietary STAAD. Instead, the acceptance smoke
    # requires the already reviewed genuine Stage-5 external evidence gate.
    matrix = eurocode_simple_span_v1_acceptance_matrix()
    assert (
        matrix.item("stage5_structural_response").state
        is AcceptanceState.EXTERNALLY_ACCEPTED
    )
    assert matrix.msc_research_verification_manifest().load_combinations is True
