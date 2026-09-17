from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import (
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    TGirderProfile,
)
from rc_bridge.design.eurocode_demand import FlexuralDemandResult, check_flexure_t_section
from rc_bridge.design.eurocode_support_flexure import NegativeBendingFlexureResult
from rc_bridge.workflow.continuous_shear_design import (
    ContinuousShearDesignCheck,
    ContinuousShearDesignInput as CanonicalContinuousShearDesignInput,
    check_continuous_section_shear,
)
from rc_bridge.workflow.continuous_support_design import (
    ContinuousSupportFlangedFlexureInput,
    ContinuousSupportFlexureInput,
    check_continuous_support_flexure,
)
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeResult,
    ContinuousDesignEnvelopeStation,
)


@dataclass(frozen=True)
class PositiveCompositeTSectionDesignInput:
    effective_flange_width_m: float
    flange_thickness_m: float
    web_width_m: float
    effective_depth_from_top_m: float
    provided_bottom_steel_area_mm2: float


@dataclass(frozen=True)
class NegativeSupportRectangularDesignInput:
    compression_width_m: float
    effective_depth_from_bottom_m: float
    provided_top_steel_area_mm2: float


@dataclass(frozen=True)
class NegativeSupportFlangedDesignInput:
    bottom_flange_width_m: float
    bottom_flange_thickness_m: float
    web_width_m: float
    effective_depth_from_bottom_m: float
    provided_top_steel_area_mm2: float


NegativeSupportDesignInput = (
    NegativeSupportRectangularDesignInput | NegativeSupportFlangedDesignInput
)


@dataclass(frozen=True)
class ContinuousShearDesignInput:
    web_width_m: float
    effective_depth_m: float
    longitudinal_steel_area_mm2: float
    provided_asw_per_s_mm2_per_m: float | None = None
    cot_theta: float = 2.0

    def __post_init__(self) -> None:
        if min(
            self.web_width_m,
            self.effective_depth_m,
            self.longitudinal_steel_area_mm2,
        ) <= 0.0:
            raise ValueError("Shear geometry and longitudinal reinforcement must be positive.")
        if self.provided_asw_per_s_mm2_per_m is not None and self.provided_asw_per_s_mm2_per_m < 0.0:
            raise ValueError("Provided A_sw/s cannot be negative.")


@dataclass(frozen=True)
class ContinuousEurocodeULSDesignResult:
    positive_flexure: FlexuralDemandResult
    negative_flexure: NegativeBendingFlexureResult
    shear: ContinuousShearDesignCheck
    positive_station: ContinuousDesignEnvelopeStation
    negative_station: ContinuousDesignEnvelopeStation
    shear_station: ContinuousDesignEnvelopeStation
    positive_design_moment_knm: float
    negative_design_moment_knm: float
    design_shear_kn: float
    status: str


def negative_support_design_input_from_project(
    project: ProjectInput,
    *,
    effective_depth_from_bottom_m: float,
    provided_top_steel_area_mm2: float,
) -> NegativeSupportDesignInput:
    """Build the hogging compression model from the physical precast profile.

    The deck slab is deliberately ignored on the compression side for hogging.
    Rectangular precast girders use their full width; T-girders use the lower stem
    width because they have no lower flange; I-girders use their actual bottom
    flange plus web. The top-steel effective depth must still be supplied because
    it depends on the actual deck reinforcement location and cover.
    """
    if effective_depth_from_bottom_m <= 0.0:
        raise ValueError("Hogging effective depth from the bottom must be positive.")
    if provided_top_steel_area_mm2 <= 0.0:
        raise ValueError("Provided top steel area must be positive.")

    profile = project.geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Physical girder profile dimensions are required to derive the hogging compression model."
        )

    if isinstance(profile, IGirderProfile):
        return NegativeSupportFlangedDesignInput(
            bottom_flange_width_m=float(profile.bottom_flange_width_m),
            bottom_flange_thickness_m=float(profile.bottom_flange_thickness_m),
            web_width_m=float(profile.web_width_m),
            effective_depth_from_bottom_m=effective_depth_from_bottom_m,
            provided_top_steel_area_mm2=provided_top_steel_area_mm2,
        )
    if isinstance(profile, TGirderProfile):
        return NegativeSupportRectangularDesignInput(
            compression_width_m=float(profile.web_width_m),
            effective_depth_from_bottom_m=effective_depth_from_bottom_m,
            provided_top_steel_area_mm2=provided_top_steel_area_mm2,
        )
    if isinstance(profile, RectangularGirderProfile):
        return NegativeSupportRectangularDesignInput(
            compression_width_m=float(profile.width_m),
            effective_depth_from_bottom_m=effective_depth_from_bottom_m,
            provided_top_steel_area_mm2=provided_top_steel_area_mm2,
        )
    raise TypeError("Unsupported physical girder profile type.")


