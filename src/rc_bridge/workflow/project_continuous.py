from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    BeamSpanEnvelope,
    ContinuousBeamResult,
    SpanPointLoad,
    member_span_envelope,
    solve_continuous_beam,
)
from rc_bridge.core.models import ProjectInput, SupportSystem


@dataclass(frozen=True)
class GlobalBeamPointLoad:
    magnitude_kn: float
    position_m: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.magnitude_kn < 0.0:
            raise ValueError("Global point-load magnitude cannot be negative.")
        if self.position_m < 0.0:
            raise ValueError("Global point-load position cannot be negative.")


@dataclass(frozen=True)
class ProjectContinuousLoadCase:
    ei_kn_m2_by_span: tuple[float, ...]
    udl_kn_m_by_span: tuple[float, ...]
    point_loads: tuple[GlobalBeamPointLoad, ...] = ()
    envelope_stations: int = 401
    name: str = "continuous beam load case"

    def __post_init__(self) -> None:
        if not self.ei_kn_m2_by_span:
            raise ValueError("At least one span EI is required.")
        if len(self.ei_kn_m2_by_span) != len(self.udl_kn_m_by_span):
            raise ValueError("EI and UDL vectors must contain the same number of spans.")
        if any(value <= 0.0 for value in self.ei_kn_m2_by_span):
            raise ValueError("All span EI values must be positive.")
        if any(value < 0.0 for value in self.udl_kn_m_by_span):
            raise ValueError("Span UDL values cannot be negative.")
        if self.envelope_stations < 2:
            raise ValueError("At least two envelope stations are required.")


@dataclass(frozen=True)
class ProjectContinuousAnalysisResult:
    load_case_name: str
    solution: ContinuousBeamResult
    span_envelopes: tuple[BeamSpanEnvelope, ...]
    total_applied_vertical_load_kn: float
    total_vertical_reaction_kn: float
    status: str


def _map_global_point_loads_to_spans(
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
            raise ValueError("Global point load lies beyond the bridge length.")
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


def run_project_continuous_load_case(
    project: ProjectInput,
    load_case: ProjectContinuousLoadCase,
) -> ProjectContinuousAnalysisResult:
    """Run one deterministic longitudinal load case for a continuous bridge girder.

    ``EI`` stays explicit per span. This avoids silently treating an uncracked
    precast profile, a composite positive-moment section and a cracked support
    section as the same stiffness. Global traffic/point loads are mapped to span
    local coordinates before assembly.
    """
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous load-case workflow requires a CONTINUOUS project.")

    span_lengths = tuple(float(value) for value in project.geometry.span_lengths_m)
    if len(span_lengths) < 2:
        raise ValueError("Continuous bridge analysis requires at least two spans.")
    if len(load_case.ei_kn_m2_by_span) != len(span_lengths):
        raise ValueError("Load-case EI vector must match the project span count.")
    if len(load_case.udl_kn_m_by_span) != len(span_lengths):
        raise ValueError("Load-case UDL vector must match the project span count.")

    mapped_points = _map_global_point_loads_to_spans(span_lengths, load_case.point_loads)
    spans = tuple(
        BeamSpan(
            length_m=length,
            ei_kn_m2=load_case.ei_kn_m2_by_span[index],
            udl_kn_m=load_case.udl_kn_m_by_span[index],
            point_loads=mapped_points[index],
        )
        for index, length in enumerate(span_lengths)
    )
    solution = solve_continuous_beam(spans)
    envelopes = tuple(
        member_span_envelope(
            span,
            solution.members[index],
            stations=load_case.envelope_stations,
        )
        for index, span in enumerate(spans)
    )

    total_applied = sum(
        span.udl_kn_m * span.length_m
        + sum(point.magnitude_kn for point in span.point_loads)
        for span in spans
    )
    total_reaction = sum(node.vertical_reaction_kn for node in solution.nodes)
    return ProjectContinuousAnalysisResult(
        load_case_name=load_case.name,
        solution=solution,
        span_envelopes=envelopes,
        total_applied_vertical_load_kn=total_applied,
        total_vertical_reaction_kn=total_reaction,
        status=(
            "Continuous longitudinal beam load case solved with explicit span EI; "
            "transverse distribution and code-specific load generation remain separate"
        ),
    )
