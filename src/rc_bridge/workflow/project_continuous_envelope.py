from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    SpanPointLoad,
    member_section_response,
    solve_continuous_beam,
)
from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    SignedSectionCombinationSet,
)
from rc_bridge.codes.eurocode.en1991_2 import LM1AdjustmentFactors
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous import GlobalBeamPointLoad
from rc_bridge.workflow.project_continuous_lm1 import (
    ProjectContinuousLM1SectionInput,
    continuous_lm1_girder_combinations,
    run_project_continuous_lm1_section,
)


@dataclass(frozen=True)
class ContinuousDesignEnvelopeInput:
    ei_kn_m2_by_span: tuple[float, ...]
    permanent_udl_kn_m_by_span: tuple[float, ...]
    girder_index: int
    lane_distributions: tuple[LaneGirderDistribution, ...]
    sls_factors: ServiceabilityPsiFactors
    permanent_point_loads: tuple[GlobalBeamPointLoad, ...] = ()
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None
    lm1_factors: LM1AdjustmentFactors | None = None
    uls_factors: EurocodeFactors | None = None
    stations_per_span: int = 11
    influence_positions: int = 201
    movement_steps: int = 301

    def __post_init__(self) -> None:
        if not self.ei_kn_m2_by_span:
            raise ValueError("At least one span EI is required.")
        if len(self.ei_kn_m2_by_span) != len(self.permanent_udl_kn_m_by_span):
            raise ValueError("EI and permanent UDL vectors must have equal lengths.")
        if any(value <= 0.0 for value in self.ei_kn_m2_by_span):
            raise ValueError("All span EI values must be positive.")
        if any(value < 0.0 for value in self.permanent_udl_kn_m_by_span):
            raise ValueError("Permanent UDL values cannot be negative.")
        if self.girder_index <= 0:
            raise ValueError("girder_index must be positive.")
        if not self.lane_distributions:
            raise ValueError("Supplied transverse lane distributions are required.")
        if self.stations_per_span < 2:
            raise ValueError("At least two design-envelope stations per span are required.")
        if self.influence_positions < 2 or self.movement_steps < 2:
            raise ValueError("Influence-line and moving-tandem discretization must each contain at least two points.")


@dataclass(frozen=True)
class ContinuousDesignEnvelopeStation:
    span_index: int
    local_position_m: float
    global_position_m: float
    permanent_moment_knm: float
    permanent_shear_kn: float
    moment_combinations: SignedSectionCombinationSet
    shear_combinations: SignedSectionCombinationSet
    section_side: str | None = None


@dataclass(frozen=True)
class ContinuousDesignEnvelopeResult:
    stations: tuple[ContinuousDesignEnvelopeStation, ...]
    max_positive_uls_moment_knm: float
    max_positive_moment_station_index: int
    min_negative_uls_moment_knm: float
    min_negative_moment_station_index: int
    max_abs_uls_shear_kn: float
    max_abs_shear_station_index: int
    max_abs_shear_signed_kn: float
    traffic_distribution_method: str
    status: str

    @property
    def max_positive_moment_station(self) -> ContinuousDesignEnvelopeStation:
        return self.stations[self.max_positive_moment_station_index]

    @property
    def min_negative_moment_station(self) -> ContinuousDesignEnvelopeStation:
        return self.stations[self.min_negative_moment_station_index]

    @property
    def max_abs_shear_station(self) -> ContinuousDesignEnvelopeStation:
        return self.stations[self.max_abs_shear_station_index]


def _map_permanent_points(
    span_lengths_m: tuple[float, ...],
    point_loads: tuple[GlobalBeamPointLoad, ...],
) -> tuple[tuple[SpanPointLoad, ...], ...]:
    boundaries = [0.0]
    for length in span_lengths_m:
        boundaries.append(boundaries[-1] + length)
    total_length = boundaries[-1]
    mapped: list[list[SpanPointLoad]] = [[] for _ in span_lengths_m]
    for load in point_loads:
        if load.position_m > total_length + 1e-12:
            raise ValueError("Permanent point load lies beyond the bridge length.")
        if abs(load.position_m - total_length) <= 1e-12:
            span_index = len(span_lengths_m) - 1
            local_position = span_lengths_m[-1]
        else:
            span_index = max(0, bisect_right(boundaries, load.position_m) - 1)
            span_index = min(span_index, len(span_lengths_m) - 1)
            local_position = load.position_m - boundaries[span_index]
        mapped[span_index].append(
            SpanPointLoad(
                magnitude_kn=load.magnitude_kn,
                position_m=local_position,
                label=load.label,
            )
        )
    return tuple(tuple(items) for items in mapped)


