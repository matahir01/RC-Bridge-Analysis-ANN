from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from rc_bridge.analysis.loads import PointLoad


@dataclass(frozen=True)
class MomentDiagramDeflectionResult:
    maximum_absolute_deflection_mm: float
    maximum_position_m: float
    station_deflections_mm: tuple[float, ...]


def _simply_supported_bending_moment_nmm(
    *,
    span_mm: float,
    x_mm: float,
    udl_n_mm: float,
    point_loads_n_mm: Sequence[tuple[float, float]],
) -> float:
    total_load_n = udl_n_mm * span_mm + sum(load_n for load_n, _ in point_loads_n_mm)
    moment_about_left_nmm = (
        udl_n_mm * span_mm * span_mm / 2.0
        + sum(load_n * position_mm for load_n, position_mm in point_loads_n_mm)
    )
    reaction_right_n = moment_about_left_nmm / span_mm
    reaction_left_n = total_load_n - reaction_right_n

    moment = reaction_left_n * x_mm - udl_n_mm * x_mm**2 / 2.0
    for load_n, position_mm in point_loads_n_mm:
        if x_mm >= position_mm:
            moment -= load_n * (x_mm - position_mm)
    return moment


def simply_supported_deflection_at_x_mm(
    *,
    span_m: float,
    target_x_m: float,
    elastic_modulus_mpa: float,
    second_moment_mm4: float,
    udl_kn_m: float = 0.0,
    point_loads: Sequence[PointLoad] = (),
    integration_segments: int = 2000,
) -> float:
    """Return elastic downward deflection using virtual-work integration.

    The beam is prismatic and simply supported. A full-span UDL and arbitrary
    point loads may act simultaneously. The numerical integration is code
    neutral and can therefore support Eurocode and BS 5400 serviceability paths.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")
    if not 0.0 <= target_x_m <= span_m:
        raise ValueError("target_x_m must lie on the span.")
    if elastic_modulus_mpa <= 0.0 or second_moment_mm4 <= 0.0:
        raise ValueError("Elastic modulus and second moment must be positive.")
    if udl_kn_m < 0.0:
        raise ValueError("UDL cannot be negative.")
    if integration_segments < 2 or integration_segments % 2 != 0:
        raise ValueError("integration_segments must be an even integer of at least 2.")
    if any(load.position_m > span_m for load in point_loads):
        raise ValueError("Point load lies outside the beam span.")

    span_mm = span_m * 1000.0
    target_mm = target_x_m * 1000.0
    physical_loads = tuple(
        (load.magnitude_kn * 1000.0, load.position_m * 1000.0)
        for load in point_loads
    )

    # Virtual unit load at the requested displacement coordinate.
    unit_loads = ((1.0, target_mm),)
    dx = span_mm / integration_segments

    def integrand(x_mm: float) -> float:
        physical_moment = _simply_supported_bending_moment_nmm(
            span_mm=span_mm,
            x_mm=x_mm,
            udl_n_mm=udl_kn_m,
            point_loads_n_mm=physical_loads,
        )
        virtual_moment = _simply_supported_bending_moment_nmm(
            span_mm=span_mm,
            x_mm=x_mm,
            udl_n_mm=0.0,
            point_loads_n_mm=unit_loads,
        )
        return physical_moment * virtual_moment

    total = integrand(0.0) + integrand(span_mm)
    for index in range(1, integration_segments):
        coefficient = 4.0 if index % 2 else 2.0
        total += coefficient * integrand(index * dx)

    integral = dx * total / 3.0
    return integral / (elastic_modulus_mpa * second_moment_mm4)


def simply_supported_midspan_deflection_mm(
    *,
    span_m: float,
    elastic_modulus_mpa: float,
    second_moment_mm4: float,
    udl_kn_m: float = 0.0,
    point_loads: Sequence[PointLoad] = (),
    integration_segments: int = 2000,
) -> float:
    """Convenience wrapper for elastic midspan deflection."""
    return simply_supported_deflection_at_x_mm(
        span_m=span_m,
        target_x_m=span_m / 2.0,
        elastic_modulus_mpa=elastic_modulus_mpa,
        second_moment_mm4=second_moment_mm4,
        udl_kn_m=udl_kn_m,
        point_loads=point_loads,
        integration_segments=integration_segments,
    )


def simply_supported_deflection_from_curvature_diagram_mm(
    *,
    stations_m: Sequence[float],
    curvatures_per_mm: Sequence[float],
) -> MomentDiagramDeflectionResult:
    """Integrate a signed piecewise-linear curvature diagram for a simple span.

    Curvature is supplied in 1/mm. The integration constant is solved from zero
    displacement at both simple supports. This generic form supports spatially
    varying cracked/uncracked stiffness instead of forcing one effective EI over
    the complete span.
    """
    if len(stations_m) != len(curvatures_per_mm) or len(stations_m) < 2:
        raise ValueError(
            "Curvature stations and values must have equal length of at least two."
        )
    stations_mm = tuple(float(value) * 1000.0 for value in stations_m)
    if abs(stations_mm[0]) > 1.0e-9:
        raise ValueError("Moment diagram must begin at the left support x=0.")
    if any(
        stations_mm[index + 1] < stations_mm[index]
        for index in range(len(stations_mm) - 1)
    ):
        raise ValueError("Moment stations must be non-decreasing.")

    curvatures = tuple(float(value) for value in curvatures_per_mm)
    free_slopes = [0.0]
    free_deflections = [0.0]
    for index in range(len(stations_mm) - 1):
        dx = stations_mm[index + 1] - stations_mm[index]
        k0 = curvatures[index]
        k1 = curvatures[index + 1]
        slope = free_slopes[-1]
        free_deflections.append(
            free_deflections[-1]
            + slope * dx
            + dx**2 * (k0 / 2.0 + (k1 - k0) / 6.0)
        )
        free_slopes.append(slope + dx * (k0 + k1) / 2.0)

    span_mm = stations_mm[-1]
    if span_mm <= 0.0:
        raise ValueError("Moment diagram span must be positive.")
    initial_slope = -free_deflections[-1] / span_mm
    signed = tuple(
        value + initial_slope * x
        for value, x in zip(free_deflections, stations_mm, strict=True)
    )

    # The maximum deflection need not occur at a supplied moment station. Inside
    # each piecewise-linear curvature segment, slope is a quadratic function of
    # local coordinate. Solve slope=0 exactly and evaluate every stationary
    # point, while still retaining station displacements for audit/plotting.
    best_absolute = -1.0
    best_position_mm = 0.0

    def consider(position_mm: float, deflection_mm: float) -> None:
        nonlocal best_absolute, best_position_mm
        magnitude = abs(deflection_mm)
        if magnitude > best_absolute:
            best_absolute = magnitude
            best_position_mm = position_mm

    for position_mm, deflection_mm in zip(stations_mm, signed, strict=True):
        consider(position_mm, deflection_mm)

    curvature_gradient_tolerance = 1.0e-18
    curvature_tolerance = 1.0e-18
    endpoint_tolerance_mm = 1.0e-9

    for index in range(len(stations_mm) - 1):
        x0 = stations_mm[index]
        dx = stations_mm[index + 1] - x0
        if dx <= 0.0:
            continue

        k0 = curvatures[index]
        k1 = curvatures[index + 1]
        gradient = (k1 - k0) / dx
        signed_slope_start = free_slopes[index] + initial_slope
        signed_deflection_start = signed[index]

        roots: list[float] = []
        if abs(gradient) <= curvature_gradient_tolerance:
            if abs(k0) > curvature_tolerance:
                roots.append(-signed_slope_start / k0)
        else:
            discriminant = k0**2 - 2.0 * gradient * signed_slope_start
            if discriminant >= 0.0:
                root_term = sqrt(max(discriminant, 0.0))
                roots.extend(
                    (
                        (-k0 - root_term) / gradient,
                        (-k0 + root_term) / gradient,
                    )
                )

        for local_x in roots:
            if not (
                endpoint_tolerance_mm
                < local_x
                < dx - endpoint_tolerance_mm
            ):
                continue
            deflection = (
                signed_deflection_start
                + signed_slope_start * local_x
                + k0 * local_x**2 / 2.0
                + gradient * local_x**3 / 6.0
            )
            consider(x0 + local_x, deflection)

    return MomentDiagramDeflectionResult(
        maximum_absolute_deflection_mm=best_absolute,
        maximum_position_m=best_position_mm / 1000.0,
        station_deflections_mm=signed,
    )


def simply_supported_deflection_from_moment_diagram_mm(
    *,
    stations_m: Sequence[float],
    moments_knm: Sequence[float],
    elastic_modulus_mpa: float,
    second_moment_mm4: float,
) -> MomentDiagramDeflectionResult:
    """Integrate a signed piecewise-linear M/EI diagram for a simple span."""
    if len(stations_m) != len(moments_knm) or len(stations_m) < 2:
        raise ValueError("Moment stations and values must have equal length of at least two.")
    if elastic_modulus_mpa <= 0.0 or second_moment_mm4 <= 0.0:
        raise ValueError("Elastic modulus and second moment must be positive.")
    curvatures = tuple(
        float(moment) * 1_000_000.0 / (elastic_modulus_mpa * second_moment_mm4)
        for moment in moments_knm
    )
    return simply_supported_deflection_from_curvature_diagram_mm(
        stations_m=stations_m,
        curvatures_per_mm=curvatures,
    )
