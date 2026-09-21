import pytest

from rc_bridge.core.models import (
    BridgeGeometry,
    DesignCode,
    DeckConstruction,
    ProjectInput,
    SupportSystem,
)
from rc_bridge.research.msc_profile import (
    MSC_ANN_TARGETS,
    evaluate_msc_deterministic_gate,
    msc_project_scope_blockers,
    require_msc_project_scope,
)


def test_default_reference_shape_is_inside_msc_project_scope() -> None:
    project = ProjectInput()

    assert msc_project_scope_blockers(project) == ()
    require_msc_project_scope(project)


def test_msc_deterministic_gate_is_ready_for_current_four_targets() -> None:
    gate = evaluate_msc_deterministic_gate(ProjectInput())

    assert gate.targets == (
        "g_flexure_knm",
        "g_shear_kn",
        "g_crack_mm",
        "g_deflection_mm",
    )
    assert gate.targets == MSC_ANN_TARGETS
    assert gate.project_scope_ready is True
    assert gate.verification_ready is True
    assert gate.ready is True
    gate.require_ready()


@pytest.mark.parametrize(
    "project,expected",
    (
        (
            ProjectInput(design_code=DesignCode.BS5400),
            "design_code must be Eurocode",
        ),
        (
            ProjectInput(
                geometry=BridgeGeometry(
                    span_lengths_m=[7.5, 7.5],
                    support_system=SupportSystem.CONTINUOUS,
                )
            ),
            "support_system must be simply supported",
        ),
        (
            ProjectInput(
                geometry=BridgeGeometry(
                    deck_construction=DeckConstruction(
                        precast_false_slab_depth_m=0.075,
                        in_situ_slab_depth_m=0.175,
                        false_slab_composite_participation=True,
                        in_situ_slab_composite_participation=True,
                    )
                )
            ),
            "false-slab composite participation",
        ),
    ),
)
def test_out_of_scope_projects_cannot_use_msc_gate(
    project: ProjectInput,
    expected: str,
) -> None:
    blockers = msc_project_scope_blockers(project)

    assert blockers
    with pytest.raises(RuntimeError, match=expected):
        require_msc_project_scope(project)
