from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrackedTSectionSLS:
    neutral_axis_from_top_mm: float
    second_moment_mm4: float
    steel_stress_mpa: float


@dataclass(frozen=True)
class CrackWidthResult:
    crack_width_mm: float
    crack_limit_mm: float
    utilization: float
    g_crack_mm: float
    steel_stress_mpa: float
    effective_tension_depth_mm: float
    effective_tension_area_mm2: float
    effective_reinforcement_ratio: float
    max_crack_spacing_mm: float
    strain_difference: float
    close_spacing: bool
    status: str


def cracked_t_section_sls(
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    modular_ratio: float,
    service_moment_knm: float,
) -> CrackedTSectionSLS:
    """Calculate transformed cracked T-section properties for positive bending.

    Tensile concrete is neglected. The neutral axis is solved from transformed
    first-moment equilibrium and may lie in the flange or the web.
    """
    values = (
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        total_depth_m,
        steel_area_mm2,
        steel_depth_m,
        modular_ratio,
    )
    if any(value <= 0 for value in values):
        raise ValueError("Section, reinforcement and modular-ratio inputs must be positive.")
    if service_moment_knm < 0:
        raise ValueError("Service moment cannot be negative.")
    if flange_thickness_m >= total_depth_m:
        raise ValueError("Flange thickness must be less than total depth.")
    if steel_depth_m >= total_depth_m:
        raise ValueError("Steel depth must lie within the section.")
    if web_width_m > effective_flange_width_m:
        raise ValueError("Web width cannot exceed effective flange width.")

    beff = effective_flange_width_m * 1000.0
    hf = flange_thickness_m * 1000.0
    bw = web_width_m * 1000.0
    h = total_depth_m * 1000.0
    d = steel_depth_m * 1000.0
    nas = modular_ratio * steel_area_mm2

    def equilibrium(x: float) -> float:
        steel_first_moment = nas * (d - x)
        if x <= hf:
            concrete_first_moment = beff * x**2 / 2.0
        else:
            concrete_first_moment = (
                beff * hf * (x - hf / 2.0)
                + bw * (x - hf) ** 2 / 2.0
            )
        return concrete_first_moment - steel_first_moment

    lower = 1e-6
    upper = min(d - 1e-6, h - 1e-6)
    if equilibrium(lower) >= 0 or equilibrium(upper) <= 0:
        raise ValueError("Unable to bracket cracked neutral axis for this section.")

    for _ in range(100):
        mid = 0.5 * (lower + upper)
        value = equilibrium(mid)
        if abs(value) < 1e-6:
            lower = upper = mid
            break
        if value < 0:
            lower = mid
        else:
            upper = mid
    x = 0.5 * (lower + upper)

    if x <= hf:
        concrete_inertia = beff * x**3 / 3.0
    else:
        web_inertia = bw * x**3 / 3.0
        flange_overhang_width = beff - bw
        flange_overhang_inertia = flange_overhang_width * (
            hf**3 / 12.0 + hf * (x - hf / 2.0) ** 2
        )
        concrete_inertia = web_inertia + flange_overhang_inertia

    inertia = concrete_inertia + nas * (d - x) ** 2
    if inertia <= 0:
        raise ValueError("Calculated cracked second moment is non-positive.")

    moment_nmm = service_moment_knm * 1e6
    steel_stress = modular_ratio * moment_nmm * (d - x) / inertia

    return CrackedTSectionSLS(
        neutral_axis_from_top_mm=x,
        second_moment_mm4=inertia,
        steel_stress_mpa=steel_stress,
    )


def effective_tension_depth_mm(
    total_depth_m: float,
    steel_depth_m: float,
    neutral_axis_from_top_mm: float,
) -> float:
    """EC2 effective tension-zone depth h_c,eff for a beam in bending."""
    h = total_depth_m * 1000.0
    d = steel_depth_m * 1000.0
    x = neutral_axis_from_top_mm
    if not 0 < d < h:
        raise ValueError("Steel depth must lie inside the section.")
    if not 0 < x < h:
        raise ValueError("Neutral axis must lie inside the section.")
    return min(2.5 * (h - d), (h - x) / 3.0, h / 2.0)


