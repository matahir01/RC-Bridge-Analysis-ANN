from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.moving_loads import (
    moving_train_max_moment,
    moving_train_max_support_reaction,
)
from rc_bridge.codes.common import LoadEffects

from .traffic import (
    HALaneLoad,
    ha_lane_load_bd37_01,
    hb_vehicle_train,
    notional_lane_layout_bd37_01,
)


@dataclass(frozen=True)
class HASimpleSpanLaneEnvelope:
    lane_load: HALaneLoad
    effects: LoadEffects
    max_moment_position_m: float
    shear_location: str
    status: str


@dataclass(frozen=True)
class HBSimpleSpanEnvelope:
    units: float
    governing_inner_axle_spacing_m: float
    effects: LoadEffects
    max_moment_position_m: float
    max_moment_lead_position_m: float
    max_reaction_side: str
    max_reaction_lead_position_m: float
    status: str


def ha_simple_span_lane_envelope_bd37_01(
    *,
    span_m: float,
    carriageway_width_m: float,
    lane_number: int,
) -> HASimpleSpanLaneEnvelope:
    """Return nominal HA UDL+KEL effects for one simple-span notional lane.

    The adverse length is taken as the full simply supported span. For maximum
    sagging moment the KEL is placed at midspan; for maximum support shear it is
    placed at the support. HA lane factors are applied before the effects are
    calculated. Transverse distribution to physical girders remains separate.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")

    layout = notional_lane_layout_bd37_01(carriageway_width_m)
    if not 1 <= lane_number <= layout.lane_count:
        raise ValueError("lane_number is outside the carriageway notional-lane layout.")

    lane = ha_lane_load_bd37_01(
        lane_number=lane_number,
        loaded_length_m=span_m,
        lane_width_m=layout.lane_width_m,
        total_notional_lanes=layout.lane_count,
    )
    moment_knm = lane.udl_kn_m * span_m**2 / 8.0 + lane.kel_kn * span_m / 4.0
    support_shear_kn = lane.udl_kn_m * span_m / 2.0 + lane.kel_kn

    return HASimpleSpanLaneEnvelope(
        lane_load=lane,
        effects=LoadEffects(moment_knm=moment_knm, shear_kn=support_shear_kn),
        max_moment_position_m=span_m / 2.0,
        shear_location="support",
        status=(
            "BD 37/01 nominal HA simple-span longitudinal envelope; transverse "
            "distribution and design load factors are applied separately"
        ),
    )


def ha_carriageway_simple_span_envelopes_bd37_01(
    *,
    span_m: float,
    carriageway_width_m: float,
) -> tuple[HASimpleSpanLaneEnvelope, ...]:
    layout = notional_lane_layout_bd37_01(carriageway_width_m)
    return tuple(
        ha_simple_span_lane_envelope_bd37_01(
            span_m=span_m,
            carriageway_width_m=carriageway_width_m,
            lane_number=lane_number,
        )
        for lane_number in range(1, layout.lane_count + 1)
    )


def hb_simple_span_envelope(
    *,
    span_m: float,
    units: float,
    inner_axle_spacing_m: float,
    movement_steps: int = 601,
    section_stations: int = 401,
    reaction_steps: int = 1201,
) -> HBSimpleSpanEnvelope:
    """Move one specified Type HB vehicle across a simply supported span."""
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")

    vehicle = hb_vehicle_train(units=units, inner_axle_spacing_m=inner_axle_spacing_m)
    moment, section_x, moment_lead = moving_train_max_moment(
        span_m,
        vehicle.train,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    reaction, side, reaction_lead = moving_train_max_support_reaction(
        span_m,
        vehicle.train,
        movement_steps=reaction_steps,
    )
    return HBSimpleSpanEnvelope(
        units=units,
        governing_inner_axle_spacing_m=inner_axle_spacing_m,
        effects=LoadEffects(moment_knm=moment, shear_kn=reaction),
        max_moment_position_m=section_x,
        max_moment_lead_position_m=moment_lead,
        max_reaction_side=side,
        max_reaction_lead_position_m=reaction_lead,
        status=(
            "Nominal BS 5400 Type HB moving-vehicle simple-span envelope; transverse "
            "placement/distribution and design factors remain separate"
        ),
    )


def governing_hb_simple_span_envelope(
    *,
    span_m: float,
    units: float,
    movement_steps: int = 601,
    section_stations: int = 401,
    reaction_steps: int = 1201,
) -> HBSimpleSpanEnvelope:
    """Return the HB spacing that governs simple-span sagging moment.

    The five prescribed inner axle spacings are checked. The returned moment and
    support shear are both taken from the selected moment-governing vehicle
    geometry; callers needing an independently shear-governing spacing should
    evaluate ``hb_simple_span_envelope`` for all spacings.
    """
    candidates = tuple(
        hb_simple_span_envelope(
            span_m=span_m,
            units=units,
            inner_axle_spacing_m=spacing,
            movement_steps=movement_steps,
            section_stations=section_stations,
            reaction_steps=reaction_steps,
        )
        for spacing in (6.0, 11.0, 16.0, 21.0, 26.0)
    )
    return max(candidates, key=lambda item: item.effects.moment_knm)
