from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rc_bridge.analysis.elastic_deflection import (
    simply_supported_deflection_at_x_mm,
    simply_supported_deflection_from_moment_diagram_mm,
)
from rc_bridge.analysis.loads import PointLoad
from rc_bridge.design.eurocode_serviceability import (
    ec2_tension_stiffening_zeta,
    interpolate_service_deformation,
)


@dataclass(frozen=True)
class DeflectionResult:
    uncracked_deflection_mm: float
    fully_cracked_deflection_mm: float
    interpolated_deflection_mm: float
    allowable_deflection_mm: float | None
    utilization: float | None
    g_deflection_mm: float | None
    zeta: float
    effective_concrete_modulus_mpa: float
    status: str

    @property
    def criterion_defined(self) -> bool:
        return self.allowable_deflection_mm is not None

    @property
    def passes(self) -> bool | None:
        if self.utilization is None:
            return None
        return self.utilization <= 1.0 + 1.0e-9


def _deflection_acceptance(
    interpolated_deflection_mm: float,
    allowable_deflection_mm: float | None,
) -> tuple[float | None, float | None]:
    if allowable_deflection_mm is None:
        return None, None
    if allowable_deflection_mm <= 0.0:
        raise ValueError("Allowable deflection must be positive when specified.")
    return (
        interpolated_deflection_mm / allowable_deflection_mm,
        allowable_deflection_mm - interpolated_deflection_mm,
    )


@dataclass(frozen=True)
class SimpleSpanMomentDiagram:
    stations_m: tuple[float, ...]
    moments_knm: tuple[float, ...]
    source: str

    def __post_init__(self) -> None:
        if len(self.stations_m) != len(self.moments_knm) or len(self.stations_m) < 2:
            raise ValueError("Moment diagram stations and values are inconsistent.")
        if not self.source.strip():
            raise ValueError("Moment diagram source is required for traceability.")


def effective_concrete_modulus_mpa(ecm_mpa: float, creep_coefficient: float = 0.0) -> float:
    """Return E_c,eff = E_cm/(1 + phi) for supplied creep coefficient."""
    if ecm_mpa <= 0:
        raise ValueError("Concrete modulus must be positive.")
    if creep_coefficient < 0:
        raise ValueError("Creep coefficient cannot be negative.")
    return ecm_mpa / (1.0 + creep_coefficient)


def simply_supported_full_span_udl_deflection_mm(
    udl_kn_m: float,
    span_m: float,
    elastic_modulus_mpa: float,
    second_moment_mm4: float,
) -> float:
    """Elastic midspan deflection for a simply supported beam under full-span UDL."""
    if udl_kn_m < 0:
        raise ValueError("UDL cannot be negative.")
    if span_m <= 0 or elastic_modulus_mpa <= 0 or second_moment_mm4 <= 0:
        raise ValueError("Span, modulus and second moment must be positive.")

    # 1 kN/m = 1 N/mm, so the numerical load value is unchanged.
    w_n_mm = udl_kn_m
    span_mm = span_m * 1000.0
    return 5.0 * w_n_mm * span_mm**4 / (
        384.0 * elastic_modulus_mpa * second_moment_mm4
    )


