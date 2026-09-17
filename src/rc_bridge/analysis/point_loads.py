from __future__ import annotations

from dataclasses import dataclass

from .loads import PointLoad


@dataclass(frozen=True)
class BeamResponse:
    reaction_left_kn: float
    reaction_right_kn: float
    moment_knm: float
    shear_kn: float


def simply_supported_reactions(span_m: float, loads: list[PointLoad]) -> tuple[float, float]:
    if span_m <= 0:
        raise ValueError("Span must be positive.")
    for load in loads:
        if load.position_m > span_m:
            raise ValueError("Point load lies outside the beam span.")

    total_load = sum(load.magnitude_kn for load in loads)
    moment_about_left = sum(load.magnitude_kn * load.position_m for load in loads)
    rb = moment_about_left / span_m
    ra = total_load - rb
    return ra, rb


def section_response(
    span_m: float,
    loads: list[PointLoad],
    x_m: float,
) -> BeamResponse:
    """Return reactions plus left-face shear and bending moment at x."""
    if not 0 <= x_m <= span_m:
        raise ValueError("Section location must lie on the span.")

    ra, rb = simply_supported_reactions(span_m, loads)
    loads_left = [load for load in loads if load.position_m <= x_m]
    shear = ra - sum(load.magnitude_kn for load in loads_left)
    moment = ra * x_m - sum(
        load.magnitude_kn * (x_m - load.position_m) for load in loads_left
    )
    return BeamResponse(ra, rb, moment, shear)


def moment_envelope(
    span_m: float,
    loads: list[PointLoad],
    stations: int = 401,
) -> tuple[float, float]:
    """Return (maximum sagging moment, position) from a station scan."""
    if stations < 2:
        raise ValueError("At least two stations are required.")
    best_m = float("-inf")
    best_x = 0.0
    for i in range(stations):
        x = span_m * i / (stations - 1)
        m = section_response(span_m, loads, x).moment_knm
        if m > best_m:
            best_m = m
            best_x = x
    return best_m, best_x
