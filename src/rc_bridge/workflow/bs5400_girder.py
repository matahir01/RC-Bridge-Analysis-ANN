from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.bs5400.combinations import BS5400Factors, factored_uls
from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.design.bs5400_flanged_flexure import (
    BS5400TSectionFlexureResult,
    check_t_section_flexure_bs5400,
)
from rc_bridge.design.bs5400_flexure import (
    BS5400RectangularFlexureResult,
    check_rectangular_flexure_bs5400,
)
from rc_bridge.design.bs5400_shear import BS5400ShearResult, check_shear_bs5400


@dataclass(frozen=True)
class BS5400RectangularGirderInput:
    width_m: float
    web_width_m: float
    effective_depth_m: float
    steel_area_mm2: float
    shear_steel_yield_mpa: float | None = None

    def __post_init__(self) -> None:
        if min(
            self.width_m,
            self.web_width_m,
            self.effective_depth_m,
            self.steel_area_mm2,
        ) <= 0.0:
            raise ValueError("BS 5400 rectangular girder inputs must be positive.")
        if self.web_width_m > self.width_m:
            raise ValueError("web_width_m cannot exceed width_m.")
        if self.shear_steel_yield_mpa is not None and self.shear_steel_yield_mpa <= 0.0:
            raise ValueError("shear_steel_yield_mpa must be positive when supplied.")


@dataclass(frozen=True)
class BS5400TGirderInput:
    effective_flange_width_m: float
    flange_thickness_m: float
    web_width_m: float
    effective_depth_m: float
    steel_area_mm2: float
    shear_steel_yield_mpa: float | None = None

    def __post_init__(self) -> None:
        if min(
            self.effective_flange_width_m,
            self.flange_thickness_m,
            self.web_width_m,
            self.effective_depth_m,
            self.steel_area_mm2,
        ) <= 0.0:
            raise ValueError("BS 5400 T-girder inputs must be positive.")
        if self.web_width_m > self.effective_flange_width_m:
            raise ValueError("web_width_m cannot exceed effective_flange_width_m.")
        if self.flange_thickness_m >= self.effective_depth_m:
            raise ValueError("flange_thickness_m must be less than effective_depth_m.")
        if self.shear_steel_yield_mpa is not None and self.shear_steel_yield_mpa <= 0.0:
            raise ValueError("shear_steel_yield_mpa must be positive when supplied.")


@dataclass(frozen=True)
class BS5400RectangularGirderResult:
    uls_combination: FactoredCombination
    flexure: BS5400RectangularFlexureResult
    shear: BS5400ShearResult
    status: str


@dataclass(frozen=True)
class BS5400TGirderResult:
    uls_combination: FactoredCombination
    flexure: BS5400TSectionFlexureResult
    shear: BS5400ShearResult
    status: str


def _bs5400_material_strengths(project: ProjectInput) -> tuple[float, float]:
    if project.design_code != DesignCode.BS5400:
        raise ValueError("BS 5400 girder workflow requires a BS5400 project.")
    if project.materials.fcu_mpa is None:
        raise ValueError(
            "BS 5400 design requires explicit concrete cube strength fcu_mpa; "
            "it is not inferred from Eurocode fck_mpa."
        )
    return float(project.materials.fcu_mpa), float(project.materials.fyk_mpa)


def run_bs5400_rectangular_girder_case(
    project: ProjectInput,
    *,
    permanent_effects: LoadEffects,
    live_effects: LoadEffects,
    factors: BS5400Factors,
    section: BS5400RectangularGirderInput,
) -> BS5400RectangularGirderResult:
    """Run the current BS 5400 legacy/comparison rectangular girder ULS path."""
    fcu_mpa, fy_mpa = _bs5400_material_strengths(project)
    fyv_mpa = section.shear_steel_yield_mpa or fy_mpa
    combination = factored_uls(permanent_effects, live_effects, factors)

    flexure = check_rectangular_flexure_bs5400(
        med_knm=abs(combination.effects.moment_knm),
        width_m=section.width_m,
        effective_depth_m=section.effective_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fy_mpa=fy_mpa,
    )
    shear = check_shear_bs5400(
        ved_kn=abs(combination.effects.shear_kn),
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fyv_mpa=fyv_mpa,
    )

    return BS5400RectangularGirderResult(
        uls_combination=combination,
        flexure=flexure,
        shear=shear,
        status=(
            "BS 5400 rectangular ULS comparison path active; SLS cracking and "
            "final shear-link sizing remain to be implemented and verified"
        ),
    )


def run_bs5400_t_girder_case(
    project: ProjectInput,
    *,
    permanent_effects: LoadEffects,
    live_effects: LoadEffects,
    factors: BS5400Factors,
    section: BS5400TGirderInput,
) -> BS5400TGirderResult:
    """Run positive-bending BS 5400 ULS flexure/shear for a T-girder.

    The effective flange width is caller-supplied so the bridge analysis/design
    basis remains explicit. Positive bending only is covered at this stage.
    """
    fcu_mpa, fy_mpa = _bs5400_material_strengths(project)
    fyv_mpa = section.shear_steel_yield_mpa or fy_mpa
    combination = factored_uls(permanent_effects, live_effects, factors)

    flexure = check_t_section_flexure_bs5400(
        med_knm=abs(combination.effects.moment_knm),
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fy_mpa=fy_mpa,
    )
    shear = check_shear_bs5400(
        ved_kn=abs(combination.effects.shear_kn),
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fyv_mpa=fyv_mpa,
    )

    return BS5400TGirderResult(
        uls_combination=combination,
        flexure=flexure,
        shear=shear,
        status=(
            "BS 5400 positive-bending T-girder ULS comparison path active; SLS cracking, "
            "negative bending and final shear-link sizing remain pending"
        ),
    )
