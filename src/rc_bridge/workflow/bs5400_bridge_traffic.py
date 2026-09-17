from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import (
    AggregatedGirderTrafficEffect,
    LaneGirderDistribution,
)
from rc_bridge.codes.bs5400.traffic import (
    BS5400NotionalLaneLayout,
    notional_lane_layout_bd37_01,
)
from rc_bridge.codes.bs5400.traffic_effects import (
    HASimpleSpanLaneEnvelope,
    ha_carriageway_simple_span_envelopes_bd37_01,
)


@dataclass(frozen=True)
class BS5400HABridgeTrafficResult:
    lane_layout: BS5400NotionalLaneLayout
    lane_envelopes: tuple[HASimpleSpanLaneEnvelope, ...]
    girder_effects: tuple[AggregatedGirderTrafficEffect, ...]


def aggregate_ha_lane_envelopes(
    envelopes: tuple[HASimpleSpanLaneEnvelope, ...],
    distributions: list[LaneGirderDistribution],
) -> tuple[AggregatedGirderTrafficEffect, ...]:
    """Map lane-wise HA longitudinal envelopes to physical girders."""
    if not envelopes or not distributions:
        raise ValueError("HA envelopes and lane distributions are required.")

    by_lane = {item.lane_number: item for item in distributions}
    if len(by_lane) != len(distributions):
        raise ValueError("Duplicate HA lane distribution definitions are not allowed.")

    girder_count = distributions[0].girder_count
    if any(item.girder_count != girder_count for item in distributions):
        raise ValueError("All HA lane distributions must use the same girder count.")

    moments = [0.0] * girder_count
    shears = [0.0] * girder_count
    methods: set[str] = set()

    for envelope in envelopes:
        lane_number = envelope.lane_load.lane_number
        distribution = by_lane.get(lane_number)
        if distribution is None:
            raise ValueError(f"Missing transverse distribution for HA lane {lane_number}.")
        methods.add(distribution.method)
        for index in range(girder_count):
            moments[index] += (
                envelope.effects.moment_knm * distribution.moment_fractions[index]
            )
            shears[index] += (
                envelope.effects.shear_kn * distribution.shear_fractions[index]
            )

    method_label = "+".join(sorted(methods))
    return tuple(
        AggregatedGirderTrafficEffect(
            girder_index=index + 1,
            moment_knm=moments[index],
            shear_kn=shears[index],
            method=method_label,
        )
        for index in range(girder_count)
    )


def run_simple_span_ha_bridge_traffic_bd37_01(
    *,
    span_m: float,
    carriageway_width_m: float,
    lane_distributions: list[LaneGirderDistribution],
) -> BS5400HABridgeTrafficResult:
    """Calculate BD 37/01 HA lane effects and distribute them to girders.

    Carriageways below 5 m have a separately loaded remaining width under BD
    37/01. That case is rejected in this first bridge-level workflow rather than
    silently omitting the remaining-area load.
    """
    layout = notional_lane_layout_bd37_01(carriageway_width_m)
    if layout.remaining_width_m > 0.0:
        raise NotImplementedError(
            "BD 37/01 carriageway remaining-area loading below 5 m is not yet "
            "implemented in the bridge-level HA workflow."
        )

    expected_lanes = set(range(1, layout.lane_count + 1))
    supplied_lanes = {item.lane_number for item in lane_distributions}
    if supplied_lanes != expected_lanes:
        raise ValueError(
            "HA distributions must be supplied for exactly the BD 37/01 notional "
            f"lanes {sorted(expected_lanes)}; got {sorted(supplied_lanes)}."
        )

    envelopes = ha_carriageway_simple_span_envelopes_bd37_01(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
    )
    effects = aggregate_ha_lane_envelopes(envelopes, lane_distributions)
    return BS5400HABridgeTrafficResult(
        lane_layout=layout,
        lane_envelopes=envelopes,
        girder_effects=effects,
    )
