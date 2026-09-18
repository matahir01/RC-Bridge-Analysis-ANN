from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_station_response import (
    StationSide,
    longitudinal_station_end_response,
)
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.codes.eurocode.en1991_2 import LM1AdjustmentFactors
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.grillage_verification_export import GrillageStiffnessModifiers
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    run_project_native_lm1_grillage_search,
)
from rc_bridge.workflow.project_bridge import UniformPermanentLoadInput
from rc_bridge.workflow.project_construction import (
    ConstructionAnalysisAssumptions,
    PermanentGrillageStageInput,
    ProjectConstructionGrillageResult,
    run_project_construction_grillage,
)
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeResult,
    ContinuousDesignEnvelopeStation,
)


@dataclass(frozen=True)
class ContinuousNativeLM1StationTrace:
    envelope_station_index: int
    girder_index: int
    span_index: int
    local_position_m: float
    global_position_m: float
    side: StationSide
    permanent_torsion_knm: float
    traffic_minimum_moment_knm: float
    traffic_maximum_moment_knm: float
    traffic_minimum_shear_kn: float
    traffic_maximum_shear_kn: float
    traffic_minimum_torsion_knm: float
    traffic_maximum_torsion_knm: float
    minimum_moment_case_id: int | None
    maximum_moment_case_id: int | None
    minimum_shear_case_id: int | None
    maximum_shear_case_id: int | None
    minimum_torsion_case_id: int | None
    maximum_torsion_case_id: int | None


@dataclass(frozen=True)
class ProjectContinuousNativeLM1EnvelopeResult:
    envelope: ContinuousDesignEnvelopeResult
    construction: ProjectConstructionGrillageResult
    traffic: ProjectNativeLM1GrillageSearchResult
    trace: tuple[ContinuousNativeLM1StationTrace, ...]
    design_stations_m: tuple[float, ...]
    status: str


def _continuous_design_stations(
    span_lengths_m: tuple[float, ...],
    *,
    stations_per_span: int,
) -> tuple[float, ...]:
    if stations_per_span < 2:
        raise ValueError("At least two continuous design stations per span are required.")
    values: set[float] = {0.0}
    offset = 0.0
    for span in span_lengths_m:
        for index in range(stations_per_span):
            values.add(
                round(offset + span * index / (stations_per_span - 1), 12)
            )
        offset += span
    return tuple(sorted(values))


def _girder_y_m(project: ProjectInput, girder_index: int) -> float:
    count = int(project.geometry.girder_count)
    if not 1 <= girder_index <= count:
        raise IndexError("girder_index is outside the project girder layout.")
    spacing = float(project.geometry.girder_spacing_m)
    return (girder_index - 1 - 0.5 * (count - 1)) * spacing


def _station_sides(local_x_m: float, span_m: float) -> tuple[StationSide, ...]:
    if abs(local_x_m) <= 1.0e-9:
        return ("right",)
    if abs(local_x_m - span_m) <= 1.0e-9:
        return ("left",)
    return ("left", "right")


