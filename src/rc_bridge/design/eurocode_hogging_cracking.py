from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_cracking import CrackWidthResult


@dataclass(frozen=True)
class CrackedHoggingSectionSLS:
    neutral_axis_from_bottom_mm: float
    second_moment_mm4: float
    top_steel_stress_mpa: float
    compression_zone: str


def _segment_first_moment_about_na(
    width_mm: float,
    y0_mm: float,
    y1_mm: float,
    neutral_axis_mm: float,
) -> float:
    if y1_mm <= y0_mm:
        return 0.0
    return width_mm * (
        neutral_axis_mm * (y1_mm - y0_mm) - (y1_mm**2 - y0_mm**2) / 2.0
    )


def _segment_inertia_about_na(
    width_mm: float,
    y0_mm: float,
    y1_mm: float,
    neutral_axis_mm: float,
) -> float:
    if y1_mm <= y0_mm:
        return 0.0
    return (
        width_mm
        * ((neutral_axis_mm - y0_mm) ** 3 - (neutral_axis_mm - y1_mm) ** 3)
        / 3.0
    )


def cracked_hogging_section_sls(
    *,
    bottom_flange_width_m: float,
    bottom_flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    top_tension_flange_width_m: float,
    top_tension_flange_thickness_m: float,
    steel_area_mm2: float,
    steel_depth_from_bottom_m: float,
    modular_ratio: float,
    service_moment_knm: float,
) -> CrackedHoggingSectionSLS:
    """Cracked transformed section for negative bending in a continuous RC girder.

    Coordinates are measured upward from the bottom compression face. Tensile
    concrete is neglected. The bottom flange may be set to zero thickness for a
    T-stem/web-only compression zone; an I-girder can supply its actual bottom
    flange. The top tension flange represents the physical deck/top-flange region
    around the support reinforcement and is not counted in compression unless the
    solved neutral axis actually reaches it.
    """
    positive = (
        bottom_flange_width_m,
        web_width_m,
        total_depth_m,
        top_tension_flange_width_m,
        top_tension_flange_thickness_m,
        steel_area_mm2,
        steel_depth_from_bottom_m,
        modular_ratio,
    )
    if any(value <= 0.0 for value in positive):
        raise ValueError("Section, reinforcement and modular-ratio inputs must be positive.")
    if bottom_flange_thickness_m < 0.0:
        raise ValueError("Bottom-flange thickness cannot be negative.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment magnitude cannot be negative.")
    if bottom_flange_width_m < web_width_m:
        raise ValueError("Bottom-flange width cannot be less than web width.")
    if top_tension_flange_width_m < web_width_m:
        raise ValueError("Top tension-flange width cannot be less than web width.")
    if bottom_flange_thickness_m + top_tension_flange_thickness_m >= total_depth_m:
        raise ValueError("Bottom and top flange thicknesses leave no web depth.")
    if not 0.0 < steel_depth_from_bottom_m < total_depth_m:
        raise ValueError("Top reinforcement depth must lie within the section.")

    b_bottom = bottom_flange_width_m * 1000.0
    t_bottom = bottom_flange_thickness_m * 1000.0
    b_web = web_width_m * 1000.0
    h = total_depth_m * 1000.0
    b_top = top_tension_flange_width_m * 1000.0
    t_top = top_tension_flange_thickness_m * 1000.0
    d = steel_depth_from_bottom_m * 1000.0
    transformed_steel_area = modular_ratio * steel_area_mm2
    top_flange_start = h - t_top

    def concrete_first_moment(x: float) -> float:
        total = 0.0
        bottom_end = min(x, t_bottom)
        total += _segment_first_moment_about_na(b_bottom, 0.0, bottom_end, x)

        web_start = t_bottom
        web_end = min(x, top_flange_start)
        total += _segment_first_moment_about_na(b_web, web_start, web_end, x)

        if x > top_flange_start:
            total += _segment_first_moment_about_na(
                b_top,
                top_flange_start,
                x,
                x,
            )
        return total

    def equilibrium(x: float) -> float:
        return concrete_first_moment(x) - transformed_steel_area * (d - x)

    lower = 1e-6
    upper = min(d - 1e-6, h - 1e-6)
    if equilibrium(lower) >= 0.0 or equilibrium(upper) <= 0.0:
        raise ValueError("Unable to bracket cracked hogging neutral axis for this section.")

    for _ in range(100):
        mid = 0.5 * (lower + upper)
        value = equilibrium(mid)
        if abs(value) < 1e-6:
            lower = upper = mid
            break
        if value < 0.0:
            lower = mid
        else:
            upper = mid
    x = 0.5 * (lower + upper)

    concrete_inertia = 0.0
    bottom_end = min(x, t_bottom)
    concrete_inertia += _segment_inertia_about_na(b_bottom, 0.0, bottom_end, x)
    web_end = min(x, top_flange_start)
    concrete_inertia += _segment_inertia_about_na(b_web, t_bottom, web_end, x)
    if x > top_flange_start:
        concrete_inertia += _segment_inertia_about_na(b_top, top_flange_start, x, x)

    inertia = concrete_inertia + transformed_steel_area * (d - x) ** 2
    if inertia <= 0.0:
        raise ValueError("Calculated cracked hogging second moment is non-positive.")

    moment_nmm = service_moment_knm * 1e6
    steel_stress = modular_ratio * moment_nmm * (d - x) / inertia
    if x <= t_bottom and t_bottom > 0.0:
        zone = "bottom_flange_only"
    elif x <= top_flange_start:
        zone = "bottom_flange_and_web" if t_bottom > 0.0 else "web_only"
    else:
        zone = "through_web_into_top_flange"

    return CrackedHoggingSectionSLS(
        neutral_axis_from_bottom_mm=x,
        second_moment_mm4=inertia,
        top_steel_stress_mpa=steel_stress,
        compression_zone=zone,
    )


