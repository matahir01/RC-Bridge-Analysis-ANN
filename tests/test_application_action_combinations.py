import pytest

from rc_bridge.application.action_combinations import (
    BridgeActionCombinationFactors,
    build_integrated_action_combinations,
)
from rc_bridge.application.extended_actions import ExtendedActionSettings
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession


def _session(*, capacities: bool = True) -> BridgeApplicationSession:
    action_settings = ExtendedActionSettings(
        thermal_uniform_expansion_delta_c=30.0,
        thermal_uniform_contraction_delta_c=20.0,
        thermal_longitudinal_restraint_fraction=0.25,
        left_footway_width_m=1.5,
        right_footway_width_m=1.5,
        lm2_longitudinal_step_m=15.0,
        lm2_transverse_step_m=5.0,
        construction_execution_udl_kn_m2=1.0,
        bearing_longitudinal_capacity_per_bearing_kn=(500.0 if capacities else 0.0),
        bearing_movement_capacity_mm=(100.0 if capacities else 0.0),
        barrier_transverse_resistance_kn=(150.0 if capacities else 0.0),
        barrier_base_moment_resistance_knm=(100.0 if capacities else 0.0),
        wind_basic_velocity_m_s=40.0,
        bearing_transverse_capacity_per_bearing_kn=(
            100.0 if capacities else 0.0
        ),
    )
    return BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            ),
            actions=action_settings,
        ),
    )


def test_compatible_traffic_groups_are_enveloped_not_summed_together() -> None:
    session = _session()
    lm1 = session.run_native_lm1()
    actions = session.run_extended_actions()
    basis = session.preferences.eurocode
    suite = build_integrated_action_combinations(
        session.project,
        lm1,
        actions,
        settings=session.preferences.actions,
        factors=BridgeActionCombinationFactors(
            uls=basis.uls_factors,
            gamma_q_nontraffic=basis.gamma_q_nontraffic,
            psi1_lm2=basis.psi1_lm2,
            psi0_thermal_uls=basis.psi0_thermal_uls,
            psi0_thermal_sls=basis.psi0_thermal_sls,
            psi1_thermal=basis.psi1_thermal,
            psi2_thermal=basis.psi2_thermal,
        ),
    )

    centre = suite.girders[3]
    groups = {item.group for item in centre.situations}
    assert groups == {"gr1a", "gr1b", "gr2", "gr3"}
    assert " + " not in centre.governing_uls_moment_situation.replace(
        "LM1 + reduced footway", ""
    )
    assert centre.uls_effects.moment_knm == pytest.approx(
        max(item.uls_effects.moment_knm for item in centre.situations)
    )
    assert centre.uls_effects.shear_kn == pytest.approx(
        max(abs(item.uls_effects.shear_kn) for item in centre.situations)
    )


def test_bearing_path_combines_braking_and_thermal_with_explicit_capacities() -> None:
    session = _session()
    session.run_native_lm1()
    actions = session.run_extended_actions()
    basis = session.preferences.eurocode
    suite = build_integrated_action_combinations(
        session.project,
        session.last_lm1_search,
        actions,
        settings=session.preferences.actions,
        factors=BridgeActionCombinationFactors(
            uls=basis.uls_factors,
            gamma_q_nontraffic=basis.gamma_q_nontraffic,
            psi1_lm2=basis.psi1_lm2,
            psi0_thermal_uls=basis.psi0_thermal_uls,
            psi0_thermal_sls=basis.psi0_thermal_sls,
            psi1_thermal=basis.psi1_thermal,
            psi2_thermal=basis.psi2_thermal,
        ),
    )

    assert suite.bearing is not None
    assert suite.bearing.persistent_uls_total_longitudinal_kn > 0.0
    assert suite.bearing.persistent_uls_per_bearing_kn > 0.0
    assert suite.bearing.required_movement_mm > 0.0
    assert suite.bearing.force_utilization is not None
    assert suite.bearing.transverse_utilization is not None
    assert suite.bearing.persistent_uls_total_transverse_kn > 0.0
    assert suite.bearing.movement_utilization is not None


def test_unspecified_bearing_and_barrier_resistances_remain_design_blockers() -> None:
    session = _session(capacities=False)
    lm1 = session.run_native_lm1()
    actions = session.run_extended_actions()
    basis = session.preferences.eurocode
    suite = build_integrated_action_combinations(
        session.project,
        lm1,
        actions,
        settings=session.preferences.actions,
        factors=BridgeActionCombinationFactors(
            uls=basis.uls_factors,
            gamma_q_nontraffic=basis.gamma_q_nontraffic,
            psi1_lm2=basis.psi1_lm2,
            psi0_thermal_uls=basis.psi0_thermal_uls,
            psi0_thermal_sls=basis.psi0_thermal_sls,
            psi1_thermal=basis.psi1_thermal,
            psi2_thermal=basis.psi2_thermal,
        ),
    )

    assert not suite.complete_for_available_models
    assert "bearing longitudinal resistance not specified" in suite.blockers
    assert "bearing movement capacity not specified" in suite.blockers
    assert "bearing transverse wind resistance not specified" in suite.blockers
    assert "safety-barrier transverse resistance not specified" in suite.blockers
    assert "safety-barrier base-moment resistance not specified" in suite.blockers