def ec2_interpolated_udl_deflection(
    *,
    udl_kn_m: float,
    span_m: float,
    ecm_mpa: float,
    uncracked_second_moment_mm4: float,
    cracked_second_moment_mm4: float,
    cracking_moment_knm: float,
    allowable_deflection_mm: float | None,
    creep_coefficient: float = 0.0,
    beta: float = 0.5,
) -> DeflectionResult:
    """EC2 two-state deflection estimate for a simply supported UDL case.

    State-I and state-II elastic deflections are calculated using uncracked and
    fully cracked transformed section properties, then interpolated using the
    EC2 7.4.3 distribution coefficient. ``beta`` remains explicit: 1.0 is used
    for a single short-term load and 0.5 for sustained/repeated loading.
    """
    if allowable_deflection_mm is not None and allowable_deflection_mm <= 0:
        raise ValueError("Allowable deflection must be positive when specified.")

    e_eff = effective_concrete_modulus_mpa(ecm_mpa, creep_coefficient)
    service_moment_knm = udl_kn_m * span_m**2 / 8.0
    zeta = ec2_tension_stiffening_zeta(
        service_moment_knm,
        cracking_moment_knm,
        beta=beta,
    )

    uncracked = simply_supported_full_span_udl_deflection_mm(
        udl_kn_m,
        span_m,
        e_eff,
        uncracked_second_moment_mm4,
    )
    cracked = simply_supported_full_span_udl_deflection_mm(
        udl_kn_m,
        span_m,
        e_eff,
        cracked_second_moment_mm4,
    )
    interpolated = interpolate_service_deformation(uncracked, cracked, zeta)
    utilization, g_deflection = _deflection_acceptance(
        interpolated,
        allowable_deflection_mm,
    )

    return DeflectionResult(
        uncracked_deflection_mm=uncracked,
        fully_cracked_deflection_mm=cracked,
        interpolated_deflection_mm=interpolated,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=g_deflection,
        zeta=zeta,
        effective_concrete_modulus_mpa=e_eff,
        status=(
            "EC2 two-state UDL deflection estimate; numerical curvature integration "
            "is required for general loading and final bridge verification"
            + (
                ""
                if allowable_deflection_mm is not None
                else "; project/client road-bridge deflection limit not specified"
            )
        ),
    )


def _maximum_pattern_deflection_mm(
    *,
    span_m: float,
    elastic_modulus_mpa: float,
    second_moment_mm4: float,
    udl_kn_m: float,
    point_loads: Sequence[PointLoad],
    evaluation_stations: int,
    integration_segments: int,
) -> tuple[float, float]:
    if evaluation_stations < 3:
        raise ValueError("At least three deflection evaluation stations are required.")
    best_deflection = -1.0
    best_x = 0.0
    for index in range(evaluation_stations):
        x_m = span_m * index / (evaluation_stations - 1)
        value = simply_supported_deflection_at_x_mm(
            span_m=span_m,
            target_x_m=x_m,
            elastic_modulus_mpa=elastic_modulus_mpa,
            second_moment_mm4=second_moment_mm4,
            udl_kn_m=udl_kn_m,
            point_loads=point_loads,
            integration_segments=integration_segments,
        )
        if value > best_deflection:
            best_deflection = value
            best_x = x_m
    return best_deflection, best_x