def hogging_effective_tension_depth_mm(
    *,
    total_depth_m: float,
    steel_depth_from_bottom_m: float,
    neutral_axis_from_bottom_mm: float,
) -> float:
    """EC2 h_c,eff measured from the top tension face for negative bending."""
    h = total_depth_m * 1000.0
    d = steel_depth_from_bottom_m * 1000.0
    x = neutral_axis_from_bottom_mm
    if not 0.0 < d < h:
        raise ValueError("Top reinforcement depth must lie inside the section.")
    if not 0.0 < x < h:
        raise ValueError("Neutral axis must lie inside the section.")
    return min(2.5 * (h - d), (h - x) / 3.0, h / 2.0)


def hogging_effective_tension_area_mm2(
    *,
    bottom_flange_width_m: float,
    bottom_flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    top_tension_flange_width_m: float,
    top_tension_flange_thickness_m: float,
    hceff_mm: float,
) -> float:
    """Concrete area within the top h_c,eff tension zone."""
    if hceff_mm <= 0.0:
        raise ValueError("Effective tension depth must be positive.")
    h = total_depth_m * 1000.0
    if hceff_mm > h:
        raise ValueError("Effective tension depth cannot exceed overall depth.")

    b_bottom = bottom_flange_width_m * 1000.0
    t_bottom = bottom_flange_thickness_m * 1000.0
    b_web = web_width_m * 1000.0
    b_top = top_tension_flange_width_m * 1000.0
    t_top = top_tension_flange_thickness_m * 1000.0
    web_depth = h - t_bottom - t_top
    if web_depth <= 0.0:
        raise ValueError("Invalid hogging section: web depth must be positive.")

    if hceff_mm <= t_top:
        return b_top * hceff_mm
    if hceff_mm <= t_top + web_depth:
        return b_top * t_top + b_web * (hceff_mm - t_top)
    return (
        b_top * t_top
        + b_web * web_depth
        + b_bottom * (hceff_mm - t_top - web_depth)
    )


def crack_width_ec2_hogging_section(
    *,
    bottom_flange_width_m: float,
    bottom_flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    top_tension_flange_width_m: float,
    top_tension_flange_thickness_m: float,
    steel_area_mm2: float,
    steel_depth_from_bottom_m: float,
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
    """First-generation EC2 direct crack-width check for a hogging support section.

    ``cracking_moment_knm`` remains explicit because construction-stage/composite
    assumptions control the uncracked support section. This function does not
    infer that stiffness or tensile strength history silently.
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
        cracking_moment_knm,
    )
    if any(value <= 0.0 for value in positive):
        raise ValueError("Reinforcement, material, cover and crack inputs must be positive.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment magnitude cannot be negative.")
    if not 0.0 < kt <= 1.0:
        raise ValueError("kt must lie between zero and one.")

    modular_ratio = es_mpa / ecm_mpa
    cracked = cracked_hogging_section_sls(
        bottom_flange_width_m=bottom_flange_width_m,
        bottom_flange_thickness_m=bottom_flange_thickness_m,
        web_width_m=web_width_m,
        total_depth_m=total_depth_m,
        top_tension_flange_width_m=top_tension_flange_width_m,
        top_tension_flange_thickness_m=top_tension_flange_thickness_m,
        steel_area_mm2=steel_area_mm2,
        steel_depth_from_bottom_m=steel_depth_from_bottom_m,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment_knm,
    )
    hceff = hogging_effective_tension_depth_mm(
        total_depth_m=total_depth_m,
        steel_depth_from_bottom_m=steel_depth_from_bottom_m,
        neutral_axis_from_bottom_mm=cracked.neutral_axis_from_bottom_mm,
    )
    aceff = hogging_effective_tension_area_mm2(
        bottom_flange_width_m=bottom_flange_width_m,
        bottom_flange_thickness_m=bottom_flange_thickness_m,
        web_width_m=web_width_m,
        total_depth_m=total_depth_m,
        top_tension_flange_width_m=top_tension_flange_width_m,
        top_tension_flange_thickness_m=top_tension_flange_thickness_m,
        hceff_mm=hceff,
    )
    rho = steel_area_mm2 / aceff
    if rho <= 0.0:
        raise ValueError("Effective reinforcement ratio must be positive.")

    sigma_s = cracked.top_steel_stress_mpa
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
            status="uncracked under supplied hogging service moment",
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
        srmax = 1.3 * (h_mm - cracked.neutral_axis_from_bottom_mm)

    crack_width = srmax * strain_difference
    utilization = crack_width / crack_limit_mm
    return CrackWidthResult(
        crack_width_mm=crack_width,
        crack_limit_mm=crack_limit_mm,
        utilization=utilization,
        g_crack_mm=crack_limit_mm - crack_width,
        steel_stress_mpa=sigma_s,
        effective_tension_depth_mm=hceff,
        effective_tension_area_mm2=aceff,
        effective_reinforcement_ratio=rho,
        max_crack_spacing_mm=srmax,
        strain_difference=strain_difference,
        close_spacing=close_spacing,
        status="first-generation EC2 direct hogging support crack-width calculation",
    )
