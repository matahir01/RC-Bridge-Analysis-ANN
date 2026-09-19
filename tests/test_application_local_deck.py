import pytest

from rc_bridge.application.extended_actions import ExtendedActionSettings
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession


def _session() -> BridgeApplicationSession:
    actions = ExtendedActionSettings(
        braking_enabled=False,
        thermal_enabled=False,
        pedestrian_enabled=False,
        lm2_enabled=True,
        lm2_longitudinal_step_m=15.0,
        lm2_transverse_step_m=5.0,
        barrier_impact_enabled=True,
        wind_enabled=False,
        construction_enabled=False,
    )
    return BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            ),
            actions=actions,
        ),
    )


def test_native_local_deck_design_checks_lm2_barrier_flexure_and_shear() -> None:
    session = _session()
    session.run_extended_actions()

    result = session.run_local_deck_design()

    assert result.lm2_case_count >= 3
    assert result.lm2_governing is not None
    assert result.uls_positive_moment_knm_per_m > 0.0
    assert result.uls_negative_moment_knm_per_m > 0.0
    assert result.accidental_negative_moment_knm_per_m >= 0.0
    assert result.bottom_transverse.arrangement.provided_area_mm2_per_m >= (
        result.bottom_transverse.governing_area_mm2_per_m
    )
    assert result.top_transverse.arrangement.provided_area_mm2_per_m >= (
        result.top_transverse.governing_area_mm2_per_m
    )
    assert result.bottom_transverse.effective_depth_m < pytest.approx(0.175)
    assert result.one_way_shear.design_shear_kn_per_m > 0.0
    assert result.one_way_shear.concrete_resistance_kn_per_m > 0.0
    assert session.last_local_deck_design is result


def test_local_deck_barrier_edge_responses_are_symmetric_for_default_bridge() -> None:
    session = _session()
    session.run_extended_actions()

    result = session.run_local_deck_design()

    assert result.barrier_left is not None
    assert result.barrier_right is not None
    assert result.barrier_left.maximum_abs_knm_per_m == pytest.approx(
        result.barrier_right.maximum_abs_knm_per_m,
        rel=1.0e-6,
        abs=1.0e-6,
    )


def test_local_deck_settings_round_trip_with_project_preferences() -> None:
    from rc_bridge.application.local_deck import LocalDeckSettings
    from rc_bridge.application.project_io import (
        dumps_project_document,
        loads_project_document,
    )

    project = application_default_project()
    preferences = ApplicationPreferences(
        local_deck=LocalDeckSettings(
            load_dispersion_horizontal_per_vertical=1.25,
            additional_dispersion_depth_m=0.03,
            nominal_bar_diameter_mm=20.0,
            available_bar_diameters_mm=(12.0, 16.0, 20.0),
            available_spacings_mm=(250.0, 200.0, 150.0),
        )
    )
    loaded = loads_project_document(
        dumps_project_document(
            project,
            application_preferences=preferences,
        )
    )

    assert loaded.application_preferences.local_deck == preferences.local_deck
