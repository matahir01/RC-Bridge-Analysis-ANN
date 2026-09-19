import pytest

from rc_bridge.application.load_cases import (
    ApplicationLoadCaseFields,
    SurfacingExtent,
    application_combination_summary,
    eurocode_variable_action_scope,
    permanent_load_audit,
)
from rc_bridge.application.preferences import (
    ApplicationPreferences,
    EurocodeApplicationBasis,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession


def _loaded_project():
    project = application_default_project()
    return ApplicationLoadCaseFields(
        surfacing_thickness_m=0.080,
        surfacing_density_kn_m3=22.0,
        surfacing_extent=SurfacingExtent.CARRIAGEWAY,
        left_barrier_kn_m=10.0,
        right_barrier_kn_m=10.0,
        left_services_kn_m=2.0,
        right_services_kn_m=2.0,
        left_services_y_m=-4.8,
        right_services_y_m=4.8,
    ).apply(project)


def test_application_load_fields_write_physical_project_actions() -> None:
    project = _loaded_project()

    assert len(project.permanent_actions.surfacing_layers) == 1
    surfacing = project.permanent_actions.surfacing_layers[0]
    assert surfacing.name == "APP:surfacing"
    assert surfacing.y_start_m == pytest.approx(-3.5)
    assert surfacing.y_end_m == pytest.approx(3.5)
    assert surfacing.pressure_kn_m2 == pytest.approx(1.76)

    names = {item.name for item in project.permanent_actions.line_actions}
    assert names == {
        "APP:left barrier",
        "APP:right barrier",
        "APP:left services",
        "APP:right services",
    }


def test_permanent_load_audit_derives_girder_and_deck_self_weight() -> None:
    project = _loaded_project()
    audit = permanent_load_audit(project)

    assert len(audit) == 7
    centre = audit[3]
    assert centre.girder_self_weight_kn_m == pytest.approx(9.5)
    assert centre.false_slab_kn_m == pytest.approx(3.1875)
    assert centre.in_situ_slab_kn_m == pytest.approx(7.4375)
    assert centre.surfacing_kn_m == pytest.approx(2.992)
    assert centre.total_equivalent_kn_m > (
        centre.girder_self_weight_kn_m
        + centre.false_slab_kn_m
        + centre.in_situ_slab_kn_m
    )

    left_edge = audit[0]
    right_edge = audit[-1]
    assert left_edge.barriers_kn_m == pytest.approx(10.0)
    assert right_edge.barriers_kn_m == pytest.approx(10.0)
    assert left_edge.services_kn_m > 0.0
    assert right_edge.services_kn_m > 0.0


def test_load_fields_round_trip_from_project() -> None:
    original = ApplicationLoadCaseFields(
        surfacing_thickness_m=0.060,
        surfacing_density_kn_m3=23.0,
        surfacing_extent=SurfacingExtent.FULL_DECK,
        left_barrier_kn_m=8.5,
        right_barrier_kn_m=9.0,
        left_services_kn_m=1.5,
        right_services_kn_m=1.8,
        left_services_y_m=-4.5,
        right_services_y_m=4.4,
    )
    project = original.apply(application_default_project())

    recovered = ApplicationLoadCaseFields.from_project(project)

    assert recovered == original


def test_variable_action_scope_does_not_hide_unimplemented_actions() -> None:
    scope = {item.name: item.status for item in eurocode_variable_action_scope()}

    assert scope["LM1 vertical road traffic"] == "implemented"
    assert scope["Braking / acceleration"].startswith("action implemented")
    assert scope["Thermal action"].startswith("kinematics implemented")
    assert scope["Pedestrian / footway live load"].startswith("implemented")
    assert scope["LM2 local axle"].startswith("implemented")
    assert scope["Vehicle impact on safety barrier"].startswith(
        "local accidental action implemented"
    )
    assert scope["Construction-stage actions"].startswith("implemented")
    assert scope["Wind action"] == "not wired"


def test_session_combines_permanent_actions_with_native_lm1() -> None:
    project = _loaded_project()
    preferences = ApplicationPreferences(
        eurocode=EurocodeApplicationBasis(
            gamma_g_unfavourable=1.35,
            gamma_g_favourable=1.0,
            gamma_q_traffic=1.5,
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        )
    )
    session = BridgeApplicationSession(project, preferences=preferences)
    search = session.run_native_lm1(
        grid_spacing_m=15.0,
        longitudinal_step_m=15.0,
        max_exhaustive_tandem_combinations=20,
    )

    rows = session.combination_summary()

    assert len(rows) == 7
    assert {row.girder_index for row in rows} == set(range(1, 8))
    centre = rows[3]
    assert centre.uls.moment_knm == pytest.approx(
        1.35 * centre.permanent_characteristic.moment_knm
        + 1.5 * centre.traffic_characteristic.moment_knm
    )
    assert centre.sls_frequent.moment_knm == pytest.approx(
        centre.permanent_characteristic.moment_knm
        + 0.75 * centre.traffic_characteristic.moment_knm
    )

    direct = application_combination_summary(
        project,
        search,
        uls_factors=preferences.eurocode.uls_factors,
        sls_factors=preferences.eurocode.sls_factors,
    )
    assert direct == rows


def test_project_save_open_retains_application_permanent_actions(tmp_path) -> None:
    session = BridgeApplicationSession(_loaded_project())
    path = session.save(tmp_path / "load_cases.json")
    opened = BridgeApplicationSession.open(path)

    assert opened.project.permanent_actions == session.project.permanent_actions
    assert opened.load_case_fields() == session.load_case_fields()
