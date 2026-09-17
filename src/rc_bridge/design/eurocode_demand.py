from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_flanged_flexure import (
    t_section_singly_reinforced_resistance,
)
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.design.eurocode_shear import (
    ShearConcreteResult,
    ShearReinforcementResult,
    concrete_shear_resistance,
    required_vertical_shear_reinforcement,
)
from rc_bridge.research.limit_states import flexural_limit_state, shear_limit_state


@dataclass(frozen=True)
class FlexuralDemandResult:
    required_steel_area_mm2: float
    provided_steel_area_mm2: float
    resistance_knm: float
    utilization: float
    g_flexure_knm: float
    status: str


@dataclass(frozen=True)
class ShearDemandResult:
    concrete_resistance_kn: float
    design_shear_kn: float
    utilization_concrete_only: float
    g_shear_concrete_kn: float
    shear_reinforcement: ShearReinforcementResult | None
    status: str


def required_tension_steel_rectangular(
    med_knm: float,
    width_m: float,
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    tolerance_knm: float = 0.01,
) -> float:
    """Solve for A_s such that simplified rectangular M_Rd >= M_Ed."""
    if med_knm < 0:
        raise ValueError("Design moment cannot be negative.")
    if med_knm == 0:
        return 0.0

    lower = 1.0
    upper = 1000.0
    for _ in range(30):
        result = rectangular_singly_reinforced_resistance(
            width_m,
            effective_depth_m,
            upper,
            fck_mpa,
            fyk_mpa,
            gamma_c=gamma_c,
            gamma_s=gamma_s,
            alpha_cc=alpha_cc,
        )
        if result.resistance_knm >= med_knm:
            break
        upper *= 2.0
    else:
        raise ValueError(
            "Unable to bracket required steel area; section may be outside model scope."
        )

    for _ in range(80):
        mid = 0.5 * (lower + upper)
        result = rectangular_singly_reinforced_resistance(
            width_m,
            effective_depth_m,
            mid,
            fck_mpa,
            fyk_mpa,
            gamma_c=gamma_c,
            gamma_s=gamma_s,
            alpha_cc=alpha_cc,
        )
        if abs(result.resistance_knm - med_knm) <= tolerance_knm:
            return mid
        if result.resistance_knm < med_knm:
            lower = mid
        else:
            upper = mid
    return upper


def required_tension_steel_t_section(
    med_knm: float,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    tolerance_knm: float = 0.01,
) -> float:
    """Solve for tension steel using the same T-section resistance kernel."""
    if med_knm < 0:
        raise ValueError("Design moment cannot be negative.")
    if med_knm == 0:
        return 0.0

    lower = 1.0
    upper = 1000.0
    for _ in range(30):
        result = t_section_singly_reinforced_resistance(
            effective_flange_width_m,
            flange_thickness_m,
            web_width_m,
            effective_depth_m,
            upper,
            fck_mpa,
            fyk_mpa,
        )
        if result.resistance_knm >= med_knm:
            break
        upper *= 2.0
    else:
        raise ValueError(
            "Unable to bracket required steel area; T-section may be outside model scope."
        )

    for _ in range(80):
        mid = 0.5 * (lower + upper)
        result = t_section_singly_reinforced_resistance(
            effective_flange_width_m,
            flange_thickness_m,
            web_width_m,
            effective_depth_m,
            mid,
            fck_mpa,
            fyk_mpa,
        )
        if abs(result.resistance_knm - med_knm) <= tolerance_knm:
            return mid
        if result.resistance_knm < med_knm:
            lower = mid
        else:
            upper = mid
    return upper


def check_flexure_rectangular(
    med_knm: float,
    width_m: float,
    effective_depth_m: float,
    provided_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
) -> FlexuralDemandResult:
    required = required_tension_steel_rectangular(
        med_knm,
        width_m,
        effective_depth_m,
        fck_mpa,
        fyk_mpa,
    )
    resistance = rectangular_singly_reinforced_resistance(
        width_m,
        effective_depth_m,
        provided_steel_area_mm2,
        fck_mpa,
        fyk_mpa,
    )
    utilization = (
        med_knm / resistance.resistance_knm
        if resistance.resistance_knm > 0
        else float("inf")
    )
    return FlexuralDemandResult(
        required_steel_area_mm2=required,
        provided_steel_area_mm2=provided_steel_area_mm2,
        resistance_knm=resistance.resistance_knm,
        utilization=utilization,
        g_flexure_knm=flexural_limit_state(resistance.resistance_knm, med_knm),
        status="simplified rectangular EC2 flexure; ductility checks pending",
    )


def check_flexure_t_section(
    med_knm: float,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    provided_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
) -> FlexuralDemandResult:
    required = required_tension_steel_t_section(
        med_knm,
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        effective_depth_m,
        fck_mpa,
        fyk_mpa,
    )
    resistance = t_section_singly_reinforced_resistance(
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        effective_depth_m,
        provided_steel_area_mm2,
        fck_mpa,
        fyk_mpa,
    )
    utilization = (
        med_knm / resistance.resistance_knm
        if resistance.resistance_knm > 0
        else float("inf")
    )
    return FlexuralDemandResult(
        required_steel_area_mm2=required,
        provided_steel_area_mm2=provided_steel_area_mm2,
        resistance_knm=resistance.resistance_knm,
        utilization=utilization,
        g_flexure_knm=flexural_limit_state(resistance.resistance_knm, med_knm),
        status=resistance.status,
    )


def check_shear(
    ved_kn: float,
    web_width_m: float,
    effective_depth_m: float,
    longitudinal_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    cot_theta: float = 2.0,
) -> ShearDemandResult:
    concrete: ShearConcreteResult = concrete_shear_resistance(
        web_width_m,
        effective_depth_m,
        longitudinal_steel_area_mm2,
        fck_mpa,
    )
    util = ved_kn / concrete.vrdc_kn if concrete.vrdc_kn > 0 else float("inf")
    reinforcement = None
    status = "concrete shear resistance adequate under current model"
    if ved_kn > concrete.vrdc_kn:
        reinforcement = required_vertical_shear_reinforcement(
            ved_kn,
            web_width_m,
            effective_depth_m,
            fck_mpa,
            fyk_mpa,
            cot_theta=cot_theta,
        )
        status = (
            "design shear reinforcement required; detailing and minimum reinforcement pending"
        )

    return ShearDemandResult(
        concrete_resistance_kn=concrete.vrdc_kn,
        design_shear_kn=ved_kn,
        utilization_concrete_only=util,
        g_shear_concrete_kn=shear_limit_state(concrete.vrdc_kn, ved_kn),
        shear_reinforcement=reinforcement,
        status=status,
    )