def run_project_continuous_lm1_design_envelope(
    project: ProjectInput,
    input_data: ContinuousDesignEnvelopeInput,
) -> ContinuousDesignEnvelopeResult:
    """Scan longitudinal Eurocode LM1 ULS/SLS effects across all continuous spans.

    Permanent loads supplied here are already per-girder longitudinal loads.
    Constant supplied transverse distributions are applied at every scan station;
    station-varying grillage effects should instead be imported directly when
    available. The shear envelope is an analysis envelope, not a replacement for
    explicit code critical-section checks near support faces.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Continuous LM1 design envelope requires a Eurocode project.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous LM1 design envelope requires a CONTINUOUS project.")

    span_lengths = tuple(float(value) for value in project.geometry.span_lengths_m)
    if len(span_lengths) < 2:
        raise ValueError("Continuous LM1 design envelope requires at least two spans.")
    if len(input_data.ei_kn_m2_by_span) != len(span_lengths):
        raise ValueError("EI vector must match the project span count.")
    if len(input_data.permanent_udl_kn_m_by_span) != len(span_lengths):
        raise ValueError("Permanent UDL vector must match the project span count.")
    if input_data.girder_index > int(project.geometry.girder_count):
        raise ValueError("girder_index exceeds the project girder count.")

    mapped_points = _map_permanent_points(span_lengths, input_data.permanent_point_loads)
    permanent_spans = tuple(
        BeamSpan(
            length_m=length,
            ei_kn_m2=input_data.ei_kn_m2_by_span[index],
            udl_kn_m=input_data.permanent_udl_kn_m_by_span[index],
            point_loads=mapped_points[index],
        )
        for index, length in enumerate(span_lengths)
    )
    permanent_solution = solve_continuous_beam(permanent_spans)

    station_results: list[ContinuousDesignEnvelopeStation] = []
    global_offset = 0.0
    traffic_method: str | None = None
    for span_index, span in enumerate(permanent_spans):
        for station_index in range(input_data.stations_per_span):
            local_x = span.length_m * station_index / (input_data.stations_per_span - 1)
            permanent = member_section_response(
                span,
                permanent_solution.members[span_index],
                local_x,
            )

            moment_traffic = run_project_continuous_lm1_section(
                project,
                ProjectContinuousLM1SectionInput(
                    ei_kn_m2_by_span=input_data.ei_kn_m2_by_span,
                    response_span_index=span_index,
                    response_position_m=local_x,
                    response_kind="moment",
                    lane_distributions=input_data.lane_distributions,
                    remaining_area_distribution=input_data.remaining_area_distribution,
                    factors=input_data.lm1_factors,
                    influence_positions=input_data.influence_positions,
                    movement_steps=input_data.movement_steps,
                ),
            )
            shear_traffic = run_project_continuous_lm1_section(
                project,
                ProjectContinuousLM1SectionInput(
                    ei_kn_m2_by_span=input_data.ei_kn_m2_by_span,
                    response_span_index=span_index,
                    response_position_m=local_x,
                    response_kind="shear",
                    lane_distributions=input_data.lane_distributions,
                    remaining_area_distribution=input_data.remaining_area_distribution,
                    factors=input_data.lm1_factors,
                    influence_positions=input_data.influence_positions,
                    movement_steps=input_data.movement_steps,
                ),
            )
            if traffic_method is None:
                traffic_method = moment_traffic.traffic_distribution_method
            elif traffic_method != moment_traffic.traffic_distribution_method:
                raise ValueError("Traffic distribution method changed within the design-envelope scan.")

            moment_combinations = continuous_lm1_girder_combinations(
                moment_traffic,
                girder_index=input_data.girder_index,
                permanent_characteristic_effect=permanent.moment_knm,
                sls_factors=input_data.sls_factors,
                uls_factors=input_data.uls_factors,
            )
            shear_combinations = continuous_lm1_girder_combinations(
                shear_traffic,
                girder_index=input_data.girder_index,
                permanent_characteristic_effect=permanent.shear_kn,
                sls_factors=input_data.sls_factors,
                uls_factors=input_data.uls_factors,
            )
            station_results.append(
                ContinuousDesignEnvelopeStation(
                    span_index=span_index,
                    local_position_m=local_x,
                    global_position_m=global_offset + local_x,
                    permanent_moment_knm=permanent.moment_knm,
                    permanent_shear_kn=permanent.shear_kn,
                    moment_combinations=moment_combinations,
                    shear_combinations=shear_combinations,
                )
            )
        global_offset += span.length_m

    stations = tuple(station_results)
    positive_index = max(
        range(len(stations)),
        key=lambda index: stations[index].moment_combinations.positive_uls_effect,
    )
    negative_index = min(
        range(len(stations)),
        key=lambda index: stations[index].moment_combinations.negative_uls_effect,
    )

    def station_max_abs_shear(index: int) -> float:
        combination = stations[index].shear_combinations
        return max(abs(combination.positive_uls_effect), abs(combination.negative_uls_effect))

    shear_index = max(range(len(stations)), key=station_max_abs_shear)
    shear_combination = stations[shear_index].shear_combinations
    shear_signed = (
        shear_combination.negative_uls_effect
        if abs(shear_combination.negative_uls_effect)
        > abs(shear_combination.positive_uls_effect)
        else shear_combination.positive_uls_effect
    )
    return ContinuousDesignEnvelopeResult(
        stations=stations,
        max_positive_uls_moment_knm=stations[
            positive_index
        ].moment_combinations.positive_uls_effect,
        max_positive_moment_station_index=positive_index,
        min_negative_uls_moment_knm=stations[
            negative_index
        ].moment_combinations.negative_uls_effect,
        min_negative_moment_station_index=negative_index,
        max_abs_uls_shear_kn=abs(shear_signed),
        max_abs_shear_station_index=shear_index,
        max_abs_shear_signed_kn=shear_signed,
        traffic_distribution_method=traffic_method or "",
        status=(
            "Continuous Eurocode LM1 analysis/design envelope scanned across all spans using one "
            "permanent-load solution and station-wise signed traffic combinations"
        ),
    )
