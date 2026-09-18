from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.physical_sections import (
    ConcreteSectionLayer,
    composite_concrete_layers,
    composite_section_total_depth_m,
    girder_web_width_m,
)
from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.codes.eurocode.combinations import EurocodeFactors, persistent_uls
from rc_bridge.core.models import ProjectInput, SectionType
from rc_bridge.design.eurocode_deflection import (
    DeflectionResult,
    ec2_interpolated_moment_diagram_deflection,
    ec2_interpolated_udl_deflection,
)
from rc_bridge.design.eurocode_demand import (
    FlexuralDemandResult,
    check_shear,
)
from rc_bridge.design.eurocode_layered_section import (
    LayeredCrackedSLS,
    LayeredCrackWidthResult,
    LayeredUncrackedSLS,
    crack_width_layered_section,
    cracked_layered_section_sls,
    layered_singly_reinforced_resistance,
    required_tension_steel_layered,
    uncracked_layered_section_sls,
)
from rc_bridge.design.eurocode_shear import (
    ProvidedShearResistanceResult,
    provided_vertical_shear_resistance,
)
from rc_bridge.design.girder_design import GirderDesignResult
from rc_bridge.research.limit_states import flexural_limit_state
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeServiceabilityInput,
)


@dataclass(frozen=True)
class LayeredGirderDesignInput:
    """Positive-bending reinforcement/detail inputs for a physical girder profile.

    ``composite_slab_width_m`` is deliberately explicit. It is the longitudinal
    compression slab width admitted to section resistance/service analysis and
    is not silently equated to grillage tributary width or a code effective width.
    """

    composite_slab_width_m: float
    effective_depth_m: float
    steel_area_mm2: float
    bar_diameter_mm: float
    bar_spacing_mm: float
    cover_mm: float
    provided_shear_asw_per_s_mm2_per_m: float | None = None

    def __post_init__(self) -> None:
        values = (
            self.composite_slab_width_m,
            self.effective_depth_m,
            self.steel_area_mm2,
            self.bar_diameter_mm,
            self.bar_spacing_mm,
            self.cover_mm,
        )
        if any(value <= 0.0 for value in values):
            raise ValueError("Layered girder geometry and reinforcement inputs must be positive.")
        if (
            self.provided_shear_asw_per_s_mm2_per_m is not None
            and self.provided_shear_asw_per_s_mm2_per_m < 0.0
        ):
            raise ValueError("Provided shear A_sw/s cannot be negative.")


@dataclass(frozen=True)
class EurocodeLayeredGirderWorkflowResult:
    section_type: SectionType
    concrete_layers: tuple[ConcreteSectionLayer, ...]
    uls_combination: FactoredCombination
    uls_design: GirderDesignResult
    uncracked_sls: LayeredUncrackedSLS
    cracked_sls: LayeredCrackedSLS
    crack: LayeredCrackWidthResult
    deflection: DeflectionResult
    provided_shear: ProvidedShearResistanceResult | None
    status: str

    @property
    def g_flexure_knm(self) -> float:
        return self.uls_design.flexure.g_flexure_knm

    @property
    def g_shear_kn(self) -> float:
        ved_kn = abs(self.uls_design.design_effects.shear_kn)
        if (
            ved_kn > self.uls_design.shear.concrete_resistance_kn
            and self.provided_shear is not None
        ):
            return self.provided_shear.governing_resistance_kn - ved_kn
        return self.uls_design.shear.g_shear_concrete_kn

    @property
    def shear_utilization(self) -> float:
        ved_kn = abs(self.uls_design.design_effects.shear_kn)
        if (
            ved_kn > self.uls_design.shear.concrete_resistance_kn
            and self.provided_shear is not None
        ):
            resistance = self.provided_shear.governing_resistance_kn
            return ved_kn / resistance if resistance > 0.0 else float("inf")
        return self.uls_design.shear.utilization_concrete_only

    @property
    def g_crack_mm(self) -> float:
        return self.crack.crack_limit_mm - self.crack.crack_width_mm

    @property
    def g_deflection_mm(self) -> float:
        return self.deflection.g_deflection_mm


