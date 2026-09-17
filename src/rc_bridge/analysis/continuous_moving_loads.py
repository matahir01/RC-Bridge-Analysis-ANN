from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    SpanPointLoad,
    member_span_envelope,
    solve_continuous_beam,
)
from rc_bridge.analysis.continuous_deflection import member_span_deflection_envelope
from rc_bridge.analysis.loads import PointLoad
from rc_bridge.analysis.moving_loads import AxleTrain, positioned_axles


@dataclass(frozen=True)
class ContinuousMovingSpanEnvelope:
    span_index: int
    max_sagging_moment_knm: float
    max_sagging_position_m: float
    max_sagging_lead_position_m: float
    min_hogging_moment_knm: float
    min_hogging_position_m: float
    min_hogging_lead_position_m: float
    max_abs_shear_kn: float
    max_abs_shear_position_m: float
    max_abs_shear_lead_position_m: float
    maximum_upward_displacement_m: float
    maximum_upward_displacement_position_m: float
    maximum_upward_displacement_lead_position_m: float
    minimum_downward_displacement_m: float
    minimum_downward_displacement_position_m: float
    minimum_downward_displacement_lead_position_m: float
    max_abs_displacement_m: float
    max_abs_displacement_position_m: float
    max_abs_displacement_lead_position_m: float


@dataclass(frozen=True)
class ContinuousMovingSupportEnvelope:
    node_index: int
    max_vertical_reaction_kn: float
    max_reaction_lead_position_m: float
    min_vertical_reaction_kn: float
    min_reaction_lead_position_m: float


@dataclass(frozen=True)
class ContinuousMovingLoadEnvelopeResult:
    span_envelopes: tuple[ContinuousMovingSpanEnvelope, ...]
    support_envelopes: tuple[ContinuousMovingSupportEnvelope, ...]
    max_abs_displacement_m: float
    max_abs_displacement_span_index: int
    max_abs_displacement_local_position_m: float
    max_abs_displacement_global_position_m: float
    max_abs_displacement_lead_position_m: float
    movement_steps: int
    section_stations: int
    lead_start_m: float
    lead_end_m: float
    status: str


def _map_global_loads_to_spans(
    spans: tuple[BeamSpan, ...],
    loads: list[PointLoad],
) -> tuple[tuple[SpanPointLoad, ...], ...]:
    boundaries = [0.0]
    for span in spans:
        boundaries.append(boundaries[-1] + span.length_m)
    total_length = boundaries[-1]

    mapped: list[list[SpanPointLoad]] = [[] for _ in spans]
    for load in loads:
        if load.position_m > total_length + 1e-12:
            raise ValueError("Moving axle lies beyond the continuous beam length.")
        if abs(load.position_m - total_length) <= 1e-12:
            span_index = len(spans) - 1
            local_position = spans[-1].length_m
        else:
            span_index = max(0, bisect_right(boundaries, load.position_m) - 1)
            span_index = min(span_index, len(spans) - 1)
            local_position = load.position_m - boundaries[span_index]
        mapped[span_index].append(
            SpanPointLoad(
                magnitude_kn=load.magnitude_kn,
                position_m=local_position,
                label=load.label,
            )
        )
    return tuple(tuple(items) for items in mapped)


