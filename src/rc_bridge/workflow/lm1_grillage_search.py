from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

from rc_bridge.analysis.grillage_effects import NativeGrillageEnvelopeResult, native_grillage_traffic_envelope
from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult, solve_vertical_grillage
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    lm1_tandem_axle_spacing_m,
    notional_lane_layout,
)
from rc_bridge.core.models import ProjectInput
from rc_bridge.export.model_verification_package import (
    ModelVerificationExportPackage,
    build_model_verification_export_package,
)
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1LongitudinalRegion,
    LM1RemainingAreaVerificationPlacement,
    build_project_lm1_grillage_verification_model,
)


@dataclass(frozen=True)
class LM1SearchPlacement:
    """One automatically generated LM1 placement evaluated by the native grillage solver."""

    case_id: int
    tandem_lead_x_m: float
    lane_placements: tuple[LM1LaneVerificationPlacement, ...]
    remaining_area_placements: tuple[LM1RemainingAreaVerificationPlacement, ...]


@dataclass(frozen=True)
class LM1SearchCaseResult:
    """Native analysis result for one candidate LM1 placement."""

    placement: LM1SearchPlacement
    model: VerificationModel
    analysis: GrillageAnalysisResult
    girder_envelope: NativeGrillageEnvelopeResult


@dataclass(frozen=True)
class LM1GoverningComponent:
    """Governing absolute response for one action effect and girder."""

    value: float
    case_id: int
    member_id: int


@dataclass(frozen=True)
class LM1GirderGoverningEnvelope:
    """Independent M/V/T governing cases for one longitudinal girder line."""

    girder_index: int
    y_m: float
    moment_knm: LM1GoverningComponent
    shear_kn: LM1GoverningComponent
    torsion_knm: LM1GoverningComponent


@dataclass(frozen=True)
class ProjectNativeLM1GrillageSearchResult:
    """Discrete LM1 placement search across one native grillage definition.

    Moment, shear and torsion are enveloped independently for every girder. The
    first implementation uses edge-based EN 1991-2 notional-lane arrangements,
    all lane-number permutations, full-length UDL, and a common tandem lead
    position scanned longitudinally. It therefore removes equal-share traffic
    distribution from this path while keeping the search assumptions explicit.
    """

    cases: tuple[LM1SearchCaseResult, ...]
    girders: tuple[LM1GirderGoverningEnvelope, ...]
    longitudinal_step_m: float

    @property
    def evaluated_case_count(self) -> int:
        return len(self.cases)

    @property
    def governing_case_ids(self) -> tuple[int, ...]:
        case_ids = {
            component.case_id
            for girder in self.girders
            for component in (girder.moment_knm, girder.shear_kn, girder.torsion_knm)
        }
        return tuple(sorted(case_ids))


def _merge_coordinates(values: list[float], *, tolerance: float = 1.0e-9) -> tuple[float, ...]:
    merged: list[float] = []
    for value in sorted(values):
        if not merged or abs(value - merged[-1]) > tolerance:
            merged.append(value)
    return tuple(merged)


def _tandem_lead_positions(total_length_m: float, step_m: float) -> tuple[float, ...]:
    if step_m <= 0.0:
        raise ValueError("LM1 longitudinal search step must be positive.")
    axle_spacing = lm1_tandem_axle_spacing_m()
    start = -axle_spacing
    positions: list[float] = [start, 0.0, total_length_m - axle_spacing, total_length_m]
    x = start
    while x <= total_length_m + 1.0e-9:
        positions.append(round(x, 12))
        x += step_m
    return _merge_coordinates(
        [min(max(value, start), total_length_m) for value in positions]
    )


