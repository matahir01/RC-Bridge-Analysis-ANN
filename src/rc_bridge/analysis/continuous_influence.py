from __future__ import annotations

import bisect
import dataclasses
import typing

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    SpanPointLoad,
    member_section_response,
    solve_continuous_beam,
)
from rc_bridge.analysis.moving_loads import AxleTrain, positioned_axles

InfluenceResponseKind = typing.Literal["moment", "shear"]


@dataclasses.dataclass(frozen=True)
class ContinuousSectionInfluenceLine:
    response_kind: InfluenceResponseKind
    response_span_index: int
    response_position_m: float
    load_positions_m: tuple[float, ...]
    ordinates: tuple[float, ...]
    bridge_length_m: float
    unit_load_kn: float
    status: str


@dataclasses.dataclass(frozen=True)
class AdverseUDLEffect:
    line_load_kn_m: float
    maximum_positive_effect: float
    minimum_negative_effect: float
    full_length_effect: float
    positive_loaded_length_m: float
    negative_loaded_length_m: float
    status: str


@dataclasses.dataclass(frozen=True)
class MovingTrainInfluenceEffect:
    maximum_positive_effect: float
    maximum_positive_lead_position_m: float
    minimum_negative_effect: float
    minimum_negative_lead_position_m: float
    movement_steps: int
    status: str


def _span_boundaries(spans: tuple[BeamSpan, ...]) -> tuple[float, ...]:
    boundaries = [0.0]
    for span in spans:
        boundaries.append(boundaries[-1] + span.length_m)
    return tuple(boundaries)


def _unit_load_spans(
    spans: tuple[BeamSpan, ...],
    global_position_m: float,
) -> tuple[BeamSpan, ...]:
    boundaries = _span_boundaries(spans)
    total_length = boundaries[-1]
    if not 0.0 <= global_position_m <= total_length:
        raise ValueError("Influence-line unit load lies outside the bridge length.")

    if abs(global_position_m - total_length) <= 1e-12:
        loaded_span_index = len(spans) - 1
        local_position = spans[-1].length_m
    else:
        loaded_span_index = max(0, bisect.bisect_right(boundaries, global_position_m) - 1)
        loaded_span_index = min(loaded_span_index, len(spans) - 1)
        local_position = global_position_m - boundaries[loaded_span_index]

    return tuple(
        BeamSpan(
            length_m=span.length_m,
            ei_kn_m2=span.ei_kn_m2,
            point_loads=(SpanPointLoad(1.0, local_position, "unit influence load"),)
            if index == loaded_span_index
            else (),
        )
        for index, span in enumerate(spans)
    )


def section_influence_line(
    spans: tuple[BeamSpan, ...],
    *,
    response_span_index: int,
    response_position_m: float,
    response_kind: InfluenceResponseKind = "moment",
    load_positions: int = 401,
) -> ContinuousSectionInfluenceLine:
    """Numerically generate a continuous-beam influence line for one section response.

    The input spans contribute geometry and EI only. Any UDL/static point loads on
    them are intentionally ignored because an influence line is generated from a
    moving unit load on the unloaded linear system.
    """
    if not spans:
        raise ValueError("At least one span is required for an influence line.")
    if not 0 <= response_span_index < len(spans):
        raise IndexError("response_span_index is outside the span list.")
    if not 0.0 <= response_position_m <= spans[response_span_index].length_m:
        raise ValueError("Response position must lie within the target span.")
    if response_kind not in ("moment", "shear"):
        raise ValueError("response_kind must be 'moment' or 'shear'.")
    if load_positions < 2:
        raise ValueError("At least two influence-line load positions are required.")

    geometry_spans = tuple(
        BeamSpan(length_m=span.length_m, ei_kn_m2=span.ei_kn_m2) for span in spans
    )
    total_length = sum(span.length_m for span in geometry_spans)
    positions = tuple(
        total_length * index / (load_positions - 1) for index in range(load_positions)
    )

    ordinates: list[float] = []
    for global_position in positions:
        loaded_spans = _unit_load_spans(geometry_spans, global_position)
        solution = solve_continuous_beam(loaded_spans)
        response = member_section_response(
            loaded_spans[response_span_index],
            solution.members[response_span_index],
            response_position_m,
        )
        value = response.moment_knm if response_kind == "moment" else response.shear_kn
        ordinates.append(value)

    return ContinuousSectionInfluenceLine(
        response_kind=response_kind,
        response_span_index=response_span_index,
        response_position_m=response_position_m,
        load_positions_m=positions,
        ordinates=tuple(ordinates),
        bridge_length_m=total_length,
        unit_load_kn=1.0,
        status=(
            "Numerical unit-load influence line for a linear Euler-Bernoulli continuous beam"
        ),
    )


