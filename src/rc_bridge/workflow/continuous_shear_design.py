from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rc_bridge.codes.eurocode.combinations import SignedSectionCombinationSet
from rc_bridge.design.eurocode_shear import (
    ProvidedShearResistanceResult,
    ShearConcreteResult,
    ShearReinforcementResult,
    concrete_shear_resistance,
    provided_vertical_shear_resistance,
    required_vertical_shear_reinforcement,
)


@dataclass(frozen=True)
class ContinuousShearDesignInput:
    web_width_m: float
    effective_depth_m: float
    longitudinal_steel_area_mm2: float
    fck_mpa: float
    fyk_mpa: float
    provided_asw_per_s_mm2_per_m: float | None = None
    cot_theta: float = 2.0

    def __post_init__(self) -> None:
        if min(
            self.web_width_m,
            self.effective_depth_m,
            self.longitudinal_steel_area_mm2,
            self.fck_mpa,
            self.fyk_mpa,
        ) <= 0.0:
            raise ValueError("Shear geometry, longitudinal reinforcement and strengths must be positive.")
        if self.provided_asw_per_s_mm2_per_m is not None and self.provided_asw_per_s_mm2_per_m < 0.0:
            raise ValueError("Provided A_sw/s cannot be negative.")
        if not 1.0 <= self.cot_theta <= 2.5:
            raise ValueError("cot(theta) must lie between 1.0 and 2.5 for this implementation.")


@dataclass(frozen=True)
class ContinuousShearDesignCheck:
    positive_uls_shear_kn: float
    negative_uls_shear_kn: float
    governing_branch: Literal["positive", "negative"]
    design_shear_kn: float
    concrete: ShearConcreteResult
    required_links: ShearReinforcementResult | None
    provided_links: ProvidedShearResistanceResult | None
    governing_resistance_kn: float | None
    utilization: float | None
    g_shear_kn: float | None
    reinforcement_required: bool
    provided_reinforcement_adequate: bool | None
    status: str


def check_continuous_section_shear(
    combinations: SignedSectionCombinationSet,
    input_data: ContinuousShearDesignInput,
) -> ContinuousShearDesignCheck:
    """Check the governing signed ULS shear branch at one continuous-girder section.

    Shear resistance is direction independent in this longitudinal model, so the
    larger absolute ULS branch governs. If V_Ed exceeds V_Rd,c, required vertical
    links are calculated. A reinforced capacity is reported only when an actual
    supplied A_sw/s is provided; the workflow never treats the required link ratio
    as though it had already been detailed on the bridge.
    """
    if combinations.response_kind != "shear":
        raise ValueError("Continuous shear design requires shear combinations.")

    positive = combinations.positive_uls_effect
    negative = combinations.negative_uls_effect
    if abs(negative) > abs(positive):
        branch: Literal["positive", "negative"] = "negative"
        ved_kn = abs(negative)
    else:
        branch = "positive"
        ved_kn = abs(positive)

    concrete = concrete_shear_resistance(
        input_data.web_width_m,
        input_data.effective_depth_m,
        input_data.longitudinal_steel_area_mm2,
        input_data.fck_mpa,
    )
    reinforcement_required = ved_kn > concrete.vrdc_kn
    required_links = None
    if reinforcement_required:
        required_links = required_vertical_shear_reinforcement(
            ved_kn,
            input_data.web_width_m,
            input_data.effective_depth_m,
            input_data.fck_mpa,
            input_data.fyk_mpa,
            cot_theta=input_data.cot_theta,
        )

    provided_links = None
    if input_data.provided_asw_per_s_mm2_per_m is not None:
        provided_links = provided_vertical_shear_resistance(
            provided_asw_per_s_mm2_per_m=input_data.provided_asw_per_s_mm2_per_m,
            web_width_m=input_data.web_width_m,
            effective_depth_m=input_data.effective_depth_m,
            fck_mpa=input_data.fck_mpa,
            fyk_mpa=input_data.fyk_mpa,
            cot_theta=input_data.cot_theta,
        )

    if not reinforcement_required:
        resistance = concrete.vrdc_kn
        utilization = ved_kn / resistance if resistance > 0.0 else float("inf")
        g_shear = resistance - ved_kn
        provided_adequate: bool | None = True
        status = (
            "Concrete shear resistance is adequate for the governing continuous-section ULS demand; "
            "minimum bridge shear reinforcement/detailing requirements remain a separate check"
        )
    elif provided_links is None:
        resistance = None
        utilization = None
        g_shear = None
        provided_adequate = None
        status = (
            "Shear reinforcement is required, but no supplied A_sw/s was provided; required links are "
            "reported without assuming that they have been detailed"
        )
    else:
        resistance = provided_links.governing_resistance_kn
        utilization = ved_kn / resistance if resistance > 0.0 else float("inf")
        g_shear = resistance - ved_kn
        provided_adequate = resistance >= ved_kn
        status = (
            "Governing continuous-section ULS shear checked using supplied vertical-link resistance; "
            "minimum reinforcement, spacing and anchorage detailing remain separate checks"
        )

    return ContinuousShearDesignCheck(
        positive_uls_shear_kn=positive,
        negative_uls_shear_kn=negative,
        governing_branch=branch,
        design_shear_kn=ved_kn,
        concrete=concrete,
        required_links=required_links,
        provided_links=provided_links,
        governing_resistance_kn=resistance,
        utilization=utilization,
        g_shear_kn=g_shear,
        reinforcement_required=reinforcement_required,
        provided_reinforcement_adequate=provided_adequate,
        status=status,
    )
