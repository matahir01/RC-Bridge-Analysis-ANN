from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import (
    BeamMemberResult,
    BeamNodeResult,
    BeamSpan,
)


@dataclass(frozen=True)
class BeamSectionDisplacement:
    span_index: int
    x_m: float
    vertical_displacement_m: float
    rotation_rad: float


@dataclass(frozen=True)
class BeamSpanDeflectionEnvelope:
    span_index: int
    maximum_upward_displacement_m: float
    maximum_upward_position_m: float
    minimum_downward_displacement_m: float
    minimum_downward_position_m: float
    max_abs_displacement_m: float
    max_abs_position_m: float


def member_section_displacement(
    span: BeamSpan,
    member: BeamMemberResult,
    left_node: BeamNodeResult,
    x_m: float,
) -> BeamSectionDisplacement:
    """Recover section displacement by integrating the solved moment field.

    ``continuous_beam`` stores vertical displacement positive upward and bending
    moment positive sagging. With that sign convention the elastic-curve relation
    is ``v'' = M / EI``. The member moment expression is integrated analytically,
    including full-span UDL and all point loads to the left of the requested
    section. This preserves the exact load particular solution instead of using
    only cubic interpolation between nodal degrees of freedom.
    """
    if member.span_index != left_node.node_index:
        raise ValueError("Left node index must match the member span index.")
    if not 0.0 <= x_m <= span.length_m:
        raise ValueError("Section location must lie within the span.")

    x = x_m
    moment_integral_kn_m2 = (
        member.left_moment_knm * x
        + member.left_shear_kn * x**2 / 2.0
        - span.udl_kn_m * x**3 / 6.0
    )
    moment_double_integral_kn_m3 = (
        member.left_moment_knm * x**2 / 2.0
        + member.left_shear_kn * x**3 / 6.0
        - span.udl_kn_m * x**4 / 24.0
    )

    for load in span.point_loads:
        if load.position_m <= x:
            distance = x - load.position_m
            moment_integral_kn_m2 -= load.magnitude_kn * distance**2 / 2.0
            moment_double_integral_kn_m3 -= load.magnitude_kn * distance**3 / 6.0

    rotation = left_node.rotation_rad + moment_integral_kn_m2 / span.ei_kn_m2
    displacement = (
        left_node.vertical_displacement_m
        + left_node.rotation_rad * x
        + moment_double_integral_kn_m3 / span.ei_kn_m2
    )
    return BeamSectionDisplacement(
        span_index=member.span_index,
        x_m=x,
        vertical_displacement_m=displacement,
        rotation_rad=rotation,
    )


def member_span_deflection_envelope(
    span: BeamSpan,
    member: BeamMemberResult,
    left_node: BeamNodeResult,
    *,
    stations: int = 401,
) -> BeamSpanDeflectionEnvelope:
    """Scan one span for upward, downward and absolute displacement extrema."""
    if stations < 2:
        raise ValueError("At least two deflection-envelope stations are required.")

    locations = {span.length_m * index / (stations - 1) for index in range(stations)}
    locations.update(load.position_m for load in span.point_loads)
    responses = [
        member_section_displacement(span, member, left_node, x_m)
        for x_m in sorted(locations)
    ]
    upward = max(responses, key=lambda item: item.vertical_displacement_m)
    downward = min(responses, key=lambda item: item.vertical_displacement_m)
    absolute = max(responses, key=lambda item: abs(item.vertical_displacement_m))
    return BeamSpanDeflectionEnvelope(
        span_index=member.span_index,
        maximum_upward_displacement_m=upward.vertical_displacement_m,
        maximum_upward_position_m=upward.x_m,
        minimum_downward_displacement_m=downward.vertical_displacement_m,
        minimum_downward_position_m=downward.x_m,
        max_abs_displacement_m=abs(absolute.vertical_displacement_m),
        max_abs_position_m=absolute.x_m,
    )
