from __future__ import annotations

from dataclasses import dataclass

from .loads import PointLoad
from .point_loads import simply_supported_reactions as point_reactions


@dataclass(frozen=True)
class CombinedEnvelopeResult:
    max_moment_knm: float
    moment_position_m: float
    max_abs_shear_kn: float
    shear_position_m: float


def _udl_moment(span_m: float, w_kn_m: float, x_m: float) -> float:
    reaction = w_kn_m * span_m / 2.0
    return reaction * x_m - w_kn_m * x_m**2 / 2.0


def _udl_shear(span_m: float, w_kn_m: float, x_m: float) -> float:
    reaction = w_kn_m * span_m / 2.0
    return reaction - w_kn_m * x_m


def _point_moment(span_m: float, loads: list[PointLoad], x_m: float) -> float:
    r_left, _ = point_reactions(span_m, loads)
    m = r_left * x_m
    for load in loads:
        if load.position_m <= x_m:
            m -= load.magnitude_kn * (x_m - load.position_m)
    return m


def _point_shear(span_m: float, loads: list[PointLoad], x_m: float) -> float:
    r_left, _ = point_reactions(span_m, loads)
    v = r_left
    for load in loads:
        if load.position_m <= x_m:
            v -= load.magnitude_kn
    return v


def combined_udl_point_envelope(
    span_m: float,
    full_span_udl_kn_m: float,
    point_loads: list[PointLoad],
    stations: int = 801,
) -> CombinedEnvelopeResult:
    """Envelope a full-span UDL and arbitrary point loads on a simple span.

    This is a mechanics routine. Code-specific load models must be assembled
    outside this module before being passed in.
    """
    if span_m <= 0:
        raise ValueError("Span must be positive.")
    if full_span_udl_kn_m < 0:
        raise ValueError("UDL cannot be negative.")
    if stations < 3:
        raise ValueError("At least three stations are required.")

    max_m = float("-inf")
    max_m_x = 0.0
    max_abs_v = -1.0
    max_v_x = 0.0

    for i in range(stations):
        x = span_m * i / (stations - 1)
        m = _udl_moment(span_m, full_span_udl_kn_m, x) + _point_moment(
            span_m, point_loads, x
        )
        v = _udl_shear(span_m, full_span_udl_kn_m, x) + _point_shear(
            span_m, point_loads, x
        )
        if m > max_m:
            max_m = m
            max_m_x = x
        if abs(v) > max_abs_v:
            max_abs_v = abs(v)
            max_v_x = x

    return CombinedEnvelopeResult(
        max_moment_knm=max_m,
        moment_position_m=max_m_x,
        max_abs_shear_kn=max_abs_v,
        shear_position_m=max_v_x,
    )
