from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
)
from rc_bridge.core.models import ProjectInput, SectionType
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import LM1GoverningBenchmarkSuite
from rc_bridge.workflow.eurocode_girder import EurocodeMaterialInput
from rc_bridge.workflow.eurocode_layered_girder import (
    EurocodeLayeredGirderWorkflowResult,
    LayeredGirderDesignInput,
    run_eurocode_layered_girder_case,
)
from rc_bridge.workflow.lm1_grillage_search import (
    LM1GirderGoverningEnvelope,
    ProjectNativeLM1GrillageSearchResult,
)
from rc_bridge.workflow.project_bridge import (
    ProjectGirderCombinationSet,
    ProjectServiceabilitySelection,
    SLSCombinationChoice,
    UniformPermanentLoadInput,
    project_eurocode_material_input,
    project_serviceability_from_combinations,
)
from rc_bridge.workflow.project_envelope_detailing import (
    native_lm1_uls_detailing_envelope,
)
from rc_bridge.workflow.project_layered_detailing import (
    ProjectLayeredGirderDetailingResult,
    run_project_layered_girder_detailing,
)
from rc_bridge.workflow.project_layered_envelope_detailing import (
    ProjectLayeredGirderEnvelopeDetailingResult,
    run_project_layered_girder_envelope_detailing,
)
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3FatigueDesignInput,
    NativeFLM3LayeredGirderFatigueResult,
    ProjectNativeFLM3GrillageSearchResult,
    run_project_layered_girder_fatigue_from_native_flm3,
)
from rc_bridge.workflow.project_native_lm1 import (
    native_lm1_service_moment_diagram,
    project_girder_combinations_from_native_lm1,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput

if TYPE_CHECKING:
    from rc_bridge.workflow.project_native_lm1_torsion import (
        NativeLM1MatchedShearTorsionResult,
    )


@dataclass(frozen=True)
class NativeLM1ProjectLayeredGirderResult:
    """Benchmark-gated native-LM1 design for one physical rectangular/T/I girder."""

    section_type: SectionType
    combinations: ProjectGirderCombinationSet
    serviceability: ProjectServiceabilitySelection
    materials: EurocodeMaterialInput
    design: EurocodeLayeredGirderWorkflowResult
    detailing: ProjectLayeredGirderDetailingResult
    envelope_detailing: ProjectLayeredGirderEnvelopeDetailingResult | None
    fatigue: NativeFLM3LayeredGirderFatigueResult | None
    shear_torsion: NativeLM1MatchedShearTorsionResult | None
    traffic_trace: LM1GirderGoverningEnvelope
    benchmark_source: str
    status: str

    @property
    def uls_torsion_knm(self) -> float:
        return self.combinations.persistent_uls.effects.torsion_knm


@dataclass(frozen=True)
class ProjectNativeLM1LayeredGirderDesignSuite:
    """Native-LM1 layered-section results for every physical girder line."""

    girders: tuple[NativeLM1ProjectLayeredGirderResult, ...]
    benchmark_source: str
    search_strategy: str

    def __post_init__(self) -> None:
        if not self.girders:
            raise ValueError("Native LM1 layered design suite requires at least one girder.")

    @property
    def governing_moment_girder_index(self) -> int:
        return max(
            self.girders,
            key=lambda item: item.combinations.persistent_uls.effects.moment_knm,
        ).combinations.girder_index

    @property
    def governing_shear_girder_index(self) -> int:
        return max(
            self.girders,
            key=lambda item: abs(item.combinations.persistent_uls.effects.shear_kn),
        ).combinations.girder_index

    @property
    def governing_torsion_girder_index(self) -> int:
        return max(
            self.girders,
            key=lambda item: abs(item.combinations.persistent_uls.effects.torsion_knm),
        ).combinations.girder_index


    @property
    def governing_fatigue_reinforcement_girder_index(self) -> int | None:
        checked = tuple(item for item in self.girders if item.fatigue is not None)
        if not checked:
            return None
        return max(
            checked,
            key=lambda item: item.fatigue.fatigue.reinforcement.utilization,
        ).combinations.girder_index

    @property
    def governing_fatigue_concrete_girder_index(self) -> int | None:
        checked = tuple(
            item
            for item in self.girders
            if item.fatigue is not None and item.fatigue.fatigue.concrete is not None
        )
        if not checked:
            return None
        return max(
            checked,
            key=lambda item: item.fatigue.fatigue.concrete.utilization,
        ).combinations.girder_index


    @property
    def governing_shear_torsion_interaction_girder_index(self) -> int | None:
        checked = tuple(item for item in self.girders if item.shear_torsion is not None)
        if not checked:
            return None
        return max(
            checked,
            key=lambda item: item.shear_torsion.governing_interaction.interaction.utilization,
        ).combinations.girder_index


def run_project_layered_girder_from_native_lm1(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    girder_index: int,
    section: LayeredGirderDesignInput,
    sls_factors: ServiceabilityPsiFactors,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
    cot_theta: float = 2.0,
    fatigue_search: ProjectNativeFLM3GrillageSearchResult | None = None,
    fatigue_design: NativeFLM3FatigueDesignInput | None = None,
    torsion_cell: TorsionCellInput | None = None,
) -> NativeLM1ProjectLayeredGirderResult:
    """Run the benchmark-gated physical-section simple-span Eurocode path.

    This is the common positive-bending adapter for rectangular, T and I
    non-prestressed precast profiles. It retains the same externally benchmarked
    native LM1 traffic envelope and co-located service-deflection trace as the
    legacy T-only adapter, while section ULS/SLS mechanics come from the actual
    physical concrete layers.
    """
    if project.geometry.girder_profile is None:
        raise ValueError(
            "Layered native LM1 design requires a complete physical girder profile."
        )
    if (fatigue_search is None) != (fatigue_design is None):
        raise ValueError(
            "fatigue_search and fatigue_design must either both be supplied or both be omitted."
        )
    combinations = project_girder_combinations_from_native_lm1(
        project,
        search=search,
        benchmark_suite=benchmark_suite,
        benchmark_report=benchmark_report,
        girder_index=girder_index,
        sls_factors=sls_factors,
        additional_permanent=additional_permanent,
        uls_factors=uls_factors,
    )
    span_m = float(project.geometry.span_lengths_m[0])
    materials = project_eurocode_material_input(
        project,
        fct_eff_mpa=fct_eff_mpa,
        es_mpa=es_mpa,
    )
    deflection_trace = native_lm1_service_moment_diagram(
        project,
        search,
        combinations=combinations,
        deflection_combination=deflection_combination,
        span_m=span_m,
        benchmark_source=benchmark_report.source_name,
        additional_permanent=additional_permanent,
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
        deflection_moment_diagram=(
            None if deflection_trace is None else deflection_trace[0]
        ),
        deflection_service_moment_knm=(
            None if deflection_trace is None else deflection_trace[1]
        ),
    )
    design = run_eurocode_layered_girder_case(
        project,
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
    detailing = run_project_layered_girder_detailing(
        project,
        section=section,
        design=design,
    )
    envelope_detailing: ProjectLayeredGirderEnvelopeDetailingResult | None = None
    if all(hasattr(case, "model") and hasattr(case, "analysis") for case in search.cases):
        detailing_envelope = native_lm1_uls_detailing_envelope(
            project,
            search=search,
            girder_index=girder_index,
            additional_permanent=additional_permanent,
            uls_factors=uls_factors,
        )
        envelope_detailing = run_project_layered_girder_envelope_detailing(
            project,
            section=section,
            envelope=detailing_envelope,
            cot_theta=cot_theta,
        )

    fatigue: NativeFLM3LayeredGirderFatigueResult | None = None
    if fatigue_search is not None and fatigue_design is not None:
        fatigue = run_project_layered_girder_fatigue_from_native_flm3(
            project,
            search=fatigue_search,
            girder_index=girder_index,
            section=section,
            lambda_s=fatigue_design.lambda_s,
            characteristic_fatigue_strength_mpa=(
                fatigue_design.characteristic_fatigue_strength_mpa
            ),
            additional_permanent=additional_permanent,
            gamma_s_fat=fatigue_design.gamma_s_fat,
            phi_fat=fatigue_design.phi_fat,
            es_mpa=es_mpa,
            check_concrete=fatigue_design.check_concrete,
            concrete_gamma_c=fatigue_design.concrete_gamma_c,
            concrete_alpha_cc=fatigue_design.concrete_alpha_cc,
            concrete_k1=fatigue_design.concrete_k1,
            concrete_beta_cc_t0=fatigue_design.concrete_beta_cc_t0,
        )
    shear_torsion: NativeLM1MatchedShearTorsionResult | None = None
    if torsion_cell is not None:
        from rc_bridge.workflow.project_native_lm1_torsion import (
            check_project_native_lm1_matched_shear_torsion,
        )

        shear_torsion = check_project_native_lm1_matched_shear_torsion(
            project,
            search=search,
            benchmark_suite=benchmark_suite,
            benchmark_report=benchmark_report,
            girder_index=girder_index,
            section=section,
            torsion_cell=torsion_cell,
            additional_permanent=additional_permanent,
            uls_factors=uls_factors,
            cot_theta=cot_theta,
        )
    trace = next(item for item in search.girders if item.girder_index == girder_index)
    return NativeLM1ProjectLayeredGirderResult(
        section_type=project.geometry.section_type,
        combinations=combinations,
        serviceability=serviceability,
        materials=materials,
        design=design,
        detailing=detailing,
        envelope_detailing=envelope_detailing,
        fatigue=fatigue,
        shear_torsion=shear_torsion,
        traffic_trace=trace,
        benchmark_source=benchmark_report.source_name,
        status=(
            "Externally benchmark-gated native LM1 simple-span EC2 design using the "
            "physical rectangular/T/I layered section for flexure, shear, cracking, "
            "deflection and practical reinforcement quantity/detail selection. Generic "
            "physical native searches also produce envelope-driven bar-curtailment and "
            "link-spacing zones. When an explicit torsion cell is supplied, matched co-located "
            "V-T interaction is checked. "
            "When a dedicated FLM3 search/design input is supplied, layered fatigue is "
            "evaluated without substituting LM1."
        ),
    )


def run_project_all_layered_girders_from_native_lm1(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    sections_by_girder: dict[int, LayeredGirderDesignInput],
    sls_factors: ServiceabilityPsiFactors,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    additional_permanent_by_girder: dict[int, UniformPermanentLoadInput] | None = None,
    uls_factors: EurocodeFactors | None = None,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
    cot_theta: float = 2.0,
    fatigue_search: ProjectNativeFLM3GrillageSearchResult | None = None,
    fatigue_design: NativeFLM3FatigueDesignInput | None = None,
    torsion_cells_by_girder: dict[int, TorsionCellInput] | None = None,
) -> ProjectNativeLM1LayeredGirderDesignSuite:
    """Run the physical rectangular/T/I native-LM1 path for all girder lines."""
    girder_count = int(project.geometry.girder_count)
    required = set(range(1, girder_count + 1))
    if set(sections_by_girder) != required:
        raise ValueError(
            "sections_by_girder must contain exactly one layered section for every girder."
        )
    additional = additional_permanent_by_girder or {}
    torsion_cells = torsion_cells_by_girder or {}
    unexpected = set(additional) - required
    if unexpected:
        raise ValueError(
            "additional_permanent_by_girder contains unknown girder indices: "
            + ", ".join(str(value) for value in sorted(unexpected))
        )
    unexpected_torsion = set(torsion_cells) - required
    if unexpected_torsion:
        raise ValueError(
            "torsion_cells_by_girder contains unknown girder indices: "
            + ", ".join(str(value) for value in sorted(unexpected_torsion))
        )
    results = tuple(
        run_project_layered_girder_from_native_lm1(
            project,
            search=search,
            benchmark_suite=benchmark_suite,
            benchmark_report=benchmark_report,
            girder_index=girder_index,
            section=sections_by_girder[girder_index],
            sls_factors=sls_factors,
            crack_combination=crack_combination,
            deflection_combination=deflection_combination,
            crack_limit_mm=crack_limit_mm,
            allowable_deflection_mm=allowable_deflection_mm,
            additional_permanent=additional.get(girder_index),
            uls_factors=uls_factors,
            fct_eff_mpa=fct_eff_mpa,
            es_mpa=es_mpa,
            creep_coefficient=creep_coefficient,
            deflection_beta=deflection_beta,
            crack_kt=crack_kt,
            cot_theta=cot_theta,
            fatigue_search=fatigue_search,
            fatigue_design=fatigue_design,
            torsion_cell=torsion_cells.get(girder_index),
        )
        for girder_index in range(1, girder_count + 1)
    )
    return ProjectNativeLM1LayeredGirderDesignSuite(
        girders=results,
        benchmark_source=benchmark_report.source_name,
        search_strategy=search.search_strategy,
    )
