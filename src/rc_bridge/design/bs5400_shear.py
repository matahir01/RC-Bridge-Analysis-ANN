from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class BS5400ShearResult:
    design_shear_kn: float
    design_shear_stress_mpa: float
    concrete_shear_stress_mpa: float
    depth_factor: float
    concrete_design_shear_stress_mpa: float
    concrete_resistance_kn: float
    maximum_shear_stress_mpa: float
    maximum_resistance_kn: float
    specified_fyv_mpa: float
    effective_fyv_mpa: float
    minimum_asv_per_s_mm2_per_mm: float
    minimum_asv_per_s_mm2_per_m: float
    design_asv_per_s_mm2_per_mm: float
    design_asv_per_s_mm2_per_m: float
    governing_asv_per_s_mm2_per_mm: float
    governing_asv_per_s_mm2_per_m: float
    requires_shear_reinforcement: bool
    exceeds_maximum_shear: bool
    g_shear_concrete_kn: float
    status: str


def check_shear_bs5400(
    *,
    ved_kn: float,
    web_width_m: float,
    effective_depth_m: float,
    longitudinal_steel_area_mm2: float,
    fcu_mpa: float,
    fyv_mpa: float,
    gamma_m_concrete_shear: float = 1.25,
    concrete_shear_coefficient: float = 0.27,
    depth_reference_mm: float = 500.0,
    minimum_depth_factor: float = 0.70,
    maximum_shear_coefficient: float = 0.75,
    maximum_shear_cap_mpa: float = 4.75,
    minimum_link_stress_mpa: float = 0.40,
    steel_design_factor: float = 0.87,
    maximum_link_yield_mpa: float = 460.0,
) -> BS5400ShearResult:
    """Legacy BS 5400 Part 4 RC shear and vertical-link design kernel.

    For beams, minimum vertical links are retained even when the design shear
    stress does not exceed the concrete design shear stress. When it does, the
    link requirement follows b(v + 0.4 - xi_s v_c)/(0.87 f_yv), which merges
    continuously with the minimum-link requirement at the transition.

    The link yield strength used in these equations is capped at 460 MPa by
    default. Bent-up bars, support enhancement and additional longitudinal shear
    reinforcement are outside this kernel and must be checked separately.
    """
    if ved_kn < 0.0:
        raise ValueError("ved_kn cannot be negative.")
    if min(
        web_width_m,
        effective_depth_m,
        longitudinal_steel_area_mm2,
        fcu_mpa,
        fyv_mpa,
    ) <= 0.0:
        raise ValueError("Section dimensions, reinforcement and strengths must be positive.")
    if min(
        gamma_m_concrete_shear,
        concrete_shear_coefficient,
        depth_reference_mm,
        minimum_depth_factor,
        maximum_shear_coefficient,
        maximum_shear_cap_mpa,
        minimum_link_stress_mpa,
        steel_design_factor,
        maximum_link_yield_mpa,
    ) <= 0.0:
        raise ValueError("BS 5400 shear coefficients must be positive.")

    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    design_shear_stress_mpa = ved_kn * 1000.0 / (bw_mm * d_mm)

    reinforcement_ratio_percent = 100.0 * longitudinal_steel_area_mm2 / (bw_mm * d_mm)
    concrete_shear_stress_mpa = (
        concrete_shear_coefficient
        / gamma_m_concrete_shear
        * reinforcement_ratio_percent ** (1.0 / 3.0)
        * fcu_mpa ** (1.0 / 3.0)
    )
    depth_factor = max((depth_reference_mm / d_mm) ** 0.25, minimum_depth_factor)
    concrete_design_stress_mpa = depth_factor * concrete_shear_stress_mpa
    concrete_resistance_kn = concrete_design_stress_mpa * bw_mm * d_mm / 1000.0

    maximum_shear_stress_mpa = min(
        maximum_shear_coefficient * sqrt(fcu_mpa),
        maximum_shear_cap_mpa,
    )
    maximum_resistance_kn = maximum_shear_stress_mpa * bw_mm * d_mm / 1000.0

    effective_fyv_mpa = min(fyv_mpa, maximum_link_yield_mpa)
    denominator = steel_design_factor * effective_fyv_mpa
    minimum_asv_per_s_mm2_per_mm = minimum_link_stress_mpa * bw_mm / denominator

    requires_links_above_minimum = design_shear_stress_mpa > concrete_design_stress_mpa
    design_asv_per_s_mm2_per_mm = 0.0
    if requires_links_above_minimum:
        design_asv_per_s_mm2_per_mm = (
            bw_mm
            * (
                design_shear_stress_mpa
                + minimum_link_stress_mpa
                - concrete_design_stress_mpa
            )
            / denominator
        )

    governing_asv_per_s_mm2_per_mm = max(
        minimum_asv_per_s_mm2_per_mm,
        design_asv_per_s_mm2_per_mm,
    )
    exceeds_maximum = design_shear_stress_mpa > maximum_shear_stress_mpa

    return BS5400ShearResult(
        design_shear_kn=ved_kn,
        design_shear_stress_mpa=design_shear_stress_mpa,
        concrete_shear_stress_mpa=concrete_shear_stress_mpa,
        depth_factor=depth_factor,
        concrete_design_shear_stress_mpa=concrete_design_stress_mpa,
        concrete_resistance_kn=concrete_resistance_kn,
        maximum_shear_stress_mpa=maximum_shear_stress_mpa,
        maximum_resistance_kn=maximum_resistance_kn,
        specified_fyv_mpa=fyv_mpa,
        effective_fyv_mpa=effective_fyv_mpa,
        minimum_asv_per_s_mm2_per_mm=minimum_asv_per_s_mm2_per_mm,
        minimum_asv_per_s_mm2_per_m=minimum_asv_per_s_mm2_per_mm * 1000.0,
        design_asv_per_s_mm2_per_mm=design_asv_per_s_mm2_per_mm,
        design_asv_per_s_mm2_per_m=design_asv_per_s_mm2_per_mm * 1000.0,
        governing_asv_per_s_mm2_per_mm=governing_asv_per_s_mm2_per_mm,
        governing_asv_per_s_mm2_per_m=governing_asv_per_s_mm2_per_mm * 1000.0,
        requires_shear_reinforcement=requires_links_above_minimum,
        exceeds_maximum_shear=exceeds_maximum,
        g_shear_concrete_kn=concrete_resistance_kn - ved_kn,
        status=(
            "BS 5400 Part 4 legacy/comparison vertical-link design; minimum links, "
            "designed link demand and web-crushing ceiling evaluated. Bent-up bars, "
            "support enhancement and additional longitudinal shear steel remain separate."
        ),
    )
