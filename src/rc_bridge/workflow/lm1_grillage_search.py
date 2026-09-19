from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import permutations, product
from math import sqrt

from rc_bridge.analysis.grillage_effects import (
    NativeGrillageEnvelopeResult,
    native_grillage_traffic_envelope,
)
from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult
from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
    vertical_grillage_structure_signature,
)
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
from rc_bridge.workflow.grillage_verification_export import (
    GrillageSectionProperties,
    GrillageStiffnessModifiers,
)
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1LongitudinalRegion,
    LM1RemainingAreaVerificationPlacement,
    build_project_lm1_grillage_verification_model,
)


class LM1SearchCancelled(RuntimeError):
    """Raised when a caller cancels a native LM1 search between solved cases."""


@dataclass(frozen=True)
class LM1SearchPlacement:
    """One automatically generated LM1 placement evaluated by the native solver."""

    case_id: int
    tandem_lead_x_m: float | None
    lane_placements: tuple[LM1LaneVerificationPlacement, ...]
    remaining_area_placements: tuple[LM1RemainingAreaVerificationPlacement, ...]

    @property
    def tandem_lead_positions_m(self) -> tuple[tuple[int, float | None], ...]:
        """Return the independently positioned tandem lead coordinate for each lane."""
        return tuple(
            (lane.lane_number, lane.tandem_lead_x_m)
            for lane in sorted(self.lane_placements, key=lambda item: item.lane_number)
        )

    @property
    def common_udl_regions(self) -> tuple[LM1LongitudinalRegion, ...]:
        """Return the common span-wise UDL pattern used by this generated case."""
        if self.lane_placements:
            return self.lane_placements[0].udl_regions
        if self.remaining_area_placements:
            return self.remaining_area_placements[0].udl_regions
        return ()


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
class LM1GirderGoverningDeflection:
    """Governing co-located native traffic displacement for one girder line."""

    girder_index: int
    value_mm: float
    case_id: int
    node_id: int | None
    position_m: float
    member_id: int | None = None


@dataclass(frozen=True)
class NativeGirderMomentDiagram:
    girder_index: int
    case_id: int
    stations_m: tuple[float, ...]
    moments_knm: tuple[float, ...]


@dataclass(frozen=True)
class ProjectNativeLM1GrillageSearchResult:
    """Discrete LM1 placement search across one native grillage definition.

    Moment, shear and torsion are enveloped independently for every girder.
    Tandem systems are positioned independently by notional lane whenever the
    complete Cartesian grid is within the configured limit. Wider carriageways
    use a deterministic reduced search that retains common-position cases,
    one-lane sweeps and a lane-1/lane-2 pair sweep.

    For continuous bridges, non-empty span-wise UDL patterns are generated.
    Each generated case currently applies one common longitudinal UDL pattern
    to all LM1 UDL strips; the snapshot API still supports lane-specific regions.
    """

    cases: tuple[LM1SearchCaseResult, ...]
    girders: tuple[LM1GirderGoverningEnvelope, ...]
    longitudinal_step_m: float
    search_strategy: str
    tandem_combinations_exhaustive: bool
    theoretical_tandem_combinations_per_transverse_layout: int
    udl_pattern_count: int
    deflections: tuple[LM1GirderGoverningDeflection, ...] = ()
    prepared_structure_count: int = 0
    reused_factorization_solve_count: int = 0

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
        case_ids.update(item.case_id for item in self.deflections)
        return tuple(sorted(case_ids))

    def deflection_for_girder(self, girder_index: int) -> LM1GirderGoverningDeflection:
        match = next(
            (item for item in self.deflections if item.girder_index == girder_index),
            None,
        )
        if match is None:
            raise RuntimeError(
                "Native LM1 search does not contain a co-located deflection trace for "
                f"girder {girder_index}."
            )
        return match


