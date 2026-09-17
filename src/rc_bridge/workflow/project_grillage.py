from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    ImportedGrillageEnvelope,
)
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.workflow.eurocode_girder import (
    EurocodeTGirderWorkflowResult,
    TGirderDesignInput,
    run_eurocode_t_girder_case,
)
from rc_bridge.workflow.project_bridge import (
    ProjectGirderCombinationSet,
    ProjectServiceabilitySelection,
    SLSCombinationChoice,
    UniformPermanentLoadInput,
    internal_girder_characteristic_permanent_effects,
    project_eurocode_material_input,
    project_serviceability_from_combinations,
)


@dataclass(frozen=True)
class ImportedProjectTGirderResult:
    source_metadata: GrillageImportMetadata
    combinations: ProjectGirderCombinationSet
    serviceability: ProjectServiceabilitySelection
    design: EurocodeTGirderWorkflowResult

    @property
    def imported_uls_torsion_knm(self) -> float:
        """Factored imported torsion retained for the future torsion check."""
        return self.combinations.persistent_uls.effects.torsion_knm


def project_internal_girder_combinations_from_grillage(
    project: ProjectInput,
    *,
    grillage: ImportedGrillageEnvelope,
    girder_index: int,
    sls_factors: ServiceabilityPsiFactors,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
) -> ProjectGirderCombinationSet:
    """Combine project Gk with imported per-girder characteristic traffic effects.

    The imported grillage envelope is treated as the characteristic traffic
    action Qk for the named source load case. The import must contain exactly
    the project's girder count. Permanent-load calculation is currently the
    internal-girder tributary-width model, so edge girders remain excluded.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("The imported-grillage workflow currently supports Eurocode only.")

    girder_count = int(project.geometry.girder_count)
    if grillage.girder_count != girder_count:
        raise ValueError(
            "Imported grillage girder count does not match the project: "
            f"{grillage.girder_count} != {girder_count}."
        )
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
    traffic = grillage.effect_for_girder(girder_index)
    method = (
        f"{grillage.metadata.method}:"
        f"{grillage.metadata.source_software}:"
        f"{grillage.metadata.load_case}"
    )

    return ProjectGirderCombinationSet(
        girder_index=girder_index,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        persistent_uls=persistent_uls(permanent, traffic, uls_factors),
        characteristic_sls=characteristic_sls(permanent, traffic),
        frequent_sls=frequent_sls(permanent, traffic, sls_factors),
        quasi_permanent_sls=quasi_permanent_sls(permanent, traffic, sls_factors),
        traffic_distribution_method=method,
    )


def run_project_internal_t_girder_from_grillage(
    project: ProjectInput,
    *,
    grillage: ImportedGrillageEnvelope,
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
) -> ImportedProjectTGirderResult:
    """Run the project T-girder ULS/SLS path using imported grillage traffic.

    Flexure, shear, cracking, and the current equivalent-UDL deflection checks
    are evaluated. Imported torsion is retained in the EN 1990 combinations but
    no torsional resistance check is performed yet; callers must not interpret
    this result as a completed torsion verification.
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

    combinations = project_internal_girder_combinations_from_grillage(
        project,
        grillage=grillage,
        girder_index=girder_index,
        sls_factors=sls_factors,
        span_index=span_index,
        additional_permanent=additional_permanent,
        uls_factors=uls_factors,
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

    return ImportedProjectTGirderResult(
        source_metadata=grillage.metadata,
        combinations=combinations,
        serviceability=serviceability,
        design=design,
    )
