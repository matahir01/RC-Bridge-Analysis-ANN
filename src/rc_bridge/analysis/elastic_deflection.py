from __future__ import annotations

from collections.abc import Sequence

from rc_bridge.analysis.loads import PointLoad


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