def _interpolated_ordinate(
    influence_line: ContinuousSectionInfluenceLine,
    global_position_m: float,
) -> float:
    positions = influence_line.load_positions_m
    ordinates = influence_line.ordinates
    if len(positions) != len(ordinates) or len(positions) < 2:
        raise ValueError("Influence line requires matching position/ordinate vectors.")
    if not 0.0 <= global_position_m <= influence_line.bridge_length_m:
        raise ValueError("Influence-line interpolation position lies outside the bridge.")

    index = bisect.bisect_right(positions, global_position_m) - 1
    if index < 0:
        return ordinates[0]
    if index >= len(positions) - 1:
        return ordinates[-1]

    x0 = positions[index]
    x1 = positions[index + 1]
    y0 = ordinates[index]
    y1 = ordinates[index + 1]
    if x1 <= x0:
        raise ValueError("Influence-line load positions must be strictly increasing.")
    ratio = (global_position_m - x0) / (x1 - x0)
    return y0 + ratio * (y1 - y0)


def moving_train_influence_effect(
    influence_line: ContinuousSectionInfluenceLine,
    train: AxleTrain,
    *,
    movement_steps: int = 1201,
) -> MovingTrainInfluenceEffect:
    """Envelope an arbitrary axle train using a previously generated influence line."""
    if movement_steps < 2:
        raise ValueError("At least two movement steps are required.")
    if influence_line.unit_load_kn <= 0.0:
        raise ValueError("Influence-line unit load must be positive.")

    lead_start = 0.0
    lead_end = influence_line.bridge_length_m + train.train_length_m
    max_effect = float("-inf")
    max_lead = lead_start
    min_effect = float("inf")
    min_lead = lead_start

    for step in range(movement_steps):
        lead = lead_start + (lead_end - lead_start) * step / (movement_steps - 1)
        axles = positioned_axles(train, lead, influence_line.bridge_length_m)
        effect = sum(
            axle.magnitude_kn
            * _interpolated_ordinate(influence_line, axle.position_m)
            / influence_line.unit_load_kn
            for axle in axles
        )
        if effect > max_effect:
            max_effect = effect
            max_lead = lead
        if effect < min_effect:
            min_effect = effect
            min_lead = lead

    return MovingTrainInfluenceEffect(
        maximum_positive_effect=max_effect,
        maximum_positive_lead_position_m=max_lead,
        minimum_negative_effect=min_effect,
        minimum_negative_lead_position_m=min_lead,
        movement_steps=movement_steps,
        status=(
            "Moving axle-train effect evaluated by linear interpolation of a numerical "
            "continuous-beam influence line"
        ),
    )


def _piecewise_signed_areas_and_lengths(
    positions: tuple[float, ...],
    ordinates: tuple[float, ...],
) -> tuple[float, float, float, float]:
    positive_area = 0.0
    negative_area = 0.0
    positive_length = 0.0
    negative_length = 0.0

    for index in range(len(positions) - 1):
        x0 = positions[index]
        x1 = positions[index + 1]
        y0 = ordinates[index]
        y1 = ordinates[index + 1]
        length = x1 - x0
        if length <= 0.0:
            raise ValueError("Influence-line load positions must be strictly increasing.")

        if y0 >= 0.0 and y1 >= 0.0:
            positive_area += 0.5 * (y0 + y1) * length
            positive_length += length
            continue
        if y0 <= 0.0 and y1 <= 0.0:
            negative_area += 0.5 * (y0 + y1) * length
            negative_length += length
            continue

        zero_fraction = -y0 / (y1 - y0)
        zero_x = x0 + zero_fraction * length
        if y0 > 0.0:
            positive_area += 0.5 * y0 * (zero_x - x0)
            positive_length += zero_x - x0
            negative_area += 0.5 * y1 * (x1 - zero_x)
            negative_length += x1 - zero_x
        else:
            negative_area += 0.5 * y0 * (zero_x - x0)
            negative_length += zero_x - x0
            positive_area += 0.5 * y1 * (x1 - zero_x)
            positive_length += x1 - zero_x

    return positive_area, negative_area, positive_length, negative_length


def adverse_udl_effect(
    influence_line: ContinuousSectionInfluenceLine,
    line_load_kn_m: float,
) -> AdverseUDLEffect:
    """Integrate UDL over positive/negative influence regions separately.

    ``maximum_positive_effect`` corresponds to loading only the positive influence
    region. ``minimum_negative_effect`` corresponds to loading only the negative
    influence region. Their sum equals the effect of loading the full bridge under
    the piecewise-linear influence-line approximation.
    """
    if line_load_kn_m < 0.0:
        raise ValueError("UDL line load cannot be negative.")
    if len(influence_line.load_positions_m) != len(influence_line.ordinates):
        raise ValueError("Influence-line positions and ordinates must have equal lengths.")
    if len(influence_line.load_positions_m) < 2:
        raise ValueError("Influence line must contain at least two ordinates.")

    positive_area, negative_area, positive_length, negative_length = (
        _piecewise_signed_areas_and_lengths(
            influence_line.load_positions_m,
            influence_line.ordinates,
        )
    )
    positive_effect = line_load_kn_m * positive_area
    negative_effect = line_load_kn_m * negative_area
    return AdverseUDLEffect(
        line_load_kn_m=line_load_kn_m,
        maximum_positive_effect=positive_effect,
        minimum_negative_effect=negative_effect,
        full_length_effect=positive_effect + negative_effect,
        positive_loaded_length_m=positive_length,
        negative_loaded_length_m=negative_length,
        status=(
            "UDL integrated over positive and negative influence-line regions separately; "
            "piecewise-linear interpolation is used between unit-load stations"
        ),
    )
