import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous import (
    GlobalBeamPointLoad,
    ProjectContinuousLoadCase,
    run_project_continuous_load_case,
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


def test_project_continuous_workflow_rejects_simple_span_project() -> None:
    project = ProjectInput()
    load_case = ProjectContinuousLoadCase(
        ei_kn_m2_by_span=(1.0e6,),
        udl_kn_m_by_span=(10.0,),
    )
    with pytest.raises(ValueError, match="CONTINUOUS"):
        run_project_continuous_load_case(project, load_case)