def ec2_interpolated_load_pattern_deflection(
    *,
    span_m: float,
    ecm_mpa: float,
    uncracked_second_moment_mm4: float,
    cracked_second_moment_mm4: float,
    service_moment_knm: float,
    cracking_moment_knm: float,
    allowable_deflection_mm: float | None,
    udl_kn_m: float = 0.0,
    point_loads: Sequence[PointLoad] = (),
    creep_coefficient: float = 0.0,
    beta: float = 0.5,
    evaluation_stations: int = 101,
    integration_segments: int = 400,
) -> DeflectionResult:
    """EC2 two-state deflection from the actual simple-span load pattern.

    The physical moment field is recovered from the supplied full-span UDL and
    point loads. Virtual-work curvature integration is evaluated along the span,
    so asymmetric axle patterns are not converted to an equivalent UDL and the
    maximum displacement is not assumed to occur at midspan. State-I and state-II
    responses are then interpolated using the EC2 7.4.3 distribution coefficient.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment cannot be negative.")
    if allowable_deflection_mm is not None and allowable_deflection_mm <= 0.0:
        raise ValueError("Allowable deflection must be positive when specified.")
    if udl_kn_m < 0.0:
        raise ValueError("UDL cannot be negative.")
    if not point_loads and udl_kn_m == 0.0:
        raise ValueError("A non-zero deflection load pattern is required.")

    e_eff = effective_concrete_modulus_mpa(ecm_mpa, creep_coefficient)
    zeta = ec2_tension_stiffening_zeta(
        service_moment_knm,
        cracking_moment_knm,
        beta=beta,
    )
    uncracked, uncracked_x = _maximum_pattern_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=e_eff,
        second_moment_mm4=uncracked_second_moment_mm4,
        udl_kn_m=udl_kn_m,
        point_loads=point_loads,
        evaluation_stations=evaluation_stations,
        integration_segments=integration_segments,
    )
    cracked, cracked_x = _maximum_pattern_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=e_eff,
        second_moment_mm4=cracked_second_moment_mm4,
        udl_kn_m=udl_kn_m,
        point_loads=point_loads,
        evaluation_stations=evaluation_stations,
        integration_segments=integration_segments,
    )
    interpolated = interpolate_service_deformation(uncracked, cracked, zeta)
    utilization, g_deflection = _deflection_acceptance(
        interpolated,
        allowable_deflection_mm,
    )
    return DeflectionResult(
        uncracked_deflection_mm=uncracked,
        fully_cracked_deflection_mm=cracked,
        interpolated_deflection_mm=interpolated,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=g_deflection,
        zeta=zeta,
        effective_concrete_modulus_mpa=e_eff,
        status=(
            "EC2 two-state load-pattern deflection by virtual-work curvature integration; "
            f"maximum searched along span (state-I x={uncracked_x:.3f} m, "
            f"state-II x={cracked_x:.3f} m)"
            + (
                ""
                if allowable_deflection_mm is not None
                else "; project/client road-bridge deflection limit not specified"
            )
        ),
    )


def ec2_interpolated_moment_diagram_deflection(
    *,
    diagram: SimpleSpanMomentDiagram,
    ecm_mpa: float,
    uncracked_second_moment_mm4: float,
    cracked_second_moment_mm4: float,
    service_moment_knm: float,
    cracking_moment_knm: float,
    allowable_deflection_mm: float | None,
    creep_coefficient: float = 0.0,
    beta: float = 0.5,
) -> DeflectionResult:
    """EC2 two-state deflection from a traceable signed bending-moment field."""
    if service_moment_knm < 0.0:
        raise ValueError("Service moment cannot be negative.")
    if allowable_deflection_mm is not None and allowable_deflection_mm <= 0.0:
        raise ValueError("Allowable deflection must be positive when specified.")
    e_eff = effective_concrete_modulus_mpa(ecm_mpa, creep_coefficient)
    zeta = ec2_tension_stiffening_zeta(
        service_moment_knm,
        cracking_moment_knm,
        beta=beta,
    )
    uncracked = simply_supported_deflection_from_moment_diagram_mm(
        stations_m=diagram.stations_m,
        moments_knm=diagram.moments_knm,
        elastic_modulus_mpa=e_eff,
        second_moment_mm4=uncracked_second_moment_mm4,
    )
    cracked = simply_supported_deflection_from_moment_diagram_mm(
        stations_m=diagram.stations_m,
        moments_knm=diagram.moments_knm,
        elastic_modulus_mpa=e_eff,
        second_moment_mm4=cracked_second_moment_mm4,
    )
    interpolated = interpolate_service_deformation(
        uncracked.maximum_absolute_deflection_mm,
        cracked.maximum_absolute_deflection_mm,
        zeta,
    )
    utilization, g_deflection = _deflection_acceptance(
        interpolated,
        allowable_deflection_mm,
    )
    return DeflectionResult(
        uncracked_deflection_mm=uncracked.maximum_absolute_deflection_mm,
        fully_cracked_deflection_mm=cracked.maximum_absolute_deflection_mm,
        interpolated_deflection_mm=interpolated,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=g_deflection,
        zeta=zeta,
        effective_concrete_modulus_mpa=e_eff,
        status=(
            "EC2 two-state deflection from traceable signed M/EI curvature integration; "
            f"source={diagram.source}; state-I maximum x={uncracked.maximum_position_m:.3f} m; "
            f"state-II maximum x={cracked.maximum_position_m:.3f} m"
            + (
                ""
                if allowable_deflection_mm is not None
                else "; project/client road-bridge deflection limit not specified"
            )
        ),
    )