def run_project_continuous_native_lm1_envelope(
    project: ProjectInput,
    *,
    girder_index: int,
    construction_stages: tuple[PermanentGrillageStageInput, ...],
    unchanged_supports_and_continuity_basis: str,
    sls_factors: ServiceabilityPsiFactors,
    stations_per_span: int = 11,
    additional_permanent_by_girder: tuple[UniformPermanentLoadInput, ...] | None = None,
    construction_assumptions: ConstructionAnalysisAssumptions | None = None,
    lm1_factors: LM1AdjustmentFactors | None = None,
    uls_factors: EurocodeFactors | None = None,
    traffic_stiffness_modifiers: GrillageStiffnessModifiers | None = None,
    longitudinal_step_m: float = 0.5,
    max_exhaustive_tandem_combinations: int = 5000,
) -> ProjectContinuousNativeLM1EnvelopeResult:
    """Build signed continuous ULS/SLS envelopes from one native full-width grillage.

    Permanent actions are recovered from the cumulative staged construction result,
    so earlier loads retain the stiffness active when they arrived. LM1 is solved
    on the final traffic-stage grillage using the same fixed design stations. At
    interior grid lines both longitudinal member sides are retained, preserving
    real shear jumps caused by transverse grillage force transfer or nodal traffic.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Continuous native LM1 production requires a Eurocode project.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous native LM1 production requires CONTINUOUS supports.")
    spans = tuple(float(value) for value in project.geometry.span_lengths_m)
    if len(spans) < 2:
        raise ValueError("Continuous native LM1 production requires at least two spans.")

    design_stations = _continuous_design_stations(
        spans,
        stations_per_span=stations_per_span,
    )
    construction = run_project_construction_grillage(
        project,
        stages=construction_stages,
        transverse_stations_m=design_stations,
        unchanged_supports_and_continuity_basis=(
            unchanged_supports_and_continuity_basis
        ),
        additional_permanent_by_girder=additional_permanent_by_girder,
        assumptions=construction_assumptions,
    )
    final_stage = construction_stages[-1]
    traffic_modifiers = (
        final_stage.stiffness_modifiers
        if traffic_stiffness_modifiers is None
        else traffic_stiffness_modifiers
    )
    traffic = run_project_native_lm1_grillage_search(
        project,
        transverse_stations_m=design_stations,
        longitudinal_sections_by_span=final_stage.longitudinal_sections_by_span,
        transverse_section=final_stage.transverse_section,
        factors=lm1_factors,
        stiffness_modifiers=traffic_modifiers,
        longitudinal_step_m=longitudinal_step_m,
        max_exhaustive_tandem_combinations=max_exhaustive_tandem_combinations,
        include_spanwise_udl_patterns=True,
        name="EN 1991-2 LM1 continuous native production search",
    )

    y_m = _girder_y_m(project, girder_index)
    permanent_model = construction.stages[-1].model
    permanent_members = construction.final_response.members
    station_results: list[ContinuousDesignEnvelopeStation] = []
    traces: list[ContinuousNativeLM1StationTrace] = []
    offset = 0.0

    for span_index, span_m in enumerate(spans):
        local_positions = tuple(
            span_m * index / (stations_per_span - 1)
            for index in range(stations_per_span)
        )
        span_start = offset
        span_end = offset + span_m
        for local_x in local_positions:
            global_x = offset + local_x
            for side in _station_sides(local_x, span_m):
                permanent = longitudinal_station_end_response(
                    permanent_model,
                    permanent_members,
                    target_y_m=y_m,
                    x_m=global_x,
                    side=side,
                    span_start_m=span_start,
                    span_end_m=span_end,
                )

                min_m = 0.0
                max_m = 0.0
                min_v = 0.0
                max_v = 0.0
                min_t = 0.0
                max_t = 0.0
                min_m_case = None
                max_m_case = None
                min_v_case = None
                max_v_case = None
                min_t_case = None
                max_t_case = None
                for case in traffic.cases:
                    response = longitudinal_station_end_response(
                        case.model,
                        case.analysis.members,
                        target_y_m=y_m,
                        x_m=global_x,
                        side=side,
                        span_start_m=span_start,
                        span_end_m=span_end,
                    )
                    if response.moment_knm < min_m:
                        min_m = response.moment_knm
                        min_m_case = case.placement.case_id
                    if response.moment_knm > max_m:
                        max_m = response.moment_knm
                        max_m_case = case.placement.case_id
                    if response.shear_kn < min_v:
                        min_v = response.shear_kn
                        min_v_case = case.placement.case_id
                    if response.shear_kn > max_v:
                        max_v = response.shear_kn
                        max_v_case = case.placement.case_id
                    if response.torsion_knm < min_t:
                        min_t = response.torsion_knm
                        min_t_case = case.placement.case_id
                    if response.torsion_knm > max_t:
                        max_t = response.torsion_knm
                        max_t_case = case.placement.case_id

                moment_combination = signed_section_combinations(
                    permanent_characteristic_effect=permanent.moment_knm,
                    traffic_characteristic=SignedSectionEnvelope(
                        maximum_positive_effect=max_m,
                        minimum_negative_effect=min_m,
                        response_kind="moment",
                    ),
                    sls_factors=sls_factors,
                    uls_factors=uls_factors,
                )
                shear_combination = signed_section_combinations(
                    permanent_characteristic_effect=permanent.shear_kn,
                    traffic_characteristic=SignedSectionEnvelope(
                        maximum_positive_effect=max_v,
                        minimum_negative_effect=min_v,
                        response_kind="shear",
                    ),
                    sls_factors=sls_factors,
                    uls_factors=uls_factors,
                )
                station_index = len(station_results)
                station_results.append(
                    ContinuousDesignEnvelopeStation(
                        span_index=span_index,
                        local_position_m=local_x,
                        global_position_m=global_x,
                        permanent_moment_knm=permanent.moment_knm,
                        permanent_shear_kn=permanent.shear_kn,
                        moment_combinations=moment_combination,
                        shear_combinations=shear_combination,
                        section_side=side,
                    )
                )
                traces.append(
                    ContinuousNativeLM1StationTrace(
                        envelope_station_index=station_index,
                        girder_index=girder_index,
                        span_index=span_index,
                        local_position_m=local_x,
                        global_position_m=global_x,
                        side=side,
                        permanent_torsion_knm=permanent.torsion_knm,
                        traffic_minimum_moment_knm=min_m,
                        traffic_maximum_moment_knm=max_m,
                        traffic_minimum_shear_kn=min_v,
                        traffic_maximum_shear_kn=max_v,
                        traffic_minimum_torsion_knm=min_t,
                        traffic_maximum_torsion_knm=max_t,
                        minimum_moment_case_id=min_m_case,
                        maximum_moment_case_id=max_m_case,
                        minimum_shear_case_id=min_v_case,
                        maximum_shear_case_id=max_v_case,
                        minimum_torsion_case_id=min_t_case,
                        maximum_torsion_case_id=max_t_case,
                    )
                )
        offset += span_m

    stations = tuple(station_results)
    positive_index = max(
        range(len(stations)),
        key=lambda index: stations[index].moment_combinations.positive_uls_effect,
    )
    negative_index = min(
        range(len(stations)),
        key=lambda index: stations[index].moment_combinations.negative_uls_effect,
    )

    def maximum_shear(index: int) -> float:
        combinations = stations[index].shear_combinations
        return max(
            abs(combinations.positive_uls_effect),
            abs(combinations.negative_uls_effect),
        )

    shear_index = max(range(len(stations)), key=maximum_shear)
    shear_combinations = stations[shear_index].shear_combinations
    signed_shear = (
        shear_combinations.negative_uls_effect
        if abs(shear_combinations.negative_uls_effect)
        > abs(shear_combinations.positive_uls_effect)
        else shear_combinations.positive_uls_effect
    )
    envelope = ContinuousDesignEnvelopeResult(
        stations=stations,
        max_positive_uls_moment_knm=(
            stations[positive_index].moment_combinations.positive_uls_effect
        ),
        max_positive_moment_station_index=positive_index,
        min_negative_uls_moment_knm=(
            stations[negative_index].moment_combinations.negative_uls_effect
        ),
        min_negative_moment_station_index=negative_index,
        max_abs_uls_shear_kn=abs(signed_shear),
        max_abs_shear_station_index=shear_index,
        max_abs_shear_signed_kn=signed_shear,
        traffic_distribution_method=(
            "native full-width vertical grillage LM1; station-side signed envelope"
        ),
        status=(
            "Continuous Eurocode signed ULS/SLS envelope from staged permanent grillage "
            "response plus native full-width LM1 station-side traffic effects"
        ),
    )
    return ProjectContinuousNativeLM1EnvelopeResult(
        envelope=envelope,
        construction=construction,
        traffic=traffic,
        trace=tuple(traces),
        design_stations_m=design_stations,
        status=(
            "Native continuous production envelope integrates full-width transverse LM1 "
            "distribution with staged/nonuniform permanent actions on one physical project. "
            "Independent external acceptance remains locked to the final validation stage."
        ),
    )
