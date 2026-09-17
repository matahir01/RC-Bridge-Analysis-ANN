import pytest

from rc_bridge.analysis.continuous_influence import AdverseUDLEffect
from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
    aggregate_lm1_continuous_section_effects,
)
from rc_bridge.codes.eurocode.lm1_effects import LM1ContinuousSectionEffect


def _effect(
    lane_number: int,
    *,
    response_kind: str,
    positive: float,
    negative: float,
) -> LM1ContinuousSectionEffect:
    return LM1ContinuousSectionEffect(
        lane_number=lane_number,
        response_kind=response_kind,
        response_span_index=0,
        response_position_m=7.5,
        line_load_kn_m=1.0,
        tandem_maximum_positive_effect=positive,
        tandem_minimum_negative_effect=negative,
        tandem_positive_lead_position_m=7.5,
        tandem_negative_lead_position_m=15.0,
        udl_maximum_positive_effect=0.0,
        udl_minimum_negative_effect=0.0,
        combined_maximum_positive_effect=positive,
        combined_minimum_negative_effect=negative,
        status="test",
    )


def _lane_distributions() -> list[LaneGirderDistribution]:
    return [
        LaneGirderDistribution(
            lane_number=1,
            moment_fractions=(0.75, 0.25),
            shear_fractions=(0.60, 0.40),
            method="validated_grillage_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=(0.25, 0.75),
            shear_fractions=(0.40, 0.60),
            method="validated_grillage_lane_2",
        ),
    ]


def test_continuous_moment_distribution_retains_positive_and_negative_effects() -> None:
    effects = [
        _effect(1, response_kind="moment", positive=100.0, negative=-40.0),
        _effect(2, response_kind="moment", positive=80.0, negative=-20.0),
    ]
    remaining = AdverseUDLEffect(
        line_load_kn_m=5.0,
        maximum_positive_effect=20.0,
        minimum_negative_effect=-10.0,
        full_length_effect=10.0,
        positive_loaded_length_m=10.0,
        negative_loaded_length_m=5.0,
        status="test",
    )
    remaining_distribution = RemainingAreaGirderDistribution(
        moment_fractions=(0.5, 0.5),
        shear_fractions=(0.5, 0.5),
        method="validated_remaining_area",
    )

    result = aggregate_lm1_continuous_section_effects(
        effects,
        _lane_distributions(),
        remaining_area_effect=remaining,
        remaining_area_distribution=remaining_distribution,
    )

    assert result[0].maximum_positive_effect == pytest.approx(105.0)
    assert result[0].minimum_negative_effect == pytest.approx(-40.0)
    assert result[1].maximum_positive_effect == pytest.approx(95.0)
    assert result[1].minimum_negative_effect == pytest.approx(-30.0)
    assert result[0].response_kind == "moment"
    assert "validated_grillage_lane_1" in result[0].method
    assert "validated_remaining_area" in result[0].method


def test_continuous_shear_distribution_uses_shear_fractions() -> None:
    effects = [
        _effect(1, response_kind="shear", positive=100.0, negative=-40.0),
        _effect(2, response_kind="shear", positive=80.0, negative=-20.0),
    ]

    result = aggregate_lm1_continuous_section_effects(effects, _lane_distributions())

    assert result[0].maximum_positive_effect == pytest.approx(92.0)
    assert result[0].minimum_negative_effect == pytest.approx(-32.0)
    assert result[1].maximum_positive_effect == pytest.approx(88.0)
    assert result[1].minimum_negative_effect == pytest.approx(-28.0)
    assert result[0].response_kind == "shear"


def test_continuous_distribution_rejects_mixed_response_sections() -> None:
    first = _effect(1, response_kind="moment", positive=100.0, negative=-40.0)
    second = LM1ContinuousSectionEffect(
        **{
            **first.__dict__,
            "lane_number": 2,
            "response_position_m": 6.0,
        }
    )

    with pytest.raises(ValueError, match="common response section"):
        aggregate_lm1_continuous_section_effects([first, second], _lane_distributions())