def run_eurocode_layered_girder_case(
    project: ProjectInput,
    *,
    girder_index: int,
    span_m: float,
    permanent_effects: LoadEffects,
    traffic_effects: LoadEffects,
    section: LayeredGirderDesignInput,
    materials: EurocodeMaterialInput,
    serviceability: EurocodeServiceabilityInput,
    uls_factors: EurocodeFactors | None = None,
    cot_theta: float = 2.0,
) -> EurocodeLayeredGirderWorkflowResult:
    """Run positive-bending EC2 ULS/SLS for rectangular, T or I profiles.

    The concrete section is built from the project's physical deck construction
    and precast profile. Nonparticipating deck layers remain absent from section
    stiffness/resistance rather than being collapsed into an equivalent T shape.
    """
    if girder_index <= 0:
        raise ValueError("girder_index must be positive.")
    if span_m <= 0.0:
        raise ValueError("Span must be positive.")
    total_depth_m = composite_section_total_depth_m(project.geometry)
    if section.effective_depth_m >= total_depth_m:
        raise ValueError("Effective depth must lie inside the physical composite section.")

    layers = composite_concrete_layers(
        project.geometry,
        slab_width_m=section.composite_slab_width_m,
    )
    combination = persistent_uls(permanent_effects, traffic_effects, uls_factors)
    med_knm = combination.effects.moment_knm
    if med_knm < -1.0e-9:
        raise ValueError(
            "Layered simple-span positive-bending workflow cannot design a hogging ULS moment."
        )
    med_knm = max(med_knm, 0.0)
    required_steel = required_tension_steel_layered(
        med_knm=med_knm,
        layers=layers,
        effective_depth_m=section.effective_depth_m,
        fck_mpa=materials.fck_mpa,
        fyk_mpa=materials.fyk_mpa,
    )
    resistance = layered_singly_reinforced_resistance(
        layers=layers,
        effective_depth_m=section.effective_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        fck_mpa=materials.fck_mpa,
        fyk_mpa=materials.fyk_mpa,
    )
    utilization = (
        med_knm / resistance.resistance_knm
        if resistance.resistance_knm > 0.0
        else float("inf")
    )
    flexure = FlexuralDemandResult(
        required_steel_area_mm2=required_steel,
        provided_steel_area_mm2=section.steel_area_mm2,
        resistance_knm=resistance.resistance_knm,
        utilization=utilization,
        g_flexure_knm=flexural_limit_state(resistance.resistance_knm, med_knm),
        status=resistance.status,
    )

    web_width_m = girder_web_width_m(project.geometry)
    shear = check_shear(
        ved_kn=abs(combination.effects.shear_kn),
        web_width_m=web_width_m,
        effective_depth_m=section.effective_depth_m,
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        fck_mpa=materials.fck_mpa,
        fyk_mpa=materials.fyk_mpa,
        cot_theta=cot_theta,
    )
    uls_design = GirderDesignResult(
        girder_index=girder_index,
        design_effects=combination.effects,
        flexure=flexure,
        shear=shear,
    )

    modular_ratio = materials.es_mpa / materials.ecm_mpa
    uncracked = uncracked_layered_section_sls(
        layers=layers,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        fct_eff_mpa=materials.fct_eff_mpa,
    )
    cracked = cracked_layered_section_sls(
        layers=layers,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=serviceability.service_moment_knm,
    )
    crack = crack_width_layered_section(
        layers=layers,
        total_depth_m=total_depth_m,
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

    provided_shear = None
    if section.provided_shear_asw_per_s_mm2_per_m is not None:
        provided_shear = provided_vertical_shear_resistance(
            provided_asw_per_s_mm2_per_m=section.provided_shear_asw_per_s_mm2_per_m,
            web_width_m=web_width_m,
            effective_depth_m=section.effective_depth_m,
            fck_mpa=materials.fck_mpa,
            fyk_mpa=materials.fyk_mpa,
            cot_theta=cot_theta,
        )

    if serviceability.deflection_moment_diagram is not None:
        deflection_moment = serviceability.deflection_service_moment_knm
        if deflection_moment is None:
            deflection_moment = max(
                abs(value)
                for value in serviceability.deflection_moment_diagram.moments_knm
            )
        deflection = ec2_interpolated_moment_diagram_deflection(
            diagram=serviceability.deflection_moment_diagram,
            ecm_mpa=materials.ecm_mpa,
            uncracked_second_moment_mm4=uncracked.second_moment_mm4,
            cracked_second_moment_mm4=cracked.second_moment_mm4,
            service_moment_knm=deflection_moment,
            cracking_moment_knm=uncracked.cracking_moment_knm,
            allowable_deflection_mm=serviceability.allowable_deflection_mm,
            creep_coefficient=serviceability.creep_coefficient,
            beta=serviceability.deflection_beta,
        )
    else:
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

    return EurocodeLayeredGirderWorkflowResult(
        section_type=project.geometry.section_type,
        concrete_layers=layers,
        uls_combination=combination,
        uls_design=uls_design,
        uncracked_sls=uncracked,
        cracked_sls=cracked,
        crack=crack,
        deflection=deflection,
        provided_shear=provided_shear,
        status=(
            "EC2 positive-bending layered physical-section workflow; rectangular/T/I "
            "precast profile geometry and participating deck layers retained explicitly"
        ),
    )
