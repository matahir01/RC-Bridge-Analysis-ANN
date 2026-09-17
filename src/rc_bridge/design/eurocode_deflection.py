from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_serviceability import (
    ec2_tension_stiffening_zeta,
    interpolate_service_deformation,
)


@dataclass(frozen=True)
class DeflectionResult:
    uncracked_deflection_mm: float
    fully_cracked_deflection_mm: float
    interpolated_deflection_mm: float
    allowable_deflection_mm: float
    utilization: float
    g_deflection_mm: float
    zeta: float
    effective_concrete_modulus_mpa: float
    status: str


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
    allowable_deflection_mm: float,
    creep_coefficient: float = 0.0,
    beta: float = 0.5,
) -> DeflectionResult:
    """EC2 two-state deflection estimate for a simply supported UDL case.

    State-I and state-II elastic deflections are calculated using uncracked and
    fully cracked transformed section properties, then interpolated using the
    EC2 7.4.3 distribution coefficient. ``beta`` remains explicit: 1.0 is used
    for a single short-term load and 0.5 for sustained/repeated loading.
    """
    if allowable_deflection_mm <= 0:
        raise ValueError("Allowable deflection must be positive.")

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
    utilization = interpolated / allowable_deflection_mm

    return DeflectionResult(
        uncracked_deflection_mm=uncracked,
        fully_cracked_deflection_mm=cracked,
        interpolated_deflection_mm=interpolated,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=allowable_deflection_mm - interpolated,
        zeta=zeta,
        effective_concrete_modulus_mpa=e_eff,
        status=(
            "EC2 two-state UDL deflection estimate; numerical curvature integration "
            "is required for general loading and final bridge verification"
        ),
    )
