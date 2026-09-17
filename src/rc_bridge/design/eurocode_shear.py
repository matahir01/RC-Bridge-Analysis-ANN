from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class ShearConcreteResult:
    vrdc_kn: float
    vmin_kn: float
    rho_l: float
    k: float
    status: str


@dataclass(frozen=True)
class ShearReinforcementResult:
    asw_per_s_mm2_per_mm: float
    asw_per_s_mm2_per_m: float
    vrdmax_kn: float
    cot_theta: float
    status: str


@dataclass(frozen=True)
class ProvidedShearResistanceResult:
    provided_asw_per_s_mm2_per_m: float
    vrds_kn: float
    vrdmax_kn: float
    governing_resistance_kn: float
    cot_theta: float
    status: str


def concrete_shear_resistance(
    web_width_m: float,
    effective_depth_m: float,
    longitudinal_steel_area_mm2: float,
    fck_mpa: float,
    gamma_c: float = 1.50,
    c_rdc_factor: float = 0.18,
    sigma_cp_mpa: float = 0.0,
    k1: float = 0.15,
) -> ShearConcreteResult:
    """EN 1992-2 / EC2 shear resistance V_Rd,c for members without design shear steel.

    The recommended expression is implemented with exposed National Annex
    parameters. Units: metres, mm², MPa -> kN.
    """
    if min(web_width_m, effective_depth_m, longitudinal_steel_area_mm2, fck_mpa) <= 0:
        raise ValueError("Geometry, reinforcement and strength must be positive.")
    if gamma_c <= 0 or c_rdc_factor <= 0:
        raise ValueError("Material and resistance factors must be positive.")

    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    k = min(1.0 + sqrt(200.0 / d_mm), 2.0)
    rho_l = min(longitudinal_steel_area_mm2 / (bw_mm * d_mm), 0.02)
    c_rdc = c_rdc_factor / gamma_c
    vmin_mpa = 0.035 * k**1.5 * sqrt(fck_mpa)

    stress_main_mpa = c_rdc * k * (100.0 * rho_l * fck_mpa) ** (1.0 / 3.0) + k1 * sigma_cp_mpa
    stress_min_mpa = vmin_mpa + k1 * sigma_cp_mpa
    stress_mpa = max(stress_main_mpa, stress_min_mpa)

    vrdc_kn = stress_mpa * bw_mm * d_mm / 1000.0
    vmin_kn = stress_min_mpa * bw_mm * d_mm / 1000.0
    return ShearConcreteResult(
        vrdc_kn=vrdc_kn,
        vmin_kn=vmin_kn,
        rho_l=rho_l,
        k=k,
        status="EN 1992 shear model; verify National Annex parameters before design use",
    )


def _reinforced_shear_resistances(
    *,
    asw_per_s_mm2_per_mm: float,
    web_width_m: float,
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float,
    gamma_s: float,
    alpha_cc: float,
    cot_theta: float,
    z_factor: float,
    alpha_cw: float,
) -> tuple[float, float]:
    if asw_per_s_mm2_per_mm < 0.0:
        raise ValueError("A_sw/s cannot be negative.")
    if min(web_width_m, effective_depth_m, fck_mpa, fyk_mpa) <= 0.0:
        raise ValueError("Geometry and strengths must be positive.")
    if not 1.0 <= cot_theta <= 2.5:
        raise ValueError("cot(theta) must lie between 1.0 and 2.5 for this implementation.")
    if min(gamma_c, gamma_s, alpha_cc, z_factor, alpha_cw) <= 0.0:
        raise ValueError("Material, lever-arm and strut factors must be positive.")

    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    z_mm = z_factor * d_mm
    fyd_mpa = fyk_mpa / gamma_s
    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    tan_theta = 1.0 / cot_theta
    nu1 = 0.6 * (1.0 - fck_mpa / 250.0)

    vrds_kn = asw_per_s_mm2_per_mm * z_mm * fyd_mpa * cot_theta / 1000.0
    vrdmax_kn = alpha_cw * bw_mm * z_mm * nu1 * fcd_mpa / (cot_theta + tan_theta) / 1000.0
    return vrds_kn, vrdmax_kn


def required_vertical_shear_reinforcement(
    ved_kn: float,
    web_width_m: float,
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    cot_theta: float = 2.0,
    z_factor: float = 0.9,
    alpha_cw: float = 1.0,
) -> ShearReinforcementResult:
    """Required vertical shear reinforcement from EC2 variable-angle truss model.

    Implements V_Rd,s = (A_sw/s) z f_ywd cot(theta), and checks V_Rd,max.
    The chosen cot(theta) is explicit and must satisfy project/National Annex rules.
    """
    if ved_kn < 0:
        raise ValueError("Design shear cannot be negative.")
    if min(web_width_m, effective_depth_m, fck_mpa, fyk_mpa) <= 0:
        raise ValueError("Geometry and strengths must be positive.")
    if not 1.0 <= cot_theta <= 2.5:
        raise ValueError("cot(theta) must lie between 1.0 and 2.5 for this implementation.")

    d_mm = effective_depth_m * 1000.0
    z_mm = z_factor * d_mm
    fyd_mpa = fyk_mpa / gamma_s
    asw_per_s = 0.0 if ved_kn == 0 else ved_kn * 1000.0 / (z_mm * fyd_mpa * cot_theta)
    _, vrdmax_kn = _reinforced_shear_resistances(
        asw_per_s_mm2_per_mm=asw_per_s,
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        cot_theta=cot_theta,
        z_factor=z_factor,
        alpha_cw=alpha_cw,
    )
    return ShearReinforcementResult(
        asw_per_s_mm2_per_mm=asw_per_s,
        asw_per_s_mm2_per_m=asw_per_s * 1000.0,
        vrdmax_kn=vrdmax_kn,
        cot_theta=cot_theta,
        status="EC2 variable-angle truss model; minimum shear steel and detailing checks still required",
    )


def provided_vertical_shear_resistance(
    *,
    provided_asw_per_s_mm2_per_m: float,
    web_width_m: float,
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    cot_theta: float = 2.0,
    z_factor: float = 0.9,
    alpha_cw: float = 1.0,
) -> ProvidedShearResistanceResult:
    """Return EC2 shear resistance for explicitly provided vertical links.

    For vertical reinforcement, V_Rd is the smaller of V_Rd,s and V_Rd,max.
    ``provided_asw_per_s_mm2_per_m`` is the actual supplied A_sw/s, not the
    required value returned by the design-demand helper.
    """
    if provided_asw_per_s_mm2_per_m < 0.0:
        raise ValueError("Provided A_sw/s cannot be negative.")

    asw_per_s_mm2_per_mm = provided_asw_per_s_mm2_per_m / 1000.0
    vrds_kn, vrdmax_kn = _reinforced_shear_resistances(
        asw_per_s_mm2_per_mm=asw_per_s_mm2_per_mm,
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        cot_theta=cot_theta,
        z_factor=z_factor,
        alpha_cw=alpha_cw,
    )
    return ProvidedShearResistanceResult(
        provided_asw_per_s_mm2_per_m=provided_asw_per_s_mm2_per_m,
        vrds_kn=vrds_kn,
        vrdmax_kn=vrdmax_kn,
        governing_resistance_kn=min(vrds_kn, vrdmax_kn),
        cot_theta=cot_theta,
        status=(
            "EC2 vertical-link shear resistance; governing V_Rd is min(V_Rd,s, V_Rd,max)"
        ),
    )
