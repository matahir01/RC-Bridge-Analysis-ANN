from rc_bridge.analysis.physical_sections import composite_section_description
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
from rc_bridge.research.msc_input_space import MSC_DEFLECTION_LIMIT_SPAN_RATIO
from rc_bridge.research.msc_profile import evaluate_msc_deterministic_gate


def _msc_acceptance_session() -> BridgeApplicationSession:
    project = application_default_project()
    preferences = ApplicationPreferences(
        eurocode=EurocodeApplicationBasis(
            # MSc serviceability criterion: L/250, following the JRC Eurocode
            # worked-example/training basis adopted for this research profile.
            # It is recorded as the research criterion rather than represented
            # as a universal normative EN 1992-2 bridge requirement.
            deflection_limit_span_ratio=MSC_DEFLECTION_LIMIT_SPAN_RATIO,
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
    assert geometry.section_type.value == "rectangular"
    assert float(geometry.girder_profile.width_m) == 0.40
    assert float(geometry.girder_profile.depth_m) == 0.95
    assert float(geometry.precast_girder_length_m) == 14.95
    assert session.preferences.eurocode.deflection_limit_span_ratio == 250.0
    assert 15000.0 / session.preferences.eurocode.deflection_limit_span_ratio == 60.0
    composite = composite_section_description(
        geometry,
        slab_width_m=1.70,
        slab_width_basis="research girder spacing",
    )
    assert composite.precast_section_type == "rectangular"
    assert composite.final_section_form == "T"
    assert composite.web_width_m == 0.40
    assert composite.participating_flange_depth_m == 0.175

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

    search = reopened.run_native_lm1(
        longitudinal_step_m=3.75,
        max_exhaustive_tandem_combinations=5000,
        convergence_tolerance=0.05,
        minimum_longitudinal_step_m=0.46875,
        max_convergence_refinements=3,
    )
    assert reopened.last_lm1_convergence is not None
    assert reopened.last_lm1_convergence.converged
    assert reopened.last_lm1_convergence.refinements[-1].maximum_relative_change <= 0.05
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