def _edge_based_transverse_layouts(
    project: ProjectInput,
) -> tuple[
    tuple[
        tuple[tuple[int, float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    """Return lane-numbered strips and remaining-area strips for both carriageway edges."""
    geometry = project.geometry
    layout = notional_lane_layout(float(geometry.carriageway_width_m))
    left = float(geometry.carriageway_left_edge_m)
    right = float(geometry.carriageway_right_edge_m)
    lane_width = float(layout.lane_width_m)
    remaining_width = float(layout.remaining_width_m)
    lane_numbers = tuple(range(1, layout.lane_count + 1))

    edge_modes = ("left",) if remaining_width <= 1.0e-12 else ("left", "right")
    generated: list[
        tuple[
            tuple[tuple[int, float, float], ...],
            tuple[tuple[float, float], ...],
        ]
    ] = []
    seen: set[
        tuple[
            tuple[tuple[int, float, float], ...],
            tuple[tuple[float, float], ...],
        ]
    ] = set()

    for remainder_edge in edge_modes:
        lane_block_left = left + remaining_width if remainder_edge == "left" else left
        slots = tuple(
            (
                lane_block_left + index * lane_width,
                lane_block_left + (index + 1) * lane_width,
            )
            for index in range(layout.lane_count)
        )
        remaining = (
            ((left, left + remaining_width),)
            if remainder_edge == "left" and remaining_width > 1.0e-12
            else ((right - remaining_width, right),)
            if remaining_width > 1.0e-12
            else ()
        )
        for numbering in permutations(lane_numbers):
            lanes = tuple(
                (lane_number, slot[0], slot[1])
                for lane_number, slot in zip(numbering, slots, strict=True)
            )
            item = (lanes, remaining)
            if item not in seen:
                seen.add(item)
                generated.append(item)
    return tuple(generated)


def generate_lm1_search_placements(
    project: ProjectInput,
    *,
    longitudinal_step_m: float = 0.5,
) -> tuple[LM1SearchPlacement, ...]:
    """Generate the first automated LM1 native-grillage search grid.

    UDL is applied over the complete bridge length in every notional lane and
    remaining-area strip. Tandem systems in all active lanes share a scanned lead
    x-coordinate in this first search generation. Both carriageway-edge origins
    and all lane-number permutations are included.
    """
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    full_length = (LM1LongitudinalRegion(0.0, total_length),)
    positions = _tandem_lead_positions(total_length, longitudinal_step_m)
    transverse_layouts = _edge_based_transverse_layouts(project)

    placements: list[LM1SearchPlacement] = []
    case_id = 1
    for lanes, remaining in transverse_layouts:
        for lead_x in positions:
            lane_placements = tuple(
                LM1LaneVerificationPlacement(
                    lane_number=lane_number,
                    y_start_m=y_start,
                    y_end_m=y_end,
                    udl_regions=full_length,
                    tandem_lead_x_m=lead_x,
                )
                for lane_number, y_start, y_end in lanes
            )
            remaining_placements = tuple(
                LM1RemainingAreaVerificationPlacement(
                    y_start_m=y_start,
                    y_end_m=y_end,
                    udl_regions=full_length,
                )
                for y_start, y_end in remaining
            )
            placements.append(
                LM1SearchPlacement(
                    case_id=case_id,
                    tandem_lead_x_m=lead_x,
                    lane_placements=lane_placements,
                    remaining_area_placements=remaining_placements,
                )
            )
            case_id += 1
    return tuple(placements)


def run_project_native_lm1_grillage_search(
    project: ProjectInput,
    *,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...],
    transverse_section: GrillageSectionProperties,
    transverse_stations_m: tuple[float, ...],
    factors: LM1AdjustmentFactors | None = None,
    longitudinal_step_m: float = 0.5,
    name: str = "EN 1991-2 LM1 native grillage automated search",
) -> ProjectNativeLM1GrillageSearchResult:
    """Run a discrete automated LM1 search and envelope M/V/T independently by girder."""
    placements = generate_lm1_search_placements(
        project,
        longitudinal_step_m=longitudinal_step_m,
    )
    if not placements:
        raise ValueError("Automated LM1 search generated no candidate placements.")

    cases: list[LM1SearchCaseResult] = []
    for placement in placements:
        case_name = f"{name} case {placement.case_id}"
        model = build_project_lm1_grillage_verification_model(
            project,
            longitudinal_sections_by_span=longitudinal_sections_by_span,
            transverse_section=transverse_section,
            transverse_stations_m=transverse_stations_m,
            lane_placements=placement.lane_placements,
            remaining_area_placements=placement.remaining_area_placements,
            factors=factors,
            name=case_name,
        )
        analysis = solve_vertical_grillage(model)
        girder_envelope = native_grillage_traffic_envelope(model, analysis)
        cases.append(
            LM1SearchCaseResult(
                placement=placement,
                model=model,
                analysis=analysis,
                girder_envelope=girder_envelope,
            )
        )

    girder_count = cases[0].girder_envelope.envelope.girder_count
    governing: list[LM1GirderGoverningEnvelope] = []
    for girder_index in range(1, girder_count + 1):
        details = [case.girder_envelope.details[girder_index - 1] for case in cases]
        moment_case_index = max(
            range(len(cases)),
            key=lambda index: details[index].effects.moment_knm,
        )
        shear_case_index = max(
            range(len(cases)),
            key=lambda index: details[index].effects.shear_kn,
        )
        torsion_case_index = max(
            range(len(cases)),
            key=lambda index: details[index].effects.torsion_knm,
        )
        base = details[0]
        moment_detail = details[moment_case_index]
        shear_detail = details[shear_case_index]
        torsion_detail = details[torsion_case_index]
        governing.append(
            LM1GirderGoverningEnvelope(
                girder_index=girder_index,
                y_m=base.y_m,
                moment_knm=LM1GoverningComponent(
                    value=moment_detail.effects.moment_knm,
                    case_id=cases[moment_case_index].placement.case_id,
                    member_id=moment_detail.governing_moment_member_id,
                ),
                shear_kn=LM1GoverningComponent(
                    value=shear_detail.effects.shear_kn,
                    case_id=cases[shear_case_index].placement.case_id,
                    member_id=shear_detail.governing_shear_member_id,
                ),
                torsion_knm=LM1GoverningComponent(
                    value=torsion_detail.effects.torsion_knm,
                    case_id=cases[torsion_case_index].placement.case_id,
                    member_id=torsion_detail.governing_torsion_member_id,
                ),
            )
        )

    return ProjectNativeLM1GrillageSearchResult(
        cases=tuple(cases),
        girders=tuple(governing),
        longitudinal_step_m=longitudinal_step_m,
    )


def build_governing_lm1_search_verification_packages(
    result: ProjectNativeLM1GrillageSearchResult,
) -> dict[int, ModelVerificationExportPackage]:
    """Export only the unique governing search cases for direct MIDAS/STAAD benchmarking."""
    by_id = {case.placement.case_id: case for case in result.cases}
    return {
        case_id: build_model_verification_export_package(by_id[case_id].model)
        for case_id in result.governing_case_ids
    }
