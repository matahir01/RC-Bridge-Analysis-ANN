from rc_bridge.application.design_checks import (
    ApplicationDesignSettings,
    run_application_design_interpretation,
)
from rc_bridge.application.load_cases import eurocode_variable_action_scope
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.project_io import dumps_project_document, loads_project_document
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.workflow.project_bridge import SLSCombinationChoice


def _session() -> BridgeApplicationSession:
    return BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            ),
            design=ApplicationDesignSettings(
                cover_mm=50.0,
                durability_minimum_cover_mm=40.0,
                cover_deviation_mm=10.0,
                aggregate_size_mm=20.0,
                nominal_link_diameter_mm=12.0,
                crack_combination=SLSCombinationChoice.FREQUENT,
                deflection_combination=SLSCombinationChoice.FREQUENT,
                creep_coefficient=0.0,
                deflection_beta=0.5,
                crack_kt=0.4,
                cot_theta=2.0,
            ),
        ),
    )


def test_design_preferences_round_trip() -> None:
    session = _session()
    loaded = loads_project_document(
        dumps_project_document(
            session.project,
            application_preferences=session.preferences,
        )
    )

    assert loaded.application_preferences.design == session.preferences.design
    assert (
        loaded.application_preferences.design.crack_combination
        is SLSCombinationChoice.FREQUENT
    )


def test_design_interpretation_runs_real_ec2_checks_after_native_lm1() -> None:
    session = _session()
    search = session.run_native_lm1()
    session.run_extended_actions()
    result = session.run_design_interpretation()

    assert result.girders
    assert len(result.girders) == session.project.geometry.girder_count
    centre = result.girders[3]
    assert centre.design.uls_design.flexure.required_steel_area_mm2 > 0.0
    assert centre.selected_bars.provided_area_mm2 >= (
        centre.design.uls_design.flexure.required_steel_area_mm2
    )
    assert centre.selected_links.provided_asw_per_s_mm2_per_m > 0.0
    assert centre.design.crack.crack_width_mm >= 0.0
    assert centre.design.deflection.interpolated_deflection_mm >= 0.0
    assert centre.design.uls_design.design_effects.moment_knm > (
        centre.traffic_characteristic.moment_knm
    )
    assert session.last_design_interpretation is result
    assert result.action_combinations is not None
    assert session.last_action_combinations is result.action_combinations
    assert centre.construction_stage_checks
    assert all(item.passes for item in centre.construction_stage_checks)
    assert centre.governing_uls_moment_situation
    assert "LM2 local deck/slab plate resistance check" in " ".join(
        result.coverage_blockers
    )

    direct = run_application_design_interpretation(
        session.project,
        search,
        uls_factors=session.preferences.eurocode.uls_factors,
        sls_factors=session.preferences.eurocode.sls_factors,
        crack_limit_mm=session.preferences.eurocode.crack_limit_mm,
        deflection_limit_span_ratio=(
            session.preferences.eurocode.deflection_limit_span_ratio
        ),
        settings=session.preferences.design,
    )
    assert direct.girders[3].selected_bars.provided_area_mm2 <= (
        centre.selected_bars.provided_area_mm2
    )
    assert (
        direct.girders[3].design.uls_design.design_effects.moment_knm
        <= centre.design.uls_design.design_effects.moment_knm
    )


def test_design_interpretation_invalidates_when_design_basis_changes() -> None:
    session = _session()
    session.run_native_lm1()
    session.run_extended_actions()
    session.run_design_interpretation()
    changed = ApplicationPreferences(
        units=session.preferences.units,
        eurocode=session.preferences.eurocode,
        analysis=session.preferences.analysis,
        design=ApplicationDesignSettings(cover_mm=55.0),
    )

    session.set_preferences(changed)

    assert session.last_lm1_search is not None
    assert session.last_design_interpretation is None


def test_barrier_vehicle_impact_is_explicitly_exposed_as_accidental_scope() -> None:
    scope = {item.name: item for item in eurocode_variable_action_scope()}

    impact = scope["Vehicle impact on safety barrier"]
    assert impact.status.startswith("local accidental action implemented")
    assert "local horizontal design task" in impact.detail
