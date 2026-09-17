from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rc_bridge.analysis.lane_distribution import (
    equal_lane_distribution,
    equal_remaining_area_distribution,
)
from rc_bridge.analysis.loads import deck_self_weight_per_girder_kn_m
from rc_bridge.analysis.simple_span import udl_simple_span
from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.eurocode_bridge_traffic import (
    BridgeLM1TrafficResult,
    run_simple_span_lm1_bridge_traffic,
)
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeServiceabilityInput,
    EurocodeTGirderWorkflowResult,
    TGirderDesignInput,
    run_eurocode_t_girder_case,
)


@dataclass(frozen=True)
class UniformPermanentLoadInput:
    """Explicit additional characteristic permanent line loads on one girder."""

    girder_self_weight_kn_m: float = 0.0
    surfacing_and_finishes_kn_m: float = 0.0
    assigned_barrier_and_services_kn_m: float = 0.0
    other_kn_m: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.girder_self_weight_kn_m,
            self.surfacing_and_finishes_kn_m,
            self.assigned_barrier_and_services_kn_m,
            self.other_kn_m,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("Permanent line-load components cannot be negative.")

    @property
    def total_additional_kn_m(self) -> float:
        return (
            self.girder_self_weight_kn_m
            + self.surfacing_and_finishes_kn_m
            + self.assigned_barrier_and_services_kn_m
            + self.other_kn_m
        )


@dataclass(frozen=True)
class ProjectGirderCombinationSet:
    girder_index: int
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    persistent_uls: FactoredCombination
    characteristic_sls: FactoredCombination
    frequent_sls: FactoredCombination
    quasi_permanent_sls: FactoredCombination
    traffic_distribution_method: str


class SLSCombinationChoice(str, Enum):
    CHARACTERISTIC = "characteristic"
    FREQUENT = "frequent"
    QUASI_PERMANENT = "quasi_permanent"


@dataclass(frozen=True)
class ProjectServiceabilitySelection:
    input: EurocodeServiceabilityInput
    crack_combination_name: str
    deflection_combination_name: str
    deflection_method: str = "equivalent full-span UDL from selected SLS maximum moment"


@dataclass(frozen=True)
class ProjectTGirderVerificationResult:
    combinations: ProjectGirderCombinationSet
    serviceability: ProjectServiceabilitySelection
    materials: EurocodeMaterialInput
    design: EurocodeTGirderWorkflowResult


