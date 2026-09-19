from rc_bridge.application.gui_presenters import (
    analysis_dashboard_data,
    analysis_girder_diagram,
    bridge_preview_data,
    deck_dashboard_data,
    design_dashboard_data,
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


def test_bridge_preview_tracks_project_geometry_and_physical_section() -> None:
    project = application_default_project()

    preview = bridge_preview_data(project)

    assert preview.total_length_m == sum(float(v) for v in project.geometry.span_lengths_m)
    assert preview.deck_width_m == float(project.geometry.deck_width_m)
    assert len(preview.girder_y_m) == project.geometry.girder_count
    assert preview.girder_outline_m
    assert preview.girder_depth_m == float(project.geometry.girder_depth_m)
    assert (
        preview.false_slab_depth_m + preview.in_situ_slab_depth_m
        == float(project.geometry.deck_structural_depth_m)
    )


def test_analysis_dashboard_exposes_exact_governing_diagrams_for_all_metrics() -> None:
    session = _session()
    result = session.run_native_lm1()

    dashboard = analysis_dashboard_data(result)

    assert len(dashboard.girders) == session.project.geometry.girder_count
    assert dashboard.max_moment_knm > 0.0
    assert dashboard.max_shear_kn > 0.0
    assert dashboard.evaluated_case_count > 0

    for metric, unit in (
        ("Moment", "kNm"),
        ("Shear", "kN"),
        ("Torsion", "kNm"),
        ("Deflection", "mm"),
    ):
        diagram = analysis_girder_diagram(
            result,
            girder_index=1,
            metric=metric,
        )
        assert diagram.unit == unit
        assert diagram.case_id in result.governing_case_ids
        assert len(diagram.stations_m) == len(diagram.values)
        assert len(diagram.stations_m) >= 2


def test_design_and_deck_presenters_follow_current_engine_results() -> None:
    session = _session()
    session.run_native_lm1()
    session.run_extended_actions()
    deck = session.run_local_deck_design()
    design = session.run_design_interpretation()

    design_view = design_dashboard_data(design)
    deck_view = deck_dashboard_data(deck)

    assert len(design_view.girders) == session.project.geometry.girder_count
    assert design_view.governing_girder_index is not None
    assert design_view.worst_utilization >= 0.0
    assert all(item.provided_bars for item in design_view.girders)
    assert all(item.provided_links for item in design_view.girders)

    assert deck_view.stations_y_m
    assert len(deck_view.stations_y_m) == len(deck_view.permanent_moments_knm_per_m)
    assert deck_view.bottom_reinforcement
    assert deck_view.top_reinforcement
    assert deck_view.status in {"PASS", "CHECK"}