def _canonical_support_input(
    negative_section: NegativeSupportDesignInput,
    *,
    fck_mpa: float,
    fyk_mpa: float,
) -> ContinuousSupportFlexureInput | ContinuousSupportFlangedFlexureInput:
    if isinstance(negative_section, NegativeSupportFlangedDesignInput):
        return ContinuousSupportFlangedFlexureInput(
            bottom_flange_width_m=negative_section.bottom_flange_width_m,
            bottom_flange_thickness_m=negative_section.bottom_flange_thickness_m,
            web_width_m=negative_section.web_width_m,
            effective_depth_from_bottom_m=negative_section.effective_depth_from_bottom_m,
            provided_top_steel_area_mm2=negative_section.provided_top_steel_area_mm2,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
        )
    return ContinuousSupportFlexureInput(
        compression_width_m=negative_section.compression_width_m,
        effective_depth_m=negative_section.effective_depth_from_bottom_m,
        provided_top_steel_area_mm2=negative_section.provided_top_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
    )


def _canonical_shear_input(
    shear_section: ContinuousShearDesignInput,
    *,
    fck_mpa: float,
    fyk_mpa: float,
) -> CanonicalContinuousShearDesignInput:
    return CanonicalContinuousShearDesignInput(
        web_width_m=shear_section.web_width_m,
        effective_depth_m=shear_section.effective_depth_m,
        longitudinal_steel_area_mm2=shear_section.longitudinal_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        provided_asw_per_s_mm2_per_m=shear_section.provided_asw_per_s_mm2_per_m,
        cot_theta=shear_section.cot_theta,
    )


def run_continuous_eurocode_uls_design(
    envelope: ContinuousDesignEnvelopeResult,
    *,
    positive_section: PositiveCompositeTSectionDesignInput,
    negative_section: NegativeSupportDesignInput,
    shear_section: ContinuousShearDesignInput,
    fck_mpa: float,
    fyk_mpa: float,
) -> ContinuousEurocodeULSDesignResult:
    """Design the governing continuous-girder ULS sections from an LM1 envelope.

    Sagging resistance uses the composite top flange. Hogging is delegated to the
    canonical signed support-design workflow. Shear is delegated to the canonical
    signed-section shear workflow, which distinguishes required reinforcement from
    actual supplied links instead of treating a calculated requirement as provided.
    """
    if fck_mpa <= 0.0 or fyk_mpa <= 0.0:
        raise ValueError("Concrete and reinforcement strengths must be positive.")

    positive_moment = max(0.0, envelope.max_positive_uls_moment_knm)
    positive_station = envelope.max_positive_moment_station
    negative_station = envelope.min_negative_moment_station
    shear_station = envelope.max_abs_shear_station

    positive = check_flexure_t_section(
        med_knm=positive_moment,
        effective_flange_width_m=positive_section.effective_flange_width_m,
        flange_thickness_m=positive_section.flange_thickness_m,
        web_width_m=positive_section.web_width_m,
        effective_depth_m=positive_section.effective_depth_from_top_m,
        provided_steel_area_mm2=positive_section.provided_bottom_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
    )

    support_check = check_continuous_support_flexure(
        negative_station.moment_combinations,
        _canonical_support_input(
            negative_section,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
        ),
    )
    negative = support_check.flexure

    shear = check_continuous_section_shear(
        shear_station.shear_combinations,
        _canonical_shear_input(
            shear_section,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
        ),
    )

    return ContinuousEurocodeULSDesignResult(
        positive_flexure=positive,
        negative_flexure=negative,
        shear=shear,
        positive_station=positive_station,
        negative_station=negative_station,
        shear_station=shear_station,
        positive_design_moment_knm=positive_moment,
        negative_design_moment_knm=negative.design_moment_magnitude_knm,
        design_shear_kn=shear.design_shear_kn,
        status=(
            "Governing continuous Eurocode ULS design: composite T-section for sagging, "
            "canonical signed support workflow for hogging, and canonical signed shear workflow. "
            "Ductility, support-face shear location and continuous-region SLS remain separate."
        ),
    )
