from rc_bridge.application.extended_actions import ExtendedActionSettings
from rc_bridge.application.fatigue import FatigueApplicationSettings
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
            ),
            actions=ExtendedActionSettings(
                braking_enabled=False,
                thermal_enabled=False,
                pedestrian_enabled=False,
                lm2_enabled=True,
                lm2_longitudinal_step_m=15.0,
                lm2_transverse_step_m=5.0,
                barrier_impact_enabled=False,
                wind_enabled=False,
                construction_enabled=True,
            ),
            fatigue=FatigueApplicationSettings(
                movement_step_m=15.0,
                section_step_m=15.0,
                axle_load_factor=1.0,
                lambda_s=1.0,
                characteristic_fatigue_strength_mpa=1000.0,
                shear_link_lambda_s=1.0,
                shear_link_characteristic_fatigue_strength_mpa=1000.0,
            ),
        ),
    )


def test_desktop_flm3_uses_selected_design_reinforcement() -> None:
    session = _session()
    session.run_native_lm1()
    session.run_extended_actions()
    design = session.run_design_interpretation()

    result = session.run_fatigue()

    assert result.search.cases
    assert len(result.girders) == session.project.geometry.girder_count
    assert not result.blockers
    for fatigue_row, design_row in zip(
        result.girders,
        design.girders,
        strict=True,
    ):
        assert fatigue_row.girder_index == design_row.girder_index
        assert fatigue_row.reference_steel_stress_range_mpa >= 0.0
        assert fatigue_row.fatigue.reinforcement.utilization >= 0.0
        assert fatigue_row.shear_links is not None
        assert fatigue_row.shear_links.fatigue.utilization >= 0.0
    assert session.last_fatigue is result


def test_default_fatigue_settings_leave_detail_category_inputs_explicit() -> None:
    session = _session()
    session.set_preferences(
        ApplicationPreferences(
            units=session.preferences.units,
            eurocode=session.preferences.eurocode,
            analysis=session.preferences.analysis,
            design=session.preferences.design,
            actions=session.preferences.actions,
            local_deck=session.preferences.local_deck,
            fatigue=FatigueApplicationSettings(
                movement_step_m=15.0,
                section_step_m=15.0,
            ),
        )
    )
    session.run_native_lm1()
    session.run_extended_actions()
    session.run_design_interpretation()

    result = session.run_fatigue()

    assert result.search.cases
    assert not result.girders
    assert result.blockers
    assert any("longitudinal reinforcement fatigue" in item for item in result.blockers)