def t_section_effective_tension_area_mm2(
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    hceff_mm: float,
) -> float:
    """Actual T-section concrete area contained in the bottom h_c,eff zone."""
    if hceff_mm <= 0:
        raise ValueError("Effective tension depth must be positive.")
    beff = effective_flange_width_m * 1000.0
    hf = flange_thickness_m * 1000.0
    bw = web_width_m * 1000.0
    h = total_depth_m * 1000.0
    if hceff_mm > h:
        raise ValueError("Effective tension depth cannot exceed overall depth.")

    web_depth = h - hf
    if hceff_mm <= web_depth:
        return bw * hceff_mm
    return bw * web_depth + beff * (hceff_mm - web_depth)


def crack_width_ec2_t_section(
    *,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    bar_diameter_mm: float,
    bar_spacing_mm: float,
    cover_mm: float,
    service_moment_knm: float,
    cracking_moment_knm: float,
    es_mpa: float,
    ecm_mpa: float,
    fct_eff_mpa: float,
    crack_limit_mm: float,
    kt: float = 0.4,
    k1: float = 0.8,
    k2: float = 0.5,
    k3: float = 3.4,
    k4: float = 0.425,
) -> CrackWidthResult:
    """Direct first-generation EC2 7.3.4 crack-width calculation for a T girder.

    Recommended k3/k4 are defaults only; National Annex/project values remain
    explicit inputs. No prestressing contribution is included in this module.
    """
    positive = (
        steel_area_mm2,
        bar_diameter_mm,
        bar_spacing_mm,
        cover_mm,
        es_mpa,
        ecm_mpa,
        fct_eff_mpa,
        crack_limit_mm,
    )
    if any(value <= 0 for value in positive):
        raise ValueError("Reinforcement, material, cover and crack-limit inputs must be positive.")
    if service_moment_knm < 0 or cracking_moment_knm <= 0:
        raise ValueError("Service moment must be non-negative and cracking moment positive.")
    if not 0 < kt <= 1:
        raise ValueError("kt must lie between zero and one.")

    modular_ratio = es_mpa / ecm_mpa
    cracked = cracked_t_section_sls(
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        total_depth_m,
        steel_area_mm2,
        steel_depth_m,
        modular_ratio,
        service_moment_knm,
    )

    hceff = effective_tension_depth_mm(
        total_depth_m,
        steel_depth_m,
        cracked.neutral_axis_from_top_mm,
    )
    aceff = t_section_effective_tension_area_mm2(
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        total_depth_m,
        hceff,
    )
    rho = steel_area_mm2 / aceff
    if rho <= 0:
        raise ValueError("Effective reinforcement ratio must be positive.")

    sigma_s = cracked.steel_stress_mpa
    if service_moment_knm <= cracking_moment_knm:
        return CrackWidthResult(
            crack_width_mm=0.0,
            crack_limit_mm=crack_limit_mm,
            utilization=0.0,
            g_crack_mm=crack_limit_mm,
            steel_stress_mpa=sigma_s,
            effective_tension_depth_mm=hceff,
            effective_tension_area_mm2=aceff,
            effective_reinforcement_ratio=rho,
            max_crack_spacing_mm=0.0,
            strain_difference=0.0,
            close_spacing=True,
            status="uncracked under supplied service moment",
        )

    strain_calc = (
        sigma_s - kt * fct_eff_mpa / rho * (1.0 + modular_ratio * rho)
    ) / es_mpa
    strain_min = 0.6 * sigma_s / es_mpa
    strain_difference = max(strain_calc, strain_min, 0.0)

    close_spacing = bar_spacing_mm <= 5.0 * (cover_mm + bar_diameter_mm / 2.0)
    if close_spacing:
        srmax = k3 * cover_mm + k1 * k2 * k4 * bar_diameter_mm / rho
    else:
        h_mm = total_depth_m * 1000.0
        srmax = 1.3 * (h_mm - cracked.neutral_axis_from_top_mm)

    wk = srmax * strain_difference
    utilization = wk / crack_limit_mm
    return CrackWidthResult(
        crack_width_mm=wk,
        crack_limit_mm=crack_limit_mm,
        utilization=utilization,
        g_crack_mm=crack_limit_mm - wk,
        steel_stress_mpa=sigma_s,
        effective_tension_depth_mm=hceff,
        effective_tension_area_mm2=aceff,
        effective_reinforcement_ratio=rho,
        max_crack_spacing_mm=srmax,
        strain_difference=strain_difference,
        close_spacing=close_spacing,
        status="first-generation EC2 direct crack-width calculation",
    )
