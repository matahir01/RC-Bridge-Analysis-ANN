from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import (
    AggregatedGirderTrafficEffect,
    LaneGirderDistribution,
    aggregate_lm1_lane_envelopes,
)
from rc_bridge.codes.eurocode.en1991_2 import LM1AdjustmentFactors, NotionalLaneLayout, notional_lane_layout
from rc_bridge.codes.eurocode.lm1_effects import LM1Envelope, lm1_carriageway_simple_span_envelopes


@dataclass(frozen=True)
class BridgeLM1TrafficResult:
    lane_layout: NotionalLaneLayout
    lane_envelopes: tuple[LM1Envelope, ...]
    girder_effects: tuple[AggregatedGirderTrafficEffect, ...]


def run_simple_span_lm1_bridge_traffic(
    *,
    span_m: float,
    carriageway_width_m: float,
    lane_distributions: list[LaneGirderDistribution],
    factors: LM1AdjustmentFactors | None = None,
) -> BridgeLM1TrafficResult:
    """Calculate lane-wise LM1 envelopes and map them to individual girders.

    ``carriageway_width_m`` must be the trafficked carriageway width, not the
    overall deck width. Lane distribution factors remain caller-supplied so a
    validated grillage model can be used without hiding its assumptions.
    """
    layout = notional_lane_layout(carriageway_width_m)
    expected_lanes = set(range(1, layout.lane_count + 1))
    supplied_lanes = {item.lane_number for item in lane_distributions}
    if supplied_lanes != expected_lanes:
        raise ValueError(
            "Lane distributions must be supplied for exactly the EN 1991-2 "
            f"notional lanes {sorted(expected_lanes)}; got {sorted(supplied_lanes)}."
        )

    envelopes = lm1_carriageway_simple_span_envelopes(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        factors=factors,
    )
    girder_effects = aggregate_lm1_lane_envelopes(envelopes, lane_distributions)
    return BridgeLM1TrafficResult(
        lane_layout=layout,
        lane_envelopes=tuple(envelopes),
        girder_effects=tuple(girder_effects),
    )
