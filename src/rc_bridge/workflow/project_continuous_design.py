from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_demand import (
    FlexuralDemandResult,
    ShearDemandResult,
    check_flexure_rectangular,
    check_flexure_t_section,
    check_shear,
)
from rc_bridge.design.eurocode_oriented_demand import check_flexure_oriented_flanged
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
    cot_theta: float = 2.0


@dataclass(frozen=True)
class ContinuousEurocodeULSDesignResult:
    positive_flexure: FlexuralDemandResult
    negative_flexure: FlexuralDemandResult
    shear: ShearDemandResult
    positive_station: ContinuousDesignEnvelopeStation
    negative_station: ContinuousDesignEnvelopeStation
    shear_station: ContinuousDesignEnvelopeStation
    positive_design_moment_knm: float
    negative_design_moment_knm: float
    design_shear_kn: float
    status: str


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

    Sagging resistance uses the composite top flange. Hogging resistance is
    intentionally separate: the deck is on the tension side and is never reused
    as a compression flange. A T-stem/rectangular lower section can therefore use
    ``NegativeSupportRectangularDesignInput``; an I-girder with a real lower flange
    can use ``NegativeSupportFlangedDesignInput``.
    """
    if fck_mpa <= 0.0 or fyk_mpa <= 0.0:
        raise ValueError("Concrete and reinforcement strengths must be positive.")

    positive_moment = max(0.0, envelope.max_positive_uls_moment_knm)
    negative_moment = max(0.0, -envelope.min_negative_uls_moment_knm)
    design_shear = envelope.max_abs_uls_shear_kn

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

    if isinstance(negative_section, NegativeSupportFlangedDesignInput):
        negative = check_flexure_oriented_flanged(
            med_knm=negative_moment,
            compression_flange_width_m=negative_section.bottom_flange_width_m,
            compression_flange_thickness_m=negative_section.bottom_flange_thickness_m,
            web_width_m=negative_section.web_width_m,
            effective_depth_from_compression_face_m=(
                negative_section.effective_depth_from_bottom_m
            ),
            provided_steel_area_mm2=negative_section.provided_top_steel_area_mm2,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
            compression_face="bottom",
        )
    else:
        negative = check_flexure_rectangular(
            med_knm=negative_moment,
            width_m=negative_section.compression_width_m,
            effective_depth_m=negative_section.effective_depth_from_bottom_m,
            provided_steel_area_mm2=negative_section.provided_top_steel_area_mm2,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
        )

    shear = check_shear(
        ved_kn=design_shear,
        web_width_m=shear_section.web_width_m,
        effective_depth_m=shear_section.effective_depth_m,
        longitudinal_steel_area_mm2=shear_section.longitudinal_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        cot_theta=shear_section.cot_theta,
    )

    return ContinuousEurocodeULSDesignResult(
        positive_flexure=positive,
        negative_flexure=negative,
        shear=shear,
        positive_station=envelope.max_positive_moment_station,
        negative_station=envelope.min_negative_moment_station,
        shear_station=envelope.max_abs_shear_station,
        positive_design_moment_knm=positive_moment,
        negative_design_moment_knm=negative_moment,
        design_shear_kn=design_shear,
        status=(
            "Governing continuous Eurocode ULS design: composite T-section for sagging, "
            "explicit lower-girder compression model for hogging, and web shear check. "
            "Ductility, support-face shear location and continuous-region SLS remain separate."
        ),
    )