def native_lm1_girder_moment_diagram(
    result: ProjectNativeLM1GrillageSearchResult,
    *,
    girder_index: int,
    case_id: int,
    coordinate_tolerance_m: float = 1.0e-9,
) -> NativeGirderMomentDiagram:
    """Recover a signed longitudinal moment field from one exact native case.

    Native longitudinal members are load-free between generated grid stations.
    Their section moments are therefore linear. The solver reports member-end
    actions, so the internal section convention is ``-M_i`` at the member start
    and ``+M_j`` at its end. Both member values are retained at an intersection:
    a transverse-member couple can produce a real zero-length moment jump, which
    contributes no area to curvature integration but must not be averaged away.
    """
    if coordinate_tolerance_m <= 0.0:
        raise ValueError("Coordinate tolerance must be positive.")
    if not 1 <= girder_index <= len(result.girders):
        raise IndexError("girder_index is outside the native LM1 result.")
    case = next(
        (item for item in result.cases if item.placement.case_id == case_id),
        None,
    )
    if case is None or not hasattr(case, "model") or not hasattr(case, "analysis"):
        raise RuntimeError("Native LM1 moment recovery requires a solved physical search case.")
    target_y = result.girders[girder_index - 1].y_m
    nodes = {node.node_id: node for node in case.model.nodes}
    member_results = {item.member_id: item for item in case.analysis.members}
    members = []
    for beam in case.model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(ni.y_m - target_y) <= 1.0e-9
            and abs(nj.y_m - target_y) <= 1.0e-9
            and nj.x_m > ni.x_m + 1.0e-9
        ):
            members.append((ni.x_m, nj.x_m, beam.member_id))
    members.sort()
    if not members:
        raise RuntimeError("No longitudinal members were found for the requested girder.")

    stations: list[float] = []
    moments: list[float] = []
    for x_i, x_j, member_id in members:
        end = member_results[member_id]
        start_moment = -end.i_vertical_bending_moment_knm
        end_moment = end.j_vertical_bending_moment_knm
        if stations and abs(x_i - stations[-1]) > coordinate_tolerance_m:
            raise RuntimeError("Longitudinal girder members are not contiguous.")
        stations.extend((x_i, x_j))
        moments.extend((start_moment, end_moment))
    return NativeGirderMomentDiagram(
        girder_index=girder_index,
        case_id=case_id,
        stations_m=tuple(stations),
        moments_knm=tuple(moments),
    )


def _member_vertical_displacement_candidates(
    case: LM1SearchCaseResult,
    *,
    target_y_m: float,
    coordinate_tolerance_m: float = 1.0e-9,
) -> tuple[tuple[float, int | None, int | None, float], ...]:
    """Return nodal and interior Hermite displacement extrema on one girder line.

    The native grillage is an Euler-Bernoulli beam model. Its displacement field
    inside each member is the cubic Hermite interpolation of solved nodal
    displacement and local slope. Therefore a governing traffic displacement may
    occur between grid nodes. Interior extrema are found from the quadratic
    derivative of that cubic rather than by densifying the grillage mesh.
    """
    nodes = {node.node_id: node for node in case.model.nodes}
    results = {node.node_id: node for node in case.analysis.nodes}
    candidates: list[tuple[float, int | None, int | None, float]] = []

    quadratic_tolerance = 1.0e-15
    linear_tolerance = 1.0e-15
    endpoint_tolerance_m = 1.0e-10

    for beam in case.model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(ni.y_m - target_y_m) > coordinate_tolerance_m
            or abs(nj.y_m - target_y_m) > coordinate_tolerance_m
            or abs(nj.x_m - ni.x_m) <= coordinate_tolerance_m
        ):
            continue

        dx = nj.x_m - ni.x_m
        length = abs(dx)
        cx = dx / length
        ri = results[beam.node_i]
        rj = results[beam.node_j]
        wi = ri.vertical_displacement_m
        wj = rj.vertical_displacement_m

        # For a longitudinal member dy=0. The grillage transformation defines
        # local Euler-Bernoulli slope as -cx*Ry.
        slope_i = -cx * ri.rotation_y_rad
        slope_j = -cx * rj.rotation_y_rad

        candidates.extend(
            (
                (abs(wi) * 1000.0, beam.node_i, None, ni.x_m),
                (abs(wj) * 1000.0, beam.node_j, None, nj.x_m),
            )
        )

        # w(s) = wi + slope_i*s + A*s^2 + B*s^3.
        coefficient_a = (
            3.0 * (wj - wi) / length**2
            - (2.0 * slope_i + slope_j) / length
        )
        coefficient_b = (
            2.0 * (wi - wj) / length**3
            + (slope_i + slope_j) / length**2
        )

        # dw/ds = slope_i + 2*A*s + 3*B*s^2.
        qa = 3.0 * coefficient_b
        qb = 2.0 * coefficient_a
        qc = slope_i
        roots: list[float] = []
        if abs(qa) <= quadratic_tolerance:
            if abs(qb) > linear_tolerance:
                roots.append(-qc / qb)
        else:
            discriminant = qb**2 - 4.0 * qa * qc
            if discriminant >= 0.0:
                root_term = sqrt(max(discriminant, 0.0))
                roots.extend(
                    (
                        (-qb - root_term) / (2.0 * qa),
                        (-qb + root_term) / (2.0 * qa),
                    )
                )

        for local_x in roots:
            if not (
                endpoint_tolerance_m
                < local_x
                < length - endpoint_tolerance_m
            ):
                continue
            displacement = (
                wi
                + slope_i * local_x
                + coefficient_a * local_x**2
                + coefficient_b * local_x**3
            )
            position_m = ni.x_m + cx * local_x
            candidates.append(
                (
                    abs(displacement) * 1000.0,
                    None,
                    beam.member_id,
                    position_m,
                )
            )

    if not candidates:
        raise RuntimeError(
            "Native LM1 deflection recovery found no longitudinal members for "
            f"girder y={target_y_m:.6g} m."
        )
    return tuple(candidates)


