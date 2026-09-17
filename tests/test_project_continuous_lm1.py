import pytest

from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous_lm1 import (
    ProjectContinuousLM1SectionInput,
    run_project_continuous_lm1_section,
)


def _project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[15.0, 15.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )


def _lane_distributions() -> tuple[LaneGirderDistribution, ...]:
    lane_1 = (0.20, 0.18, 0.16, 0.14, 0.12, 0.10, 0.10)
    lane_2 = tuple(reversed(lane_1))
    return (
        LaneGirderDistribution(
            lane_number=1,
            moment_fractions=lane_1,
            shear_fractions=lane_1,
            method="validated_test_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=lane_2,
            shear_fractions=lane_2,
            method="validated_test_lane_2",
        ),
    )


def _remaining_distribution() -> RemainingAreaGirderDistribution:
    fractions = tuple(1.0 / 7.0 for _ in range(7))
    return RemainingAreaGirderDistribution(
        moment_fractions=fractions,
        shear_fractions=fractions,
        method="validated_test_remaining_area",
    )


def test_project_continuous_lm1_maps_support_hogging_to_all_girders() -> None:
    result = run_project_continuous_lm1_section(
        _project(),
        ProjectContinuousLM1SectionInput(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            response_span_index=0,
            response_position_m=15.0,
            response_kind="moment",
            lane_distributions=_lane_distributions(),
            remaining_area_distribution=_remaining_distribution(),
            influence_positions=101,
            movement_steps=121,
        ),
    )

    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)
    assert len(result.lane_effects) == 2
    assert len(result.girder_effects) == 7
    assert result.remaining_area_effect is not None
    assert any(item.minimum_negative_effect < 0.0 for item in result.girder_effects)
    assert "validated_test_lane_1" in result.traffic_distribution_method

    total_positive = sum(item.maximum_positive_effect for item in result.girder_effects)
    total_negative = sum(item.minimum_negative_effect for item in result.girder_effects)
    source_positive = sum(
        item.combined_maximum_positive_effect for item in result.lane_effects
    ) + result.remaining_area_effect.maximum_positive_effect
    source_negative = sum(
        item.combined_minimum_negative_effect for item in result.lane_effects
    ) + result.remaining_area_effect.minimum_negative_effect
    assert total_positive == pytest.approx(source_positive)
    assert total_negative == pytest.approx(source_negative)


def test_project_continuous_lm1_requires_remaining_area_distribution() -> None:
    with pytest.raises(ValueError, match="remaining-area distribution"):
        run_project_continuous_lm1_section(
            _project(),
            ProjectContinuousLM1SectionInput(
                ei_kn_m2_by_span=(1.0e6, 1.0e6),
                response_span_index=0,
                response_position_m=7.5,
                response_kind="moment",
                lane_distributions=_lane_distributions(),
                influence_positions=31,
                movement_steps=41,
            ),
        )


def test_project_continuous_lm1_requires_complete_lane_distribution_set() -> None:
    with pytest.raises(ValueError, match="every LM1 notional lane"):
        run_project_continuous_lm1_section(
            _project(),
            ProjectContinuousLM1SectionInput(
                ei_kn_m2_by_span=(1.0e6, 1.0e6),
                response_span_index=0,
                response_position_m=7.5,
                response_kind="moment",
                lane_distributions=(_lane_distributions()[0],),
                remaining_area_distribution=_remaining_distribution(),
                influence_positions=31,
                movement_steps=41,
            ),
        )
