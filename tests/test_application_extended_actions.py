import pytest

from rc_bridge.application.extended_actions import (
    ExtendedActionSettings,
    barrier_impact_action,
    braking_action,
    construction_action,
    lm2_action,
    pedestrian_action,
    run_extended_actions,
    thermal_action,
)
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.project_io import dumps_project_document, loads_project_document
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.core.models import PermanentActionStage


def _settings() -> ExtendedActionSettings:
    return ExtendedActionSettings(
        braking_enabled=True,
        braking_alpha_q1=1.0,
        braking_alpha_Q1=1.0,
        thermal_enabled=True,
        thermal_uniform_expansion_delta_c=30.0,
        thermal_uniform_contraction_delta_c=20.0,
        thermal_gradient_heat_c=15.0,
        thermal_gradient_cool_c=8.0,
        pedestrian_enabled=True,
        pedestrian_load_kn_m2=5.0,
        left_footway_width_m=1.5,
        right_footway_width_m=1.5,
        lm2_enabled=True,
        lm2_longitudinal_step_m=15.0,
        lm2_transverse_step_m=5.0,
        barrier_impact_enabled=True,
        construction_enabled=True,
        construction_execution_udl_kn_m2=1.0,
    )


def test_braking_action_matches_first_generation_en1991_2_reference_formula() -> None:
    result = braking_action(application_default_project(), _settings())

    assert result.loaded_length_m == pytest.approx(15.0)
    assert result.lane_width_m == pytest.approx(3.0)
    assert result.uncapped_force_kn == pytest.approx(400.5)
    assert result.characteristic_force_kn == pytest.approx(400.5)
    assert result.minimum_force_kn == pytest.approx(180.0)
    assert result.maximum_force_kn == pytest.approx(900.0)


def test_thermal_action_reports_free_movement_gradient_and_restraint_benchmark() -> None:
    result = thermal_action(application_default_project(), _settings())

    assert result.expansion_movement_mm == pytest.approx(4.5)
    assert result.contraction_movement_mm == pytest.approx(3.0)
    assert result.heat_gradient_curvature_per_m == pytest.approx(0.000125)
    assert result.heat_gradient_free_midspan_mm == pytest.approx(3.515625)
    assert result.full_restraint_expansion_force_kn > 0.0
    assert result.climate_input_complete


def test_pedestrian_action_solves_two_defined_footways_on_native_grillage() -> None:
    result = pedestrian_action(
        application_default_project(),
        _settings(),
        grid_spacing_m=15.0,
    )

    assert result.applied
    assert result.loaded_area_m2 == pytest.approx(45.0)
    assert result.total_characteristic_load_kn == pytest.approx(225.0)
    assert len(result.girders) == 7
    assert max(item.effects.moment_knm for item in result.girders) > 0.0


def test_lm2_action_scans_carriageway_and_retains_contact_patch_pressure() -> None:
    result = lm2_action(
        application_default_project(),
        _settings(),
        grid_spacing_m=15.0,
    )

    assert result.axle_load_kn == pytest.approx(400.0)
    assert result.wheel_load_kn == pytest.approx(200.0)
    assert result.contact_pressure_kn_m2 == pytest.approx(
        200.0 / (0.35 * 0.60)
    )
    assert result.evaluated_case_count == 9
    assert len(result.girders) == 7
    assert len(result.governing_positions) == 7


def test_barrier_impact_calculates_horizontal_local_action_without_faking_3d_solve() -> None:
    result = barrier_impact_action(_settings())

    assert result.transverse_characteristic_force_kn == pytest.approx(100.0)
    assert result.accompanying_vertical_wheel_load_kn == pytest.approx(225.0)
    assert result.barrier_base_moment_knm == pytest.approx(50.0)
    assert "vertical grillage does not analyse the horizontal force" in result.status


def test_construction_action_separates_all_three_physical_stages() -> None:
    result = construction_action(application_default_project(), _settings())

    assert len(result.girders) == 21
    assert {item.stage for item in result.girders} == set(PermanentActionStage)
    precast = [
        item
        for item in result.girders
        if item.girder_index == 4
        and item.stage is PermanentActionStage.PRECAST_GIRDER
    ][0]
    wet = [
        item
        for item in result.girders
        if item.girder_index == 4
        and item.stage is PermanentActionStage.DECK_CONSTRUCTION
    ][0]
    assert precast.characteristic_max_moment_knm > 0.0
    assert wet.characteristic_max_moment_knm > 0.0
    assert wet.execution_udl_kn_m > 0.0


def test_extended_actions_preferences_round_trip() -> None:
    project = application_default_project()
    preferences = ApplicationPreferences(actions=_settings())
    loaded = loads_project_document(
        dumps_project_document(
            project,
            application_preferences=preferences,
        )
    )

    assert loaded.application_preferences.actions == preferences.actions


def test_session_runs_all_six_actions_and_retains_result() -> None:
    session = BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            ),
            actions=_settings(),
        ),
    )

    result = session.run_extended_actions()

    assert result.braking is not None
    assert result.thermal is not None
    assert result.pedestrian is not None
    assert result.lm2 is not None
    assert result.barrier_impact is not None
    assert result.construction is not None
    assert not result.unresolved_inputs
    assert session.last_extended_actions is result


def test_default_extended_actions_keep_unknown_project_inputs_visible() -> None:
    result = run_extended_actions(
        application_default_project(),
        ExtendedActionSettings(
            lm2_enabled=False,
            construction_enabled=False,
        ),
        grid_spacing_m=15.0,
    )

    assert "thermal uniform expansion/contraction ranges" in result.unresolved_inputs
    assert "footway widths for pedestrian loading" in result.unresolved_inputs