@dataclass(frozen=True)
class _LM1SearchPlan:
    placements: tuple[LM1SearchPlacement, ...]
    tandem_combinations_exhaustive: bool
    theoretical_tandem_combinations_per_transverse_layout: int
    udl_pattern_count: int
    strategy: str


def _merge_coordinates(
    values: list[float],
    *,
    tolerance: float = 1.0e-9,
) -> tuple[float, ...]:
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


def _seed_positions(
    positions: tuple[float, ...],
    *,
    maximum_count: int = 5,
) -> tuple[float, ...]:
    if len(positions) <= maximum_count:
        return positions
    indices = {
        round(index * (len(positions) - 1) / (maximum_count - 1))
        for index in range(maximum_count)
    }
    return tuple(positions[index] for index in sorted(indices))


def _tandem_position_vectors(
    *,
    lane_count: int,
    positions: tuple[float, ...],
    max_exhaustive_combinations: int,
) -> tuple[tuple[tuple[float, ...], ...], bool, int]:
    if lane_count < 1:
        raise ValueError("LM1 search requires at least one notional lane.")
    if max_exhaustive_combinations < 1:
        raise ValueError("max_exhaustive_tandem_combinations must be positive.")

    theoretical = len(positions) ** lane_count
    if theoretical <= max_exhaustive_combinations:
        return tuple(product(positions, repeat=lane_count)), True, theoretical

    candidates: list[tuple[float, ...]] = []
    seen: set[tuple[float, ...]] = set()

    def add(values: tuple[float, ...]) -> None:
        if values not in seen:
            seen.add(values)
            candidates.append(values)

    for position in positions:
        add((position,) * lane_count)

    seeds = _seed_positions(positions)
    for seed in seeds:
        base = [seed] * lane_count
        for lane_index in range(lane_count):
            for position in positions:
                trial = base.copy()
                trial[lane_index] = position
                add(tuple(trial))

    if lane_count >= 2:
        middle = positions[len(positions) // 2]
        base = [middle] * lane_count
        pair_count = len(positions) ** 2
        if pair_count <= max_exhaustive_combinations:
            for lane_1_position in positions:
                for lane_2_position in positions:
                    trial = base.copy()
                    trial[0] = lane_1_position
                    trial[1] = lane_2_position
                    add(tuple(trial))

    return tuple(candidates), False, theoretical


def _span_regions(project: ProjectInput) -> tuple[LM1LongitudinalRegion, ...]:
    regions: list[LM1LongitudinalRegion] = []
    x = 0.0
    for span_length in project.geometry.span_lengths_m:
        x_next = x + float(span_length)
        regions.append(LM1LongitudinalRegion(x, x_next))
        x = x_next
    return tuple(regions)


def _udl_region_patterns(
    project: ProjectInput,
    *,
    include_spanwise_patterns: bool,
) -> tuple[tuple[LM1LongitudinalRegion, ...], ...]:
    spans = _span_regions(project)
    if not spans:
        raise ValueError("LM1 UDL search requires at least one physical span.")
    if not include_spanwise_patterns or len(spans) == 1:
        return (spans,)

    patterns: list[tuple[LM1LongitudinalRegion, ...]] = []
    seen: set[tuple[tuple[float, float], ...]] = set()

    def add(regions: tuple[LM1LongitudinalRegion, ...]) -> None:
        signature = tuple((item.x_start_m, item.x_end_m) for item in regions)
        if signature and signature not in seen:
            seen.add(signature)
            patterns.append(regions)

    span_count = len(spans)
    if span_count <= 4:
        for mask in range(1, 1 << span_count):
            add(tuple(spans[index] for index in range(span_count) if mask & (1 << index)))
    else:
        add(spans)
        for region in spans:
            add((region,))
        add(tuple(spans[::2]))
        add(tuple(spans[1::2]))
        for index in range(span_count - 1):
            add((spans[index], spans[index + 1]))

    return tuple(patterns)


def _edge_based_transverse_layouts(
    project: ProjectInput,
) -> tuple[
    tuple[
        tuple[tuple[int, float, float], ...],
        tuple[tuple[float, float], ...],
    ],
    ...,
]:
    """Return lane-numbered strips and remaining-area strips for both edges."""
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


def _generate_lm1_search_plan(
    project: ProjectInput,
    *,
    longitudinal_step_m: float,
    max_exhaustive_tandem_combinations: int,
    include_spanwise_udl_patterns: bool,
) -> _LM1SearchPlan:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    positions = _tandem_lead_positions(total_length, longitudinal_step_m)
    transverse_layouts = _edge_based_transverse_layouts(project)
    lane_count = notional_lane_layout(float(project.geometry.carriageway_width_m)).lane_count
    tandem_vectors, exhaustive, theoretical = _tandem_position_vectors(
        lane_count=lane_count,
        positions=positions,
        max_exhaustive_combinations=max_exhaustive_tandem_combinations,
    )
    udl_patterns = _udl_region_patterns(
        project,
        include_spanwise_patterns=include_spanwise_udl_patterns,
    )

    placements: list[LM1SearchPlacement] = []
    case_id = 1
    for lanes, remaining in transverse_layouts:
        for udl_regions in udl_patterns:
            for tandem_vector in tandem_vectors:
                tandem_by_lane = {
                    lane_number: tandem_vector[lane_number - 1]
                    for lane_number in range(1, lane_count + 1)
                }
                lane_placements = tuple(
                    LM1LaneVerificationPlacement(
                        lane_number=lane_number,
                        y_start_m=y_start,
                        y_end_m=y_end,
                        udl_regions=udl_regions,
                        tandem_lead_x_m=tandem_by_lane[lane_number],
                    )
                    for lane_number, y_start, y_end in lanes
                )
                remaining_placements = tuple(
                    LM1RemainingAreaVerificationPlacement(
                        y_start_m=y_start,
                        y_end_m=y_end,
                        udl_regions=udl_regions,
                    )
                    for y_start, y_end in remaining
                )
                common_tandem = (
                    tandem_vector[0]
                    if all(
                        abs(value - tandem_vector[0]) <= 1.0e-12
                        for value in tandem_vector
                    )
                    else None
                )
                placements.append(
                    LM1SearchPlacement(
                        case_id=case_id,
                        tandem_lead_x_m=common_tandem,
                        lane_placements=lane_placements,
                        remaining_area_placements=remaining_placements,
                    )
                )
                case_id += 1

    tandem_strategy = (
        "exhaustive-independent-tandem"
        if exhaustive
        else "reduced-independent-tandem"
    )
    udl_strategy = (
        "span-pattern-udl"
        if include_spanwise_udl_patterns and len(project.geometry.span_lengths_m) > 1
        else "full-length-udl"
    )
    return _LM1SearchPlan(
        placements=tuple(placements),
        tandem_combinations_exhaustive=exhaustive,
        theoretical_tandem_combinations_per_transverse_layout=theoretical,
        udl_pattern_count=len(udl_patterns),
        strategy=f"{tandem_strategy}+{udl_strategy}",
    )


def _common_lm1_analysis_stations(
    project: ProjectInput,
    *,
    base_stations_m: tuple[float, ...],
    placements: tuple[LM1SearchPlacement, ...],
) -> tuple[float, ...]:
    """Return one longitudinal grid containing every candidate axle/load boundary."""

    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    axle_spacing = lm1_tandem_axle_spacing_m()
    values = [float(value) for value in base_stations_m]
    for placement in placements:
        for lane in placement.lane_placements:
            for region in lane.udl_regions:
                values.extend((region.x_start_m, region.x_end_m))
            if lane.tandem_lead_x_m is None:
                continue
            for axle_x in (
                lane.tandem_lead_x_m,
                lane.tandem_lead_x_m + axle_spacing,
            ):
                if -1.0e-9 <= axle_x <= total_length + 1.0e-9:
                    values.append(min(max(float(axle_x), 0.0), total_length))
        for remaining in placement.remaining_area_placements:
            for region in remaining.udl_regions:
                values.extend((region.x_start_m, region.x_end_m))
    return _merge_coordinates(values)


def _common_lm1_transverse_grid_lines(
    placements: tuple[LM1SearchPlacement, ...],
) -> tuple[float, ...]:
    """Return all lane/remaining-area boundaries used by the complete search."""

    values: list[float] = []
    for placement in placements:
        for lane in placement.lane_placements:
            values.extend((lane.y_start_m, lane.y_end_m))
        for remaining in placement.remaining_area_placements:
            values.extend((remaining.y_start_m, remaining.y_end_m))
    return _merge_coordinates(values)


def generate_lm1_search_placements(
    project: ProjectInput,
    *,
    longitudinal_step_m: float = 0.5,
    max_exhaustive_tandem_combinations: int = 5000,
    include_spanwise_udl_patterns: bool = True,
) -> tuple[LM1SearchPlacement, ...]:
    """Generate automated LM1 native-grillage search cases.

    Tandem lead positions are independent by lane. The full Cartesian search is
    used when it is small enough; otherwise a deterministic reduced search is
    used. Continuous bridges also receive non-empty span-wise UDL patterns.
    """
    return _generate_lm1_search_plan(
        project,
        longitudinal_step_m=longitudinal_step_m,
        max_exhaustive_tandem_combinations=max_exhaustive_tandem_combinations,
        include_spanwise_udl_patterns=include_spanwise_udl_patterns,
    ).placements


def run_project_native_lm1_grillage_search(
    project: ProjectInput,
    *,
    transverse_stations_m: tuple[float, ...],
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...] | None = None,
    transverse_section: GrillageSectionProperties | None = None,
    factors: LM1AdjustmentFactors | None = None,
    stiffness_modifiers: GrillageStiffnessModifiers | None = None,
    longitudinal_step_m: float = 0.5,
    max_exhaustive_tandem_combinations: int = 5000,
    include_spanwise_udl_patterns: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    name: str = "EN 1991-2 LM1 native grillage automated search",
) -> ProjectNativeLM1GrillageSearchResult:
    """Run automated LM1 placement search and envelope M/V/T by girder.

    When explicit grillage sections are omitted, physical longitudinal and
    transverse gross properties are derived from the project geometry by the
    common verification-model builder. Explicit section inputs remain available
    as expert overrides and are preserved in exported benchmark models.
    """
    plan = _generate_lm1_search_plan(
        project,
        longitudinal_step_m=longitudinal_step_m,
        max_exhaustive_tandem_combinations=max_exhaustive_tandem_combinations,
        include_spanwise_udl_patterns=include_spanwise_udl_patterns,
    )
    if not plan.placements:
        raise ValueError("Automated LM1 search generated no candidate placements.")

    common_stations = _common_lm1_analysis_stations(
        project,
        base_stations_m=transverse_stations_m,
        placements=plan.placements,
    )
    common_y_lines = _common_lm1_transverse_grid_lines(plan.placements)
    prepared_by_signature: dict[tuple[object, ...], object] = {}
    cases: list[LM1SearchCaseResult] = []
    total_cases = len(plan.placements)
    if progress_callback is not None:
        progress_callback(0, total_cases)

    for completed_before, placement in enumerate(plan.placements):
        if cancel_check is not None and cancel_check():
            raise LM1SearchCancelled(
                f"Native LM1 analysis cancelled after {completed_before} of {total_cases} cases."
            )

        case_name = f"{name} case {placement.case_id}"
        model = build_project_lm1_grillage_verification_model(
            project,
            longitudinal_sections_by_span=longitudinal_sections_by_span,
            transverse_section=transverse_section,
            transverse_stations_m=common_stations,
            lane_placements=placement.lane_placements,
            remaining_area_placements=placement.remaining_area_placements,
            factors=factors,
            stiffness_modifiers=stiffness_modifiers,
            additional_transverse_y_m=common_y_lines,
            name=case_name,
        )
        signature = vertical_grillage_structure_signature(model)
        prepared = prepared_by_signature.get(signature)
        if prepared is None:
            prepared = prepare_vertical_grillage(model)
            prepared_by_signature[signature] = prepared
        analysis = solve_prepared_vertical_grillage(prepared, model)
        girder_envelope = native_grillage_traffic_envelope(model, analysis)
        cases.append(
            LM1SearchCaseResult(
                placement=placement,
                model=model,
                analysis=analysis,
                girder_envelope=girder_envelope,
            )
        )
        if progress_callback is not None:
            progress_callback(len(cases), total_cases)

    girder_count = cases[0].girder_envelope.envelope.girder_count
    governing: list[LM1GirderGoverningEnvelope] = []
    governing_deflections: list[LM1GirderGoverningDeflection] = []
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
        displacement_candidates: list[
            tuple[float, int, int | None, int | None, float]
        ] = []
        for case in cases:
            displacement_candidates.extend(
                (
                    value_mm,
                    case.placement.case_id,
                    node_id,
                    member_id,
                    position_m,
                )
                for value_mm, node_id, member_id, position_m in (
                    _member_vertical_displacement_candidates(
                        case,
                        target_y_m=base.y_m,
                    )
                )
            )
        value_mm, case_id, node_id, member_id, position_m = max(
            displacement_candidates,
            key=lambda item: item[0],
        )
        governing_deflections.append(
            LM1GirderGoverningDeflection(
                girder_index=girder_index,
                value_mm=value_mm,
                case_id=case_id,
                node_id=node_id,
                position_m=position_m,
                member_id=member_id,
            )
        )

    return ProjectNativeLM1GrillageSearchResult(
        cases=tuple(cases),
        girders=tuple(governing),
        longitudinal_step_m=longitudinal_step_m,
        search_strategy=plan.strategy,
        tandem_combinations_exhaustive=plan.tandem_combinations_exhaustive,
        theoretical_tandem_combinations_per_transverse_layout=(
            plan.theoretical_tandem_combinations_per_transverse_layout
        ),
        udl_pattern_count=plan.udl_pattern_count,
        deflections=tuple(governing_deflections),
        prepared_structure_count=len(prepared_by_signature),
        reused_factorization_solve_count=(
            len(cases) - len(prepared_by_signature)
        ),
    )


def build_governing_lm1_search_verification_packages(
    result: ProjectNativeLM1GrillageSearchResult,
) -> dict[int, ModelVerificationExportPackage]:
    """Export unique governing search cases for direct MIDAS/STAAD benchmarking."""
    by_id = {case.placement.case_id: case for case in result.cases}
    return {
        case_id: build_model_verification_export_package(by_id[case_id].model)
        for case_id in result.governing_case_ids
    }
