from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rc_bridge.analysis.grillage_solver import GrillageMemberEndResult
from rc_bridge.export.verification_model import VerificationModel

StationSide = Literal["left", "right"]


@dataclass(frozen=True)
class LongitudinalGrillageStationResponse:
    """Signed internal actions at one longitudinal grillage member end.

    Moment is sagging-positive. Shear is positive on the left face of a member
    running in increasing global x. Torsion follows the same increasing-x member
    convention. The project grillage generator creates longitudinal members in
    increasing x, which makes the sign convention stable across traffic and
    staged permanent-action models.
    """

    member_id: int
    node_id: int
    member_end: Literal["I", "J"]
    side: StationSide
    x_m: float
    y_m: float
    moment_knm: float
    shear_kn: float
    torsion_knm: float


def longitudinal_station_end_response(
    model: VerificationModel,
    member_results: Sequence[GrillageMemberEndResult],
    *,
    target_y_m: float,
    x_m: float,
    side: StationSide,
    span_start_m: float,
    span_end_m: float,
    tolerance_m: float = 1.0e-9,
) -> LongitudinalGrillageStationResponse:
    """Recover one span-side response at a fixed longitudinal grid station.

    side='left' selects the member immediately to the left of x_m;
    side='right' selects the member immediately to the right. The span
    bounds disambiguate the two physical members meeting at an internal support.

    The function intentionally operates at model grid stations. This is exact
    for member-end actions, including UDL-loaded permanent-action members, and
    avoids interpolating a quadratic permanent bending field as though it were
    linear.
    """
    if side not in ("left", "right"):
        raise ValueError("side must be 'left' or 'right'.")
    if span_end_m <= span_start_m:
        raise ValueError("span bounds are invalid.")
    if x_m < span_start_m - tolerance_m or x_m > span_end_m + tolerance_m:
        raise ValueError("Requested station lies outside the supplied span bounds.")

    nodes = {node.node_id: node for node in model.nodes}
    results = {item.member_id: item for item in member_results}
    matches: list[LongitudinalGrillageStationResponse] = []

    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        dx = nj.x_m - ni.x_m
        if abs(dx) <= tolerance_m:
            continue
        if abs(ni.y_m - target_y_m) > tolerance_m:
            continue
        if abs(nj.y_m - target_y_m) > tolerance_m:
            continue
        if dx < 0.0:
            raise ValueError(
                "Longitudinal grillage station recovery requires members ordered in "
                "increasing global x."
            )

        midpoint = 0.5 * (ni.x_m + nj.x_m)
        if midpoint < span_start_m - tolerance_m or midpoint > span_end_m + tolerance_m:
            continue

        result = results.get(beam.member_id)
        if result is None:
            raise ValueError(
                f"Member {beam.member_id} is missing from the supplied analysis response."
            )

        if side == "right" and abs(ni.x_m - x_m) <= tolerance_m:
            matches.append(
                LongitudinalGrillageStationResponse(
                    member_id=beam.member_id,
                    node_id=beam.node_i,
                    member_end="I",
                    side=side,
                    x_m=x_m,
                    y_m=target_y_m,
                    moment_knm=result.i_vertical_bending_moment_knm,
                    shear_kn=result.i_vertical_force_kn,
                    torsion_knm=result.i_torsion_knm,
                )
            )
        elif side == "left" and abs(nj.x_m - x_m) <= tolerance_m:
            matches.append(
                LongitudinalGrillageStationResponse(
                    member_id=beam.member_id,
                    node_id=beam.node_j,
                    member_end="J",
                    side=side,
                    x_m=x_m,
                    y_m=target_y_m,
                    moment_knm=-result.j_vertical_bending_moment_knm,
                    shear_kn=-result.j_vertical_force_kn,
                    torsion_knm=-result.j_torsion_knm,
                )
            )

    if len(matches) != 1:
        raise ValueError(
            "Expected exactly one longitudinal member-end response for "
            f"y={target_y_m:.6g} m, x={x_m:.6g} m, side={side!r}, "
            f"span=({span_start_m:.6g}, {span_end_m:.6g}) m; found {len(matches)}."
        )
    return matches[0]
