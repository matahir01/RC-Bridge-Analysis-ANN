from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.analysis.continuous_influence import (
    AdverseUDLEffect,
    ContinuousSectionInfluenceLine,
    InfluenceResponseKind,
    MovingTrainInfluenceEffect,
    adverse_udl_effect,
    moving_train_influence_effect,
    section_influence_line,
)
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    NotionalLaneLayout,
    lm1_remaining_area_udl_kn_m2,
    lm1_tandem_train,
    notional_lane_layout,
)
from rc_bridge.codes.eurocode.lm1_effects import lane_udl_line_load_kn_m


@dataclass(frozen=True)
class LM1ContinuousLaneSectionEffect:
    lane_number: int
    response_kind: InfluenceResponseKind
    response_span_index: int
    response_position_m: float
    lane_width_m: float
    udl_line_load_kn_m: float
    tandem_effect: MovingTrainInfluenceEffect
    udl_effect: AdverseUDLEffect
    maximum_positive_effect: float
    minimum_negative_effect: float
    status: str


@dataclass(frozen=True)
class LM1ContinuousRemainingAreaEffect:
    response_kind: InfluenceResponseKind
    response_span_index: int
    response_position_m: float
    remaining_width_m: float
    udl_kn_m2: float
    line_load_kn_m: float
    udl_effect: AdverseUDLEffect
    maximum_positive_effect: float
    minimum_negative_effect: float
    status: str


@dataclass(frozen=True)
class LM1ContinuousCarriagewaySectionEffect:
    response_kind: InfluenceResponseKind
    response_span_index: int
    response_position_m: float
    lane_layout: NotionalLaneLayout
    lane_effects: tuple[LM1ContinuousLaneSectionEffect, ...]
    remaining_area_effect: LM1ContinuousRemainingAreaEffect
    summed_adverse_positive_effect: float
    summed_adverse_negative_effect: float
    status: str


def _lane_effect_from_influence(
    influence_line: ContinuousSectionInfluenceLine,
    *,
    lane_number: int,
    lane_width_m: float,
    factors: LM1AdjustmentFactors | None,
    movement_steps: int,
) -> LM1ContinuousLaneSectionEffect:
    if lane_number < 1:
        raise ValueError("LM1 lane number must be at least 1.")
    if lane_width_m <= 0.0:
        raise ValueError("LM1 lane width must be positive.")

    train = lm1_tandem_train(lane_number, factors)
    line_load = lane_udl_line_load_kn_m(lane_number, lane_width_m, factors)
    tandem_effect = moving_train_influence_effect(
        influence_line,
        train,
        movement_steps=movement_steps,
    )
    udl_effect = adverse_udl_effect(influence_line, line_load)
    return LM1ContinuousLaneSectionEffect(
        lane_number=lane_number,
        response_kind=influence_line.response_kind,
        response_span_index=influence_line.response_span_index,
        response_position_m=influence_line.response_position_m,
        lane_width_m=lane_width_m,
        udl_line_load_kn_m=line_load,
        tandem_effect=tandem_effect,
        udl_effect=udl_effect,
        maximum_positive_effect=(
            tandem_effect.maximum_positive_effect + udl_effect.maximum_positive_effect
        ),
        minimum_negative_effect=(
            tandem_effect.minimum_negative_effect + udl_effect.minimum_negative_effect
        ),
        status=(
            "EN 1991-2 LM1 lane section effect from the lane tandem plus UDL loaded on "
            "the adverse influence-line region; transverse distribution is not included"
        ),
    )


def lm1_lane_continuous_section_effect(
    spans: tuple[BeamSpan, ...],
    *,
    response_span_index: int,
    response_position_m: float,
    lane_number: int,
    lane_width_m: float = 3.0,
    factors: LM1AdjustmentFactors | None = None,
    response_kind: InfluenceResponseKind = "moment",
    influence_positions: int = 401,
    movement_steps: int = 1201,
) -> LM1ContinuousLaneSectionEffect:
    influence = section_influence_line(
        spans,
        response_span_index=response_span_index,
        response_position_m=response_position_m,
        response_kind=response_kind,
        load_positions=influence_positions,
    )
    return _lane_effect_from_influence(
        influence,
        lane_number=lane_number,
        lane_width_m=lane_width_m,
        factors=factors,
        movement_steps=movement_steps,
    )


def lm1_carriageway_continuous_section_effect(
    spans: tuple[BeamSpan, ...],
    *,
    carriageway_width_m: float,
    response_span_index: int,
    response_position_m: float,
    factors: LM1AdjustmentFactors | None = None,
    response_kind: InfluenceResponseKind = "moment",
    influence_positions: int = 401,
    movement_steps: int = 1201,
) -> LM1ContinuousCarriagewaySectionEffect:
    """Return LM1 longitudinal effects at one section of a continuous beam.

    One numerical influence line is reused for all LM1 notional lanes. Tandem
    systems are moved independently in each lane, and each lane UDL is integrated
    over only the influence-line region that is adverse for the requested sign.
    The remaining carriageway-area UDL is treated separately. These are
    longitudinal effects for the carriageway as a whole; transverse distribution
    to individual girders remains a separate analysis step.
    """
    layout = notional_lane_layout(carriageway_width_m)
    influence = section_influence_line(
        spans,
        response_span_index=response_span_index,
        response_position_m=response_position_m,
        response_kind=response_kind,
        load_positions=influence_positions,
    )
    lanes = tuple(
        _lane_effect_from_influence(
            influence,
            lane_number=lane_number,
            lane_width_m=layout.lane_width_m,
            factors=factors,
            movement_steps=movement_steps,
        )
        for lane_number in range(1, layout.lane_count + 1)
    )

    remaining_pressure = lm1_remaining_area_udl_kn_m2(factors)
    remaining_line = remaining_pressure * layout.remaining_width_m
    remaining_udl = adverse_udl_effect(influence, remaining_line)
    remaining = LM1ContinuousRemainingAreaEffect(
        response_kind=response_kind,
        response_span_index=response_span_index,
        response_position_m=response_position_m,
        remaining_width_m=layout.remaining_width_m,
        udl_kn_m2=remaining_pressure,
        line_load_kn_m=remaining_line,
        udl_effect=remaining_udl,
        maximum_positive_effect=remaining_udl.maximum_positive_effect,
        minimum_negative_effect=remaining_udl.minimum_negative_effect,
        status=(
            "EN 1991-2 LM1 remaining-area UDL applied only on adverse influence-line regions"
        ),
    )

    return LM1ContinuousCarriagewaySectionEffect(
        response_kind=response_kind,
        response_span_index=response_span_index,
        response_position_m=response_position_m,
        lane_layout=layout,
        lane_effects=lanes,
        remaining_area_effect=remaining,
        summed_adverse_positive_effect=(
            sum(item.maximum_positive_effect for item in lanes)
            + remaining.maximum_positive_effect
        ),
        summed_adverse_negative_effect=(
            sum(item.minimum_negative_effect for item in lanes)
            + remaining.minimum_negative_effect
        ),
        status=(
            "Continuous-span EN 1991-2 LM1 longitudinal section envelope. Each notional "
            "lane is positioned independently for an adverse longitudinal response; "
            "transverse girder distribution and National Annex verification remain separate"
        ),
    )
