from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    ImportedGirderEffect,
    ImportedGrillageEnvelope,
)
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_deflection import SimpleSpanMomentDiagram
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import LM1GoverningBenchmarkSuite
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeTGirderWorkflowResult,
    TGirderDesignInput,
    run_eurocode_t_girder_case,
)
from rc_bridge.workflow.lm1_grillage_search import (
    LM1GirderGoverningEnvelope,
    ProjectNativeLM1GrillageSearchResult,
    native_lm1_girder_moment_diagram,
)
from rc_bridge.workflow.project_bridge import (
    ProjectGirderCombinationSet,
    ProjectServiceabilitySelection,
    SLSCombinationChoice,
    UniformPermanentLoadInput,
    girder_characteristic_permanent_effects,
    girder_permanent_moments_knm_at,
    project_eurocode_material_input,
    project_serviceability_from_combinations,
)
from rc_bridge.workflow.project_detailing import (
    ProjectTGirderDetailingResult,
    run_project_t_girder_detailing,
)
from rc_bridge.workflow.project_envelope_detailing import (
    ProjectTGirderEnvelopeDetailingResult,
    native_lm1_uls_detailing_envelope,
    run_project_t_girder_envelope_detailing,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput

if TYPE_CHECKING:
    from rc_bridge.workflow.project_native_lm1_torsion import (
        NativeLM1MatchedShearTorsionResult,
    )


@dataclass(frozen=True)
class NativeLM1ProjectTGirderResult:
    """Eurocode T-girder design driven by the externally benchmarked native LM1 envelope."""

    combinations: ProjectGirderCombinationSet
    serviceability: ProjectServiceabilitySelection
    materials: EurocodeMaterialInput
    design: EurocodeTGirderWorkflowResult
    detailing: ProjectTGirderDetailingResult
    envelope_detailing: ProjectTGirderEnvelopeDetailingResult | None
    shear_torsion: NativeLM1MatchedShearTorsionResult | None
    traffic_trace: LM1GirderGoverningEnvelope
    benchmark_source: str
    status: str

    @property
    def uls_torsion_knm(self) -> float:
        return self.combinations.persistent_uls.effects.torsion_knm


@dataclass(frozen=True)
class ProjectNativeLM1TGirderDesignSuite:
    """Externally benchmarked native-LM1 design results for every project girder."""

    girders: tuple[NativeLM1ProjectTGirderResult, ...]
    benchmark_source: str
    search_strategy: str

    def __post_init__(self) -> None:
        if not self.girders:
            raise ValueError("Native LM1 design suite requires at least one girder result.")

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
    def governing_shear_torsion_interaction_girder_index(self) -> int | None:
        checked = tuple(item for item in self.girders if item.shear_torsion is not None)
        if not checked:
            return None
        return max(
            checked,
            key=lambda item: item.shear_torsion.governing_interaction.interaction.utilization,
        ).combinations.girder_index


def _require_simple_span_native_design_project(project: ProjectInput) -> None:
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native LM1 girder design currently supports Eurocode projects only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "This native LM1 girder design adapter is the simple-span path; "
            "continuous design must use the signed continuous-envelope workflow."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError(
            "The current native LM1 simple-span design adapter requires exactly one span."
        )


def require_native_lm1_external_benchmark(
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    required_case_ids: tuple[int, ...] | None = None,
) -> None:
    """Require passing external evidence for native LM1 cases used by design.

    The independent M/V/T governing case set is required by default. Callers may
    require additional interaction cases. A benchmark suite may contain extra
    cases from the same current native search, but it cannot omit any required
    case or substitute a case object from another grid/load search.
    """
    if not benchmark_report.passes:
        failed = ", ".join(str(value) for value in benchmark_report.failed_case_ids)
        missing = ", ".join(str(value) for value in benchmark_report.missing_case_ids)
        detail = failed or missing or "benchmark completeness/tolerance requirements"
        raise RuntimeError(
            "Native LM1 production design remains locked because the external "
            f"benchmark has not passed: {detail}."
        )

    required_ids = (
        set(search.governing_case_ids)
        if required_case_ids is None
        else set(required_case_ids)
    )
    required_ids.update(search.governing_case_ids)
    search_by_id = {item.placement.case_id: item for item in search.cases}
    search_ids = set(search_by_id)
    invalid_required = sorted(required_ids - search_ids)
    if invalid_required:
        raise RuntimeError(
            "Native LM1 production design requested benchmark cases outside the "
            "current search: " + ", ".join(str(value) for value in invalid_required)
        )

    suite_by_id = {item.case_id: item for item in benchmark_suite.cases}
    suite_ids = set(suite_by_id)
    report_ids = {item.case_id for item in benchmark_report.case_reports}
    if suite_ids != report_ids:
        raise RuntimeError(
            "Native LM1 production design remains locked because benchmark suite "
            "and report case IDs do not match."
        )
    unexpected = sorted(suite_ids - search_ids)
    if unexpected:
        raise RuntimeError(
            "Native LM1 production design remains locked because benchmark cases "
            "are not part of the current native search: "
            + ", ".join(str(value) for value in unexpected)
        )
    missing_required = sorted(required_ids - suite_ids)
    if missing_required:
        raise RuntimeError(
            "Native LM1 production design remains locked because required external "
            "benchmark cases are missing: "
            + ", ".join(str(value) for value in missing_required)
        )

    for case_id in sorted(suite_ids):
        if suite_by_id[case_id].case != search_by_id[case_id]:
            raise RuntimeError(
                "Native LM1 production design remains locked because benchmark case "
                f"{case_id} was generated from a different native search case."
            )


def native_lm1_characteristic_envelope(
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
) -> ImportedGrillageEnvelope:
    """Convert verified independent native M/V/T maxima into a design-compatible Qk envelope."""
    require_native_lm1_external_benchmark(
        search,
        benchmark_suite=benchmark_suite,
        benchmark_report=benchmark_report,
    )
    if not search.girders:
        raise ValueError("Native LM1 search contains no girder envelopes.")

    effects = tuple(
        ImportedGirderEffect(
            girder_index=item.girder_index,
            effects=LoadEffects(
                moment_knm=item.moment_knm.value,
                shear_kn=item.shear_kn.value,
                torsion_knm=item.torsion_knm.value,
            ),
        )
        for item in search.girders
    )
    return ImportedGrillageEnvelope(
        metadata=GrillageImportMetadata(
            source_software="RC-Bridge native vertical grillage",
            model_name="Automated EN 1991-2 LM1 governing search",
            load_case="LM1 characteristic independent per-girder M/V/T envelope",
            method=(
                "externally_benchmarked_native_lm1:"
                + benchmark_report.source_name
                + ":"
                + search.search_strategy
            ),
        ),
        girder_effects=effects,
    )


def project_girder_combinations_from_native_lm1(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    girder_index: int,
    sls_factors: ServiceabilityPsiFactors,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
) -> ProjectGirderCombinationSet:
    """Assemble EN 1990 combinations from benchmarked native LM1 per-girder effects."""
    _require_simple_span_native_design_project(project)
    envelope = native_lm1_characteristic_envelope(
        search,
        benchmark_suite=benchmark_suite,
        benchmark_report=benchmark_report,
    )
    if envelope.girder_count != int(project.geometry.girder_count):
        raise ValueError(
            "Native LM1 envelope girder count does not match the project layout."
        )
    if not 1 <= girder_index <= envelope.girder_count:
        raise IndexError("girder_index is outside the native LM1 envelope.")

    permanent = girder_characteristic_permanent_effects(
        project,
        girder_index=girder_index,
        additional=additional_permanent,
    )
    traffic = envelope.effect_for_girder(girder_index)
    return ProjectGirderCombinationSet(
        girder_index=girder_index,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        persistent_uls=persistent_uls(permanent, traffic, uls_factors),
        characteristic_sls=characteristic_sls(permanent, traffic),
        frequent_sls=frequent_sls(permanent, traffic, sls_factors),
        quasi_permanent_sls=quasi_permanent_sls(permanent, traffic, sls_factors),
        traffic_distribution_method=envelope.metadata.method,
    )


def native_lm1_service_moment_diagram(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    combinations: ProjectGirderCombinationSet,
    deflection_combination: SLSCombinationChoice,
    span_m: float,
    benchmark_source: str,
    additional_permanent: UniformPermanentLoadInput | None = None,
) -> tuple[SimpleSpanMomentDiagram, float] | None:
    """Combine Gk with one co-located native LM1 deflection-case moment field.

    Permanent response is recovered from the physical segmented action pattern
    at the same stations. The traffic field comes directly from the native case
    that governs vertical displacement for this girder. Member-end jumps at
    transverse intersections are retained as duplicate stations and integrate
    over zero length.

    Synthetic/legacy search fixtures without native displacement traces return
    ``None`` and remain on the explicitly labelled compatibility adapter.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")
    if not search.deflections:
        return None

    girder_index = combinations.girder_index
    governing = search.deflection_for_girder(girder_index)
    traffic = native_lm1_girder_moment_diagram(
        search,
        girder_index=girder_index,
        case_id=governing.case_id,
    )
    if abs(traffic.stations_m[-1] - span_m) > 1.0e-9:
        raise RuntimeError("Native LM1 moment diagram does not match the project span.")

    if deflection_combination == SLSCombinationChoice.CHARACTERISTIC:
        selected = combinations.characteristic_sls
    elif deflection_combination == SLSCombinationChoice.FREQUENT:
        selected = combinations.frequent_sls
    elif deflection_combination == SLSCombinationChoice.QUASI_PERMANENT:
        selected = combinations.quasi_permanent_sls
    else:
        raise ValueError(
            f"Unsupported SLS deflection combination: {deflection_combination}"
        )
    permanent_factor = selected.factors["G"]
    traffic_factor = selected.factors["Q_traffic"]
    permanent_moments = girder_permanent_moments_knm_at(
        project,
        girder_index=girder_index,
        stations_m=traffic.stations_m,
        additional=additional_permanent,
    )
    # The native member-end convention recovered by the raw diagram is
    # negative for simple-span sagging. Permanent project moments are
    # sagging-positive, so align the traffic field before combination.
    combined = tuple(
        permanent_factor * permanent_moment - traffic_factor * traffic_moment
        for permanent_moment, traffic_moment in zip(
            permanent_moments,
            traffic.moments_knm,
            strict=True,
        )
    )
    diagram = SimpleSpanMomentDiagram(
        stations_m=traffic.stations_m,
        moments_knm=combined,
        source=(
            f"native LM1 case {governing.case_id}, girder {girder_index}, "
            f"governing node {governing.node_id} at x={governing.position_m:.6g} m; "
            f"G={permanent_factor:.6g}, Q_traffic={traffic_factor:.6g}; "
            "native longitudinal moment mapped to sagging-positive; "
            f"external benchmark={benchmark_source}"
        ),
    )
    return diagram, max(abs(value) for value in combined)


def run_project_t_girder_from_native_lm1(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    girder_index: int,
    section: TGirderDesignInput,
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
    torsion_cell: TorsionCellInput | None = None,
) -> NativeLM1ProjectTGirderResult:
    """Run simple-span EC2 flexure/shear/crack/deflection design from native LM1 traffic.

    The traffic M, V and T values are independent characteristic envelope maxima,
    which is appropriate for separate component checks. When torsion-cell geometry
    is supplied, combined V-T interaction is evaluated separately from co-located
    member-end effects in the same native LM1 traffic case rather than combining
    unrelated independent maxima.
    """
    _require_simple_span_native_design_project(project)
    expected_total_depth_m = (
        float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    )
    if abs(section.total_depth_m - expected_total_depth_m) > 1.0e-9:
        raise ValueError(
            "T-girder total depth must match project girder depth plus physical deck depth."
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
    detailing = run_project_t_girder_detailing(
        project,
        section=section,
        design=design,
    )
    envelope_detailing: ProjectTGirderEnvelopeDetailingResult | None = None
    if all(hasattr(case, "model") and hasattr(case, "analysis") for case in search.cases):
        detailing_envelope = native_lm1_uls_detailing_envelope(
            project,
            search=search,
            girder_index=girder_index,
            additional_permanent=additional_permanent,
            uls_factors=uls_factors,
        )
        envelope_detailing = run_project_t_girder_envelope_detailing(
            project,
            section=section,
            envelope=detailing_envelope,
            cot_theta=cot_theta,
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
    return NativeLM1ProjectTGirderResult(
        combinations=combinations,
        serviceability=serviceability,
        materials=materials,
        design=design,
        detailing=detailing,
        envelope_detailing=envelope_detailing,
        shear_torsion=shear_torsion,
        traffic_trace=trace,
        benchmark_source=benchmark_report.source_name,
        status=(
            "Simple-span Eurocode girder design and current reinforcement detailing driven by "
            "externally benchmarked native LM1 per-girder traffic envelopes; independent M/V/T "
            "governing case IDs are retained, with matched co-located V-T interaction checked "
            "when explicit torsion-cell geometry is supplied. Physical native searches also "
            "produce section-by-section bar-curtailment and link-spacing zones from co-located "
            "ULS envelopes. Service deflection uses the co-located native LM1 curvature field."
        ),
    )


def run_project_all_t_girders_from_native_lm1(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    sections_by_girder: dict[int, TGirderDesignInput],
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
    torsion_cells_by_girder: dict[int, TorsionCellInput] | None = None,
) -> ProjectNativeLM1TGirderDesignSuite:
    """Run the benchmark-gated native LM1 Eurocode design path for every girder."""
    _require_simple_span_native_design_project(project)
    girder_count = int(project.geometry.girder_count)
    required = set(range(1, girder_count + 1))
    if set(sections_by_girder) != required:
        raise ValueError(
            "sections_by_girder must contain exactly one T-section for every project girder."
        )
    additional = additional_permanent_by_girder or {}
    torsion_cells = torsion_cells_by_girder or {}
    unexpected_additional = set(additional) - required
    if unexpected_additional:
        raise ValueError(
            "additional_permanent_by_girder contains unknown girder indices: "
            + ", ".join(str(value) for value in sorted(unexpected_additional))
        )
    unexpected_torsion = set(torsion_cells) - required
    if unexpected_torsion:
        raise ValueError(
            "torsion_cells_by_girder contains unknown girder indices: "
            + ", ".join(str(value) for value in sorted(unexpected_torsion))
        )

    results = tuple(
        run_project_t_girder_from_native_lm1(
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
            torsion_cell=torsion_cells.get(girder_index),
        )
        for girder_index in range(1, girder_count + 1)
    )
    return ProjectNativeLM1TGirderDesignSuite(
        girders=results,
        benchmark_source=benchmark_report.source_name,
        search_strategy=search.search_strategy,
    )