def moving_train_continuous_envelope(
    spans: tuple[BeamSpan, ...],
    train: AxleTrain,
    *,
    movement_steps: int = 601,
    section_stations: int = 201,
) -> ContinuousMovingLoadEnvelopeResult:
    """Move an axle train across a continuous beam and envelope longitudinal effects.

    ``spans`` may contain static UDLs and static point loads; the moving train is
    superimposed on those loads at each lead-axle position. The routine is
    code-neutral: traffic-code axle definitions are supplied through ``AxleTrain``.

    Each physical span records moment, shear and vertical-displacement extrema.
    Both upward and downward displacement are retained because loading one span of
    a continuous bridge can lift a remote span. Support reaction extrema include
    possible uplift.
    """
    if not spans:
        raise ValueError("At least one span is required for a moving-load envelope.")
    if movement_steps < 2:
        raise ValueError("At least two movement steps are required.")
    if section_stations < 2:
        raise ValueError("At least two section stations are required.")

    total_length = sum(span.length_m for span in spans)
    lead_start = 0.0
    lead_end = total_length + train.train_length_m

    span_state = [
        {
            "max_sagging_moment_knm": float("-inf"),
            "max_sagging_position_m": 0.0,
            "max_sagging_lead_position_m": 0.0,
            "min_hogging_moment_knm": float("inf"),
            "min_hogging_position_m": 0.0,
            "min_hogging_lead_position_m": 0.0,
            "max_abs_shear_kn": float("-inf"),
            "max_abs_shear_position_m": 0.0,
            "max_abs_shear_lead_position_m": 0.0,
            "maximum_upward_displacement_m": float("-inf"),
            "maximum_upward_displacement_position_m": 0.0,
            "maximum_upward_displacement_lead_position_m": 0.0,
            "minimum_downward_displacement_m": float("inf"),
            "minimum_downward_displacement_position_m": 0.0,
            "minimum_downward_displacement_lead_position_m": 0.0,
            "max_abs_displacement_m": float("-inf"),
            "max_abs_displacement_position_m": 0.0,
            "max_abs_displacement_lead_position_m": 0.0,
        }
        for _ in spans
    ]
    support_count = len(spans) + 1
    support_state = [
        {
            "max_vertical_reaction_kn": float("-inf"),
            "max_reaction_lead_position_m": 0.0,
            "min_vertical_reaction_kn": float("inf"),
            "min_reaction_lead_position_m": 0.0,
        }
        for _ in range(support_count)
    ]

    for step in range(movement_steps):
        lead_position = lead_start + (lead_end - lead_start) * step / (movement_steps - 1)
        global_axles = positioned_axles(train, lead_position, total_length)
        mapped_axles = _map_global_loads_to_spans(spans, global_axles)
        loaded_spans = tuple(
            BeamSpan(
                length_m=span.length_m,
                ei_kn_m2=span.ei_kn_m2,
                udl_kn_m=span.udl_kn_m,
                point_loads=span.point_loads + mapped_axles[index],
            )
            for index, span in enumerate(spans)
        )
        solution = solve_continuous_beam(loaded_spans)

        for index, span in enumerate(loaded_spans):
            envelope = member_span_envelope(
                span,
                solution.members[index],
                stations=section_stations,
            )
            deflection = member_span_deflection_envelope(
                span,
                solution.members[index],
                solution.nodes[index],
                stations=section_stations,
            )
            state = span_state[index]
            if envelope.max_sagging_moment_knm > state["max_sagging_moment_knm"]:
                state["max_sagging_moment_knm"] = envelope.max_sagging_moment_knm
                state["max_sagging_position_m"] = envelope.max_sagging_position_m
                state["max_sagging_lead_position_m"] = lead_position
            if envelope.min_hogging_moment_knm < state["min_hogging_moment_knm"]:
                state["min_hogging_moment_knm"] = envelope.min_hogging_moment_knm
                state["min_hogging_position_m"] = envelope.min_hogging_position_m
                state["min_hogging_lead_position_m"] = lead_position
            if envelope.max_abs_shear_kn > state["max_abs_shear_kn"]:
                state["max_abs_shear_kn"] = envelope.max_abs_shear_kn
                state["max_abs_shear_position_m"] = envelope.max_abs_shear_position_m
                state["max_abs_shear_lead_position_m"] = lead_position
            if (
                deflection.maximum_upward_displacement_m
                > state["maximum_upward_displacement_m"]
            ):
                state["maximum_upward_displacement_m"] = (
                    deflection.maximum_upward_displacement_m
                )
                state["maximum_upward_displacement_position_m"] = (
                    deflection.maximum_upward_position_m
                )
                state["maximum_upward_displacement_lead_position_m"] = lead_position
            if (
                deflection.minimum_downward_displacement_m
                < state["minimum_downward_displacement_m"]
            ):
                state["minimum_downward_displacement_m"] = (
                    deflection.minimum_downward_displacement_m
                )
                state["minimum_downward_displacement_position_m"] = (
                    deflection.minimum_downward_position_m
                )
                state["minimum_downward_displacement_lead_position_m"] = lead_position
            if deflection.max_abs_displacement_m > state["max_abs_displacement_m"]:
                state["max_abs_displacement_m"] = deflection.max_abs_displacement_m
                state["max_abs_displacement_position_m"] = deflection.max_abs_position_m
                state["max_abs_displacement_lead_position_m"] = lead_position

        for node in solution.nodes:
            state = support_state[node.node_index]
            reaction = node.vertical_reaction_kn
            if reaction > state["max_vertical_reaction_kn"]:
                state["max_vertical_reaction_kn"] = reaction
                state["max_reaction_lead_position_m"] = lead_position
            if reaction < state["min_vertical_reaction_kn"]:
                state["min_vertical_reaction_kn"] = reaction
                state["min_reaction_lead_position_m"] = lead_position

    span_envelopes = tuple(
        ContinuousMovingSpanEnvelope(span_index=index, **state)
        for index, state in enumerate(span_state)
    )
    support_envelopes = tuple(
        ContinuousMovingSupportEnvelope(node_index=index, **state)
        for index, state in enumerate(support_state)
    )
    displacement_span_index = max(
        range(len(span_envelopes)),
        key=lambda index: span_envelopes[index].max_abs_displacement_m,
    )
    displacement_span = span_envelopes[displacement_span_index]
    displacement_global_position = (
        sum(span.length_m for span in spans[:displacement_span_index])
        + displacement_span.max_abs_displacement_position_m
    )
    return ContinuousMovingLoadEnvelopeResult(
        span_envelopes=span_envelopes,
        support_envelopes=support_envelopes,
        max_abs_displacement_m=displacement_span.max_abs_displacement_m,
        max_abs_displacement_span_index=displacement_span_index,
        max_abs_displacement_local_position_m=(
            displacement_span.max_abs_displacement_position_m
        ),
        max_abs_displacement_global_position_m=displacement_global_position,
        max_abs_displacement_lead_position_m=(
            displacement_span.max_abs_displacement_lead_position_m
        ),
        movement_steps=movement_steps,
        section_stations=section_stations,
        lead_start_m=lead_start,
        lead_end_m=lead_end,
        status=(
            "Code-neutral moving axle-train envelope on an Euler-Bernoulli continuous beam; "
            "moment, shear, support reaction and vertical displacement extrema are retained. "
            "Traffic-code definitions and transverse distribution remain separate"
        ),
    )