def project_eurocode_material_input(
    project: ProjectInput,
    *,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
) -> EurocodeMaterialInput:
    """Build the girder-workflow material input from project properties.

    Ecm and the default fct,eff are derived from first-generation EC2 concrete
    properties. Supply ``fct_eff_mpa`` explicitly for early-age cracking or any
    other stage where the effective tensile strength differs from 28-day fctm.
    A project elastic-modulus override takes precedence over the EC2 estimate.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Eurocode material derivation requires a Eurocode project.")
    if fct_eff_mpa is not None and fct_eff_mpa <= 0.0:
        raise ValueError("fct_eff_mpa must be positive when supplied.")
    if es_mpa <= 0.0:
        raise ValueError("es_mpa must be positive.")

    fck_mpa = float(project.materials.fck_mpa)
    properties = concrete_properties_ec2(fck_mpa)
    ecm_mpa = (
        float(project.materials.elastic_modulus_mpa)
        if project.materials.elastic_modulus_mpa is not None
        else properties.ecm_mpa
    )
    return EurocodeMaterialInput(
        fck_mpa=fck_mpa,
        fyk_mpa=float(project.materials.fyk_mpa),
        ecm_mpa=ecm_mpa,
        fct_eff_mpa=fct_eff_mpa or properties.fctm_mpa,
        es_mpa=es_mpa,
    )


def internal_girder_deck_self_weight_kn_m(project: ProjectInput) -> float:
    """Physical deck self-weight on an internal girder tributary width.

    This includes both precast false slab and in-situ slab because both are
    permanent weight, regardless of whether the false slab participates in the
    composite compression flange.
    """
    geometry = project.geometry
    return deck_self_weight_per_girder_kn_m(
        deck_thickness_m=geometry.physical_deck_depth_m,
        girder_spacing_m=float(geometry.girder_spacing_m),
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def internal_girder_characteristic_permanent_effects(
    project: ProjectInput,
    *,
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
) -> LoadEffects:
    """Return simple-span characteristic G effects for an internal girder.

    Deck self-weight is derived from the physical deck build-up. Girder own
    weight, surfacing, barriers/services, and other permanent loads are explicit
    inputs until the corresponding section/load models are defined. Edge-girder
    deck tributary width must be handled separately.
    """
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This permanent-load adapter currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    deck_kn_m = internal_girder_deck_self_weight_kn_m(project)
    extra_kn_m = (additional or UniformPermanentLoadInput()).total_additional_kn_m
    result = udl_simple_span(span_m, deck_kn_m + extra_kn_m)
    return LoadEffects(
        moment_knm=result.max_moment_knm,
        shear_kn=result.max_shear_kn,
    )


def run_project_lm1_equal_share_verification(
    project: ProjectInput,
    *,
    span_index: int = 0,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> BridgeLM1TrafficResult:
    """Run the current simple-span LM1 benchmark with equal transverse shares.

    This is intentionally labelled verification-only. It checks longitudinal
    LM1 mechanics, bridge geometry plumbing, and conservation of total traffic
    effects. It is not the production transverse-distribution solution; that
    must use validated analytical factors or imported grillage results.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("This verification workflow currently supports Eurocode projects only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This verification workflow currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    carriageway_width_m = float(project.geometry.carriageway_width_m)
    girder_count = int(project.geometry.girder_count)
    layout = notional_lane_layout(carriageway_width_m)

    lane_distributions = [
        equal_lane_distribution(lane_number, girder_count)
        for lane_number in range(1, layout.lane_count + 1)
    ]
    remaining_distribution = (
        equal_remaining_area_distribution(girder_count)
        if layout.remaining_width_m > 0.0
        else None
    )

    return run_simple_span_lm1_bridge_traffic(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        lane_distributions=lane_distributions,
        remaining_area_distribution=remaining_distribution,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )


def project_internal_girder_combinations_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    sls_factors: ServiceabilityPsiFactors,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> ProjectGirderCombinationSet:
    """Assemble Gk/Qk and Eurocode ULS/SLS effects for an internal girder.

    The traffic branch intentionally uses the equal-share verification model.
    Production design must replace it with validated analytical or imported
    grillage distribution before the solver is marked verified for ANN use.
    """
    girder_count = int(project.geometry.girder_count)
    if not 2 <= girder_index <= girder_count - 1:
        raise ValueError(
            "This helper is for internal girders only; edge-girder permanent-load "
            "tributary widths must be modelled separately."
        )

    permanent = internal_girder_characteristic_permanent_effects(
        project,
        span_index=span_index,
        additional=additional_permanent,
    )
    traffic_result = run_project_lm1_equal_share_verification(
        project,
        span_index=span_index,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    traffic_item = traffic_result.girder_effects[girder_index - 1]
    traffic = LoadEffects(
        moment_knm=traffic_item.moment_knm,
        shear_kn=traffic_item.shear_kn,
    )

    return ProjectGirderCombinationSet(
        girder_index=girder_index,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        persistent_uls=persistent_uls(permanent, traffic, uls_factors),
        characteristic_sls=characteristic_sls(permanent, traffic),
        frequent_sls=frequent_sls(permanent, traffic, sls_factors),
        quasi_permanent_sls=quasi_permanent_sls(permanent, traffic, sls_factors),
        traffic_distribution_method=traffic_item.method,
    )


def _select_sls_combination(
    combinations: ProjectGirderCombinationSet,
    choice: SLSCombinationChoice,
) -> FactoredCombination:
    if choice == SLSCombinationChoice.CHARACTERISTIC:
        return combinations.characteristic_sls
    if choice == SLSCombinationChoice.FREQUENT:
        return combinations.frequent_sls
    if choice == SLSCombinationChoice.QUASI_PERMANENT:
        return combinations.quasi_permanent_sls
    raise ValueError(f"Unsupported SLS combination choice: {choice}")


def project_serviceability_from_combinations(
    combinations: ProjectGirderCombinationSet,
    *,
    span_m: float,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
) -> ProjectServiceabilitySelection:
    """Build current SLS inputs from explicitly selected EN 1990 combinations.

    Deflection still uses the current solver's equivalent full-span UDL model.
    The equivalent line load is back-calculated from the selected SLS maximum
    sagging moment as w_eq = 8M/L^2. This approximation remains visible in the
    returned method label and will later be replaced by curvature integration.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")
    if crack_limit_mm <= 0.0 or allowable_deflection_mm <= 0.0:
        raise ValueError("SLS limits must be positive.")

    crack_case = _select_sls_combination(combinations, crack_combination)
    deflection_case = _select_sls_combination(combinations, deflection_combination)
    equivalent_udl_kn_m = 8.0 * deflection_case.effects.moment_knm / span_m**2

    return ProjectServiceabilitySelection(
        input=EurocodeServiceabilityInput(
            service_moment_knm=crack_case.effects.moment_knm,
            equivalent_full_span_udl_kn_m=equivalent_udl_kn_m,
            crack_limit_mm=crack_limit_mm,
            allowable_deflection_mm=allowable_deflection_mm,
            creep_coefficient=creep_coefficient,
            deflection_beta=deflection_beta,
            crack_kt=crack_kt,
        ),
        crack_combination_name=crack_case.name,
        deflection_combination_name=deflection_case.name,
    )


def run_project_internal_t_girder_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    section: TGirderDesignInput,
    sls_factors: ServiceabilityPsiFactors,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
    cot_theta: float = 2.0,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> ProjectTGirderVerificationResult:
    """Run the current project-to-design path for an internal T-girder.

    This remains a verification workflow because traffic is still distributed
    equally between girders. It is suitable for plumbing and hand-check
    validation, not for production bridge design or ANN data generation until
    transverse distribution is replaced and independently verified.
    """
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    expected_total_depth_m = (
        float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    )
    if abs(section.total_depth_m - expected_total_depth_m) > 1e-9:
        raise ValueError(
            "T-girder total depth must match project girder depth plus physical deck depth."
        )

    combinations = project_internal_girder_combinations_verification(
        project,
        girder_index=girder_index,
        sls_factors=sls_factors,
        span_index=span_index,
        additional_permanent=additional_permanent,
        uls_factors=uls_factors,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    materials = project_eurocode_material_input(
        project,
        fct_eff_mpa=fct_eff_mpa,
        es_mpa=es_mpa,
    )
    serviceability = project_serviceability_from_combinations(
        combinations,
        span_m=span_m,
        crack_combination=crack_combination,
        deflection_combination=deflection_combination,
        crack_limit_mm=crack_limit_mm,
        allowable_deflection_mm=allowable_deflection_mm,
        creep_coefficient=creep_coefficient,
        deflection_beta=deflection_beta,
        crack_kt=crack_kt,
    )
    design = run_eurocode_t_girder_case(
        girder_index=girder_index,
        span_m=span_m,
        permanent_effects=combinations.permanent_characteristic,
        traffic_effects=combinations.traffic_characteristic,
        section=section,
        materials=materials,
        serviceability=serviceability.input,
        uls_factors=uls_factors,
        cot_theta=cot_theta,
    )

    return ProjectTGirderVerificationResult(
        combinations=combinations,
        serviceability=serviceability,
        materials=materials,
        design=design,
    )
