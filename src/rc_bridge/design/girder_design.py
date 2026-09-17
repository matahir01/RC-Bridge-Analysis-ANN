from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.common import LoadEffects
from rc_bridge.design.eurocode_demand import (
    FlexuralDemandResult,
    ShearDemandResult,
    check_flexure_rectangular,
    check_flexure_t_section,
    check_shear,
)


@dataclass(frozen=True)
class GirderDesignResult:
    girder_index: int
    design_effects: LoadEffects
    flexure: FlexuralDemandResult
    shear: ShearDemandResult


def design_rectangular_girder_ec2(
    girder_index: int,
    design_effects: LoadEffects,
    width_m: float,
    web_width_m: float,
    effective_depth_m: float,
    provided_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    cot_theta: float = 2.0,
) -> GirderDesignResult:
    """Run current EC2 flexure/shear checks for one rectangular girder."""
    if girder_index <= 0:
        raise ValueError("girder_index must be positive.")

    flexure = check_flexure_rectangular(
        med_knm=design_effects.moment_knm,
        width_m=width_m,
        effective_depth_m=effective_depth_m,
        provided_steel_area_mm2=provided_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
    )
    shear = check_shear(
        ved_kn=abs(design_effects.shear_kn),
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        longitudinal_steel_area_mm2=provided_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        cot_theta=cot_theta,
    )
    return GirderDesignResult(
        girder_index=girder_index,
        design_effects=design_effects,
        flexure=flexure,
        shear=shear,
    )


def design_t_girder_ec2(
    girder_index: int,
    design_effects: LoadEffects,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    provided_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    cot_theta: float = 2.0,
) -> GirderDesignResult:
    """Run positive-bending T-section flexure plus web shear checks."""
    if girder_index <= 0:
        raise ValueError("girder_index must be positive.")

    flexure = check_flexure_t_section(
        med_knm=design_effects.moment_knm,
        effective_flange_width_m=effective_flange_width_m,
        flange_thickness_m=flange_thickness_m,
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        provided_steel_area_mm2=provided_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
    )
    shear = check_shear(
        ved_kn=abs(design_effects.shear_kn),
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        longitudinal_steel_area_mm2=provided_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        cot_theta=cot_theta,
    )
    return GirderDesignResult(
        girder_index=girder_index,
        design_effects=design_effects,
        flexure=flexure,
        shear=shear,
    )
