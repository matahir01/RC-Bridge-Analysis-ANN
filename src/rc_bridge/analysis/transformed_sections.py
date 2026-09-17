from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrackedTSectionProperties:
    neutral_axis_from_top_mm: float
    second_moment_mm4: float
    steel_stress_mpa: float


def cracked_t_section_properties(
    *,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    modular_ratio: float,
    service_moment_knm: float,
) -> CrackedTSectionProperties:
    """Return transformed cracked T-section properties for positive bending.

    Tensile concrete is neglected. The neutral axis is solved from transformed
    first-moment equilibrium and may lie in the flange or the web. This is a
    code-neutral elastic section-analysis helper; design-code-specific crack or
    stress limits are applied by their own modules.
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
    if any(value <= 0.0 for value in values):
        raise ValueError("Section, reinforcement and modular-ratio inputs must be positive.")
    if service_moment_knm < 0.0:
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
    if equilibrium(lower) >= 0.0 or equilibrium(upper) <= 0.0:
        raise ValueError("Unable to bracket cracked neutral axis for this section.")

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
    if inertia <= 0.0:
        raise ValueError("Calculated cracked second moment is non-positive.")

    moment_nmm = service_moment_knm * 1e6
    steel_stress_mpa = modular_ratio * moment_nmm * (d - x) / inertia

    return CrackedTSectionProperties(
        neutral_axis_from_top_mm=x,
        second_moment_mm4=inertia,
        steel_stress_mpa=steel_stress_mpa,
    )
