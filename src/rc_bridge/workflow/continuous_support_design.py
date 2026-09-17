from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.eurocode.combinations import SignedSectionCombinationSet
from rc_bridge.design.eurocode_support_flexure import (
    NegativeBendingFlexureResult,
    check_negative_bending_flanged_support,
    check_negative_bending_rectangular_support,
)


@dataclass(frozen=True)
class ContinuousSupportFlexureInput:
    compression_width_m: float
    effective_depth_m: float
    provided_top_steel_area_mm2: float
    fck_mpa: float
    fyk_mpa: float

    def __post_init__(self) -> None:
        if min(
            self.compression_width_m,
            self.effective_depth_m,
            self.provided_top_steel_area_mm2,
            self.fck_mpa,
            self.fyk_mpa,
        ) <= 0.0:
            raise ValueError("Support flexure geometry, reinforcement and strengths must be positive.")


@dataclass(frozen=True)
class ContinuousSupportFlangedFlexureInput:
    bottom_flange_width_m: float
    bottom_flange_thickness_m: float
    web_width_m: float
    effective_depth_from_bottom_m: float
    provided_top_steel_area_mm2: float
    fck_mpa: float
    fyk_mpa: float

    def __post_init__(self) -> None:
        if min(
            self.bottom_flange_width_m,
            self.bottom_flange_thickness_m,
            self.web_width_m,
            self.effective_depth_from_bottom_m,
            self.provided_top_steel_area_mm2,
            self.fck_mpa,
            self.fyk_mpa,
        ) <= 0.0:
            raise ValueError("Flanged support flexure geometry, reinforcement and strengths must be positive.")
        if self.web_width_m > self.bottom_flange_width_m:
            raise ValueError("Support web width cannot exceed the bottom flange width.")
        if self.bottom_flange_thickness_m >= self.effective_depth_from_bottom_m:
            raise ValueError("Bottom flange thickness must be less than the effective depth.")


ContinuousSupportDesignInput = ContinuousSupportFlexureInput | ContinuousSupportFlangedFlexureInput


@dataclass(frozen=True)
class ContinuousSupportFlexureCheck:
    negative_uls_effect_knm: float
    flexure: NegativeBendingFlexureResult
    status: str


def check_continuous_support_flexure(
    combinations: SignedSectionCombinationSet,
    input_data: ContinuousSupportDesignInput,
) -> ContinuousSupportFlexureCheck:
    """Route the negative ULS branch into the verified support-region top-steel check.

    The positive-bending deck compression flange is never credited. A web/stem
    compression region uses ``ContinuousSupportFlexureInput``; an I-girder with an
    actual lower compression flange uses ``ContinuousSupportFlangedFlexureInput``.
    """
    if combinations.response_kind != "moment":
        raise ValueError("Support flexure design requires moment combinations.")
    if combinations.negative_uls_effect >= 0.0:
        raise ValueError(
            "The selected negative ULS branch is not hogging; no negative-bending support check applies."
        )

    if isinstance(input_data, ContinuousSupportFlangedFlexureInput):
        flexure = check_negative_bending_flanged_support(
            design_moment_knm=combinations.negative_uls_effect,
            bottom_flange_width_m=input_data.bottom_flange_width_m,
            bottom_flange_thickness_m=input_data.bottom_flange_thickness_m,
            web_width_m=input_data.web_width_m,
            effective_depth_from_bottom_m=input_data.effective_depth_from_bottom_m,
            provided_top_steel_area_mm2=input_data.provided_top_steel_area_mm2,
            fck_mpa=input_data.fck_mpa,
            fyk_mpa=input_data.fyk_mpa,
        )
    else:
        flexure = check_negative_bending_rectangular_support(
            design_moment_knm=combinations.negative_uls_effect,
            compression_width_m=input_data.compression_width_m,
            effective_depth_m=input_data.effective_depth_m,
            provided_top_steel_area_mm2=input_data.provided_top_steel_area_mm2,
            fck_mpa=input_data.fck_mpa,
            fyk_mpa=input_data.fyk_mpa,
        )

    return ContinuousSupportFlexureCheck(
        negative_uls_effect_knm=combinations.negative_uls_effect,
        flexure=flexure,
        status=(
            "Continuous support negative ULS branch checked with explicit top reinforcement; "
            "positive-bending deck compression flange is not credited"
        ),
    )
