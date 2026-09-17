from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import (
    AggregatedGirderTrafficEffect,
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
    aggregate_lm1_lane_envelopes,
)
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    NotionalLaneLayout,
    notional_lane_layout,
)
from rc_bridge.codes.eurocode.lm1_effects import (
    LM1Envelope,
    LM1RemainingAreaEnvelope,
    lm1_carriageway_simple_span_envelopes,
    lm1_remaining_area_simple_span_envelope,
)


@dataclass(frozen=True)
class BridgeLM1TrafficResult:
    lane_layout: NotionalLaneLayout
    lane_envelopes: tuple[LM1Envelope, ...]
    remaining_area_envelope: LM1RemainingAreaEnvelope
    girder_effects: tuple[AggregatedGirderTrafficEffect, ...]


def run_simple_span_lm1_bridge_traffic(
    *,
    span_m: float,
    carriageway_width_m: float,
    lane_distributions: list[LaneGirderDistribution],
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None,
    factors: LM1AdjustmentFactors | None = None,
    movement_steps: int = 401,
    section_stations: int = 401,
) -> BridgeLM1TrafficResult:
    """Calculate LM1 traffic effects and map them to individual girders.

    ``carriageway_width_m`` is the trafficked carriageway width, not the total
    deck width. Notional-lane and remaining-area transverse factors stay
    caller-supplied so validated grillage results can be used without hiding
    their assumptions.
    """
    layout = notional_lane_layout(carriageway_width_m)
    expected_lanes = set(range(1, layout.lane_count + 1))
    supplied_lanes = {item.lane_number for item in lane_distributions}
    if supplied_lanes != expected_lanes:
        raise ValueError(
            "Lane distributions must be supplied for exactly the EN 1991-2 "
            f"notional lanes {sorted(expected_lanes)}; got {sorted(supplied_lanes)}."
        )
    if layout.remaining_width_m > 0.0 and remaining_area_distribution is None:
        raise ValueError(
            "The EN 1991-2 remaining carriageway area has non-zero width; "
            "a transverse distribution must be supplied for it."
        )

    envelopes = lm1_carriageway_simple_span_envelopes(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        factors=factors,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    remaining_area = lm1_remaining_area_simple_span_envelope(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        factors=factors,
    )

    if layout.remaining_width_m > 0.0:
        girder_effects = aggregate_lm1_lane_envelopes(
            envelopes,
            lane_distributions,
            remaining_area_envelope=remaining_area,
            remaining_area_distribution=remaining_area_distribution,
        )
    else:
        girder_effects = aggregate_lm1_lane_envelopes(envelopes, lane_distributions)

    return BridgeLM1TrafficResult(
        lane_layout=layout,
        lane_envelopes=tuple(envelopes),
        remaining_area_envelope=remaining_area,
        girder_effects=tuple(girder_effects),
    )
