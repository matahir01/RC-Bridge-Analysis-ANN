from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.codes.eurocode.combinations import EurocodeFactors, persistent_uls
from rc_bridge.design.eurocode_cracking import (
    CrackedTSectionSLS,
    CrackWidthResult,
    crack_width_ec2_t_section,
    cracked_t_section_sls,
)
from rc_bridge.design.eurocode_deflection import DeflectionResult, ec2_interpolated_udl_deflection
from rc_bridge.design.eurocode_serviceability import (
    UncrackedTSectionSLS,
    uncracked_t_section_sls,
)
from rc_bridge.design.girder_design import GirderDesignResult, design_t_girder_ec2


@dataclass(frozen=True)
class TGirderDesignInput:
    effective_flange_width_m: float
    flange_thickness_m: float
    web_width_m: float
    total_depth_m: float
    effective_depth_m: float
    steel_area_mm2: float
    bar_diameter_mm: float
    bar_spacing_mm: float
    cover_mm: float


@dataclass(frozen=True)
class EurocodeMaterialInput:
    fck_mpa: float
    fyk_mpa: float
    ecm_mpa: float
    fct_eff_mpa: float
    es_mpa: float = 200000.0


@dataclass(frozen=True)
class EurocodeServiceabilityInput:
    service_moment_knm: float
    equivalent_full_span_udl_kn_m: float
    crack_limit_mm: float
    allowable_deflection_mm: float
    creep_coefficient: float = 0.0
    deflection_beta: float = 0.5
    crack_kt: float = 0.4


@dataclass(frozen=True)
class EurocodeTGirderWorkflowResult:
    uls_combination: FactoredCombination
    uls_design: GirderDesignResult
    uncracked_sls: UncrackedTSectionSLS
    cracked_sls: CrackedTSectionSLS
    crack: CrackWidthResult
    deflection: DeflectionResult

    @property
    def g_flexure_knm(self) -> float:
        return self.uls_design.flexure.g_flexure_knm

    @property
    def g_shear_kn(self) -> float:
        return self.uls_design.shear.g_shear_concrete_kn

    @property
    def g_crack_mm(self) -> float:
        return self.crack.g_crack_mm

    @property
    def g_deflection_mm(self) -> float:
        return self.deflection.g_deflection_mm


def run_eurocode_t_girder_case(
    *,
    girder_index: int,
    span_m: float,
    permanent_effects: LoadEffects,
    traffic_effects: LoadEffects,
    section: TGirderDesignInput,
    materials: EurocodeMaterialInput,
    serviceability: EurocodeServiceabilityInput,
    uls_factors: EurocodeFactors | None = None,
    cot_theta: float = 2.0,
) -> EurocodeTGirderWorkflowResult:
    """Run the current deterministic Eurocode T-girder design workflow.

    Traffic and permanent effects supplied here are already per-girder effects.
    This deliberately prevents a provisional transverse distribution method
    from being hidden inside the design workflow. The bridge-level analysis
    layer is responsible for producing those effects and recording its method.

    The deflection branch currently represents an equivalent simply supported
    full-span UDL case. General load-pattern deflection will later use numerical
    curvature integration.
    """
    if span_m <= 0:
        raise ValueError("Span must be positive.")
    if serviceability.service_moment_knm < 0:
        raise ValueError("Service moment cannot be negative.")

    combination = persistent_uls(permanent_effects, traffic_effects, uls_factors)
    uls_design = design_t_girder_ec2(
        girder_index=girder_index,
        design_effects=combination.effects,
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        provided_steel_area_mm2=section.steel_area_mm2,
        fck_mpa=materials.fck_mpa,
        fyk_mpa=materials.fyk_mpa,
        cot_theta=cot_theta,
    )

    modular_ratio = materials.es_mpa / materials.ecm_mpa
    uncracked = uncracked_t_section_sls(
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        total_depth_m=section.total_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        fct_eff_mpa=materials.fct_eff_mpa,
    )
    cracked = cracked_t_section_sls(
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        total_depth_m=section.total_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=serviceability.service_moment_knm,
    )
    crack = crack_width_ec2_t_section(
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        total_depth_m=section.total_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        bar_diameter_mm=section.bar_diameter_mm,
        bar_spacing_mm=section.bar_spacing_mm,
        cover_mm=section.cover_mm,
        service_moment_knm=serviceability.service_moment_knm,
        cracking_moment_knm=uncracked.cracking_moment_knm,
        es_mpa=materials.es_mpa,
        ecm_mpa=materials.ecm_mpa,
        fct_eff_mpa=materials.fct_eff_mpa,
        crack_limit_mm=serviceability.crack_limit_mm,
        kt=serviceability.crack_kt,
    )
    deflection = ec2_interpolated_udl_deflection(
        udl_kn_m=serviceability.equivalent_full_span_udl_kn_m,
        span_m=span_m,
        ecm_mpa=materials.ecm_mpa,
        uncracked_second_moment_mm4=uncracked.second_moment_mm4,
        cracked_second_moment_mm4=cracked.second_moment_mm4,
        cracking_moment_knm=uncracked.cracking_moment_knm,
        allowable_deflection_mm=serviceability.allowable_deflection_mm,
        creep_coefficient=serviceability.creep_coefficient,
        beta=serviceability.deflection_beta,
    )

    return EurocodeTGirderWorkflowResult(
        uls_combination=combination,
        uls_design=uls_design,
        uncracked_sls=uncracked,
        cracked_sls=cracked,
        crack=crack,
        deflection=deflection,
    )
