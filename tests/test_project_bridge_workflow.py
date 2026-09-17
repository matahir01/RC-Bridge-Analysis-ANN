import pytest

from rc_bridge.core.models import ProjectInput, SupportSystem
from rc_bridge.workflow.project_bridge import (
    internal_girder_deck_self_weight_kn_m,
    run_project_lm1_equal_share_verification,
)


def test_reference_project_internal_girder_deck_self_weight() -> None:
    project = ProjectInput()
    assert internal_girder_deck_self_weight_kn_m(project) == pytest.approx(10.625)


def test_reference_project_lm1_verification_uses_7m_carriageway_and_7_girders() -> None:
    project = ProjectInput()
    result = run_project_lm1_equal_share_verification(
        project,
        movement_steps=21,
        section_stations=31,
    )
    assert result.lane_layout.carriageway_width_m == pytest.approx(7.0)
    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)
    assert len(result.girder_effects) == 7
    assert all("verification_only" in item.method for item in result.girder_effects)


def test_project_equal_share_verification_rejects_continuous_system() -> None:
    project = ProjectInput()
    project.geometry.support_system = SupportSystem.CONTINUOUS
    with pytest.raises(ValueError, match="simple spans only"):
        run_project_lm1_equal_share_verification(project)
