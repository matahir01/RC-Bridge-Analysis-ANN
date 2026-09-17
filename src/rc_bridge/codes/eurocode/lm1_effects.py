from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.combined_effects import combined_udl_point_envelope
from rc_bridge.analysis.moving_loads import positioned_axles
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    lm1_characteristic_lane_load,
    lm1_tandem_train,
    notional_lane_layout,
)


@dataclass(frozen=True)
class LM1Envelope:
    max_moment_knm: float
    moment_position_m: float
    moment_governing_lead_position_m: float
    max_abs_shear_kn: float
    shear_position_m: float
    shear_governing_lead_position_m: float
    lane_number: int


def lane_udl_line_load_kn_m(
    lane_number: int,
    lane_width_m: float,
    factors: LM1AdjustmentFactors | None = None,
) -> float:
    lane = lm1_characteristic_lane_load(lane_number, factors)
    return lane.udl_kn_m2 * lane_width_m


def lm1_lane_simple_span_envelope(
    span_m: float,
    lane_number: int,
    lane_width_m: float = 3.0,
    factors: LM1AdjustmentFactors | None = None,
    movement_steps: int = 401,
    section_stations: int = 401,
) -> LM1Envelope:
    if span_m <= 0:
        raise ValueError("Span must be positive.")
    if lane_width_m <= 0:
        raise ValueError("Lane width must be positive.")
    if movement_steps < 2:
        raise ValueError("At least two movement steps are required.")

    train = lm1_tandem_train(lane_number, factors)
    udl_line = lane_udl_line_load_kn_m(lane_number, lane_width_m, factors)
    end = span_m + train.train_length_m

    best_m = float("-inf")
    best_m_x = 0.0
    best_m_lead = 0.0
    best_v = -1.0
    best_v_x = 0.0
    best_v_lead = 0.0

    for i in range(movement_steps):
        lead = end * i / (movement_steps - 1)
        axles = positioned_axles(train, lead, span_m)
        result = combined_udl_point_envelope(
            span_m,
            udl_line,
            axles,
            stations=section_stations,
        )
        if result.max_moment_knm > best_m:
            best_m = result.max_moment_knm
            best_m_x = result.moment_position_m
            best_m_lead = lead
        if result.max_abs_shear_kn > best_v:
            best_v = result.max_abs_shear_kn
            best_v_x = result.shear_position_m
            best_v_lead = lead

    return LM1Envelope(
        max_moment_knm=best_m,
        moment_position_m=best_m_x,
        moment_governing_lead_position_m=best_m_lead,
        max_abs_shear_kn=best_v,
        shear_position_m=best_v_x,
        shear_governing_lead_position_m=best_v_lead,
        lane_number=lane_number,
    )


def lm1_carriageway_simple_span_envelopes(
    span_m: float,
    carriageway_width_m: float,
    factors: LM1AdjustmentFactors | None = None,
) -> list[LM1Envelope]:
    layout = notional_lane_layout(carriageway_width_m)
    return [
        lm1_lane_simple_span_envelope(
            span_m,
            lane_number=i,
            lane_width_m=layout.lane_width_m,
            factors=factors,
        )
        for i in range(1, layout.lane_count + 1)
    ]
