import pytest

from rc_bridge.analysis.moving_loads import AxleTrain
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous import (
    GlobalBeamPointLoad,
    ProjectContinuousLoadCase,
    ProjectContinuousMovingLoadCase,
    run_project_continuous_load_case,
    run_project_continuous_moving_train,
)


def _continuous_project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )


def test_project_two_span_udl_reproduces_continuous_beam_support_moment() -> None:
    project = _continuous_project()
    result = run_project_continuous_load_case(
        project,
        ProjectContinuousLoadCase(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            udl_kn_m_by_span=(20.0, 20.0),
            name="symmetric permanent load",
        ),
    )

    assert result.total_applied_vertical_load_kn == pytest.approx(400.0)
    assert result.total_vertical_reaction_kn == pytest.approx(400.0)
    assert result.solution.nodes[1].vertical_reaction_kn == pytest.approx(250.0)
    assert result.solution.members[0].right_moment_knm == pytest.approx(-250.0)
    assert result.solution.members[1].left_moment_knm == pytest.approx(-250.0)
    assert result.span_envelopes[0].max_sagging_moment_knm == pytest.approx(
        140.625,
        rel=1e-4,
    )
    assert len(result.span_deflection_envelopes) == 2
    assert result.span_deflection_envelopes[0].max_abs_displacement_m == pytest.approx(
        result.span_deflection_envelopes[1].max_abs_displacement_m,
        rel=1e-12,
    )
    assert result.span_deflection_envelopes[0].minimum_downward_displacement_m < 0.0
    assert result.max_abs_vertical_displacement_m == pytest.approx(
        result.span_deflection_envelopes[0].max_abs_displacement_m,
        rel=1e-12,
    )
    assert result.max_abs_vertical_displacement_span_index == 0
    assert result.max_abs_vertical_displacement_global_position_m == pytest.approx(
        result.max_abs_vertical_displacement_local_position_m
    )


def test_project_continuous_global_point_load_mapping_preserves_equilibrium() -> None:
    project = _continuous_project()
    result = run_project_continuous_load_case(
        project,
        ProjectContinuousLoadCase(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            udl_kn_m_by_span=(0.0, 0.0),
            point_loads=(
                GlobalBeamPointLoad(100.0, 5.0, "span 1 point"),
                GlobalBeamPointLoad(80.0, 12.5, "span 2 point"),
                GlobalBeamPointLoad(40.0, 10.0, "internal support point"),
            ),
        ),
    )

    assert result.total_applied_vertical_load_kn == pytest.approx(220.0)
    assert result.total_vertical_reaction_kn == pytest.approx(220.0)
    assert sum(node.vertical_reaction_kn for node in result.solution.nodes) == pytest.approx(
        220.0
    )
    assert result.max_abs_vertical_displacement_m > 0.0
    assert 0.0 <= result.max_abs_vertical_displacement_global_position_m <= 20.0


def test_project_continuous_moving_train_uses_project_span_geometry() -> None:
    project = _continuous_project()
    train = AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,))
    result = run_project_continuous_moving_train(
        project,
        ProjectContinuousMovingLoadCase(
            train=train,
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            movement_steps=81,
            section_stations=81,
            name="single moving axle",
        ),
    )

    assert result.load_case_name == "single moving axle"
    assert result.envelope.lead_start_m == pytest.approx(0.0)
    assert result.envelope.lead_end_m == pytest.approx(20.0)
    assert len(result.envelope.span_envelopes) == 2
    assert len(result.envelope.support_envelopes) == 3
    assert result.envelope.span_envelopes[0].max_sagging_moment_knm == pytest.approx(
        result.envelope.span_envelopes[1].max_sagging_moment_knm,
        rel=1e-10,
    )


def test_project_continuous_moving_train_rejects_span_count_mismatch() -> None:
    project = _continuous_project()
    load_case = ProjectContinuousMovingLoadCase(
        train=AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,)),
        ei_kn_m2_by_span=(1.0e6,),
    )
    with pytest.raises(ValueError, match="span count"):
        run_project_continuous_moving_train(project, load_case)


def test_project_continuous_workflow_rejects_simple_span_project() -> None:
    project = ProjectInput()
    load_case = ProjectContinuousLoadCase(
        ei_kn_m2_by_span=(1.0e6,),
        udl_kn_m_by_span=(10.0,),
    )
    with pytest.raises(ValueError, match="CONTINUOUS"):
        run_project_continuous_load_case(project, load_case)

    moving_case = ProjectContinuousMovingLoadCase(
        train=AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,)),
        ei_kn_m2_by_span=(1.0e6,),
    )
    with pytest.raises(ValueError, match="CONTINUOUS"):
        run_project_continuous_moving_train(project, moving_case)
