from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from rc_bridge.analysis.grillage_solver import (
    GrillageAnalysisResult,
    solve_vertical_grillage,
)
from rc_bridge.analysis.moving_loads import positioned_axles
from rc_bridge.codes.eurocode.fatigue_traffic import fatigue_load_model_3
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_cracking import cracked_t_section_sls
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import (
    GrillagePointLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    girder_permanent_moments_knm_at,
    project_eurocode_material_input,
)
from rc_bridge.workflow.project_fatigue import (
    ConcreteFatigueInput,
    ProjectFatigueInput,
    ProjectFatigueResult,
    ReinforcementFatigueInput,
    run_project_eurocode_fatigue,
)


@dataclass(frozen=True)
class NativeFLM3CaseResult:
    """One solved full-width FLM3 vehicle position."""

    case_id: int
    lead_position_m: float
    model: VerificationModel
    analysis: GrillageAnalysisResult


@dataclass(frozen=True)
class NativeFLM3GirderMomentRange:
    """Governing signed FLM3 moment range at one physical girder section."""

    girder_index: int
    y_m: float
    section_position_m: float
    minimum_moment_knm: float
    maximum_moment_knm: float
    moment_range_knm: float
    minimum_case_id: int | None
    maximum_case_id: int | None
    minimum_lead_position_m: float | None
    maximum_lead_position_m: float | None
    minimum_member_id: int | None
    maximum_member_id: int | None


@dataclass(frozen=True)
class ProjectNativeFLM3GrillageSearchResult:
    """Native full-width FLM3 search with per-girder co-located moment ranges."""

    cases: tuple[NativeFLM3CaseResult, ...]
    girders: tuple[NativeFLM3GirderMomentRange, ...]
    span_m: float
    vehicle_centre_y_m: float
    axle_load_factor: float
    movement_step_m: float
    section_step_m: float
    status: str

    def range_for_girder(self, girder_index: int) -> NativeFLM3GirderMomentRange:
        match = next(
            (item for item in self.girders if item.girder_index == girder_index),
            None,
        )
        if match is None:
            raise IndexError("girder_index is outside the native FLM3 result.")
        return match


@dataclass(frozen=True)
class NativeFLM3TGirderFatigueResult:
    """EC2 longitudinal reinforcement/concrete fatigue check from native FLM3."""

    girder_index: int
    traffic_range: NativeFLM3GirderMomentRange
    permanent_moment_knm: float
    minimum_total_moment_knm: float
    maximum_total_moment_knm: float
    reference_steel_stress_range_mpa: float
    minimum_concrete_compression_mpa: float
    maximum_concrete_compression_mpa: float
    fatigue: ProjectFatigueResult
    status: str


@dataclass(frozen=True)
class NativeFLM3FatigueDesignInput:
    """Project-level EC2 fatigue resistance and damage-equivalence inputs."""

    lambda_s: float
    characteristic_fatigue_strength_mpa: float
    gamma_s_fat: float = 1.15
    phi_fat: float = 1.0
    check_concrete: bool = True
    concrete_gamma_c: float = 1.50
    concrete_alpha_cc: float = 1.0
    concrete_k1: float = 0.85
    concrete_beta_cc_t0: float = 1.0

    def __post_init__(self) -> None:
        if min(
            self.lambda_s,
            self.characteristic_fatigue_strength_mpa,
            self.gamma_s_fat,
            self.phi_fat,
            self.concrete_gamma_c,
            self.concrete_alpha_cc,
            self.concrete_k1,
            self.concrete_beta_cc_t0,
        ) <= 0.0:
            raise ValueError("Native FLM3 fatigue design factors must be positive.")


@dataclass
class _RangeState:
    minimum_moment_knm: float = 0.0
    maximum_moment_knm: float = 0.0
    minimum_case_id: int | None = None
    maximum_case_id: int | None = None
    minimum_lead_position_m: float | None = None
    maximum_lead_position_m: float | None = None
    minimum_member_id: int | None = None
    maximum_member_id: int | None = None


def _girder_y_coordinates(project: ProjectInput) -> tuple[float, ...]:
    count = int(project.geometry.girder_count)
    spacing = float(project.geometry.girder_spacing_m)
    first = (
        -float(project.geometry.deck_width_m) / 2.0
        + float(project.geometry.nominal_edge_overhang_m)
    )
    return tuple(first + index * spacing for index in range(count))


def _regular_positions(end_m: float, step_m: float) -> tuple[float, ...]:
    divisions = max(1, ceil(end_m / step_m))
    return tuple(min(index * step_m, end_m) for index in range(divisions + 1))


def _flm3_lead_positions(
    *,
    span_m: float,
    train_length_m: float,
    axle_offsets_m: tuple[float, ...],
    movement_step_m: float,
) -> tuple[float, ...]:
    end = span_m + train_length_m
    positions = set(_regular_positions(end, movement_step_m))
    positions.update((0.0, end))
    for target in (0.0, span_m / 2.0, span_m):
        for offset in axle_offsets_m:
            lead = target + offset
            if 0.0 <= lead <= end:
                positions.add(lead)
    return tuple(sorted(round(value, 12) for value in positions))


def _section_positions(
    *,
    span_m: float,
    section_step_m: float,
    additional_stations_m: tuple[float, ...],
) -> tuple[float, ...]:
    positions = set(_regular_positions(span_m, section_step_m))
    positions.update((0.0, span_m / 2.0, span_m))
    for station in additional_stations_m:
        value = float(station)
        if value < -1.0e-9 or value > span_m + 1.0e-9:
            raise ValueError("A fatigue reporting station lies outside the simple span.")
        positions.add(min(max(value, 0.0), span_m))
    return tuple(sorted(round(value, 12) for value in positions))


def _signed_longitudinal_moment_candidates(
    case: NativeFLM3CaseResult,
    *,
    target_y_m: float,
    x_m: float,
    tolerance_m: float = 1.0e-9,
) -> tuple[tuple[float, int], ...]:
    nodes = {node.node_id: node for node in case.model.nodes}
    results = {item.member_id: item for item in case.analysis.members}
    candidates: list[tuple[float, int]] = []

    for beam in case.model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(ni.y_m - target_y_m) > tolerance_m
            or abs(nj.y_m - target_y_m) > tolerance_m
            or abs(nj.x_m - ni.x_m) <= tolerance_m
        ):
            continue
        left = min(ni.x_m, nj.x_m)
        right = max(ni.x_m, nj.x_m)
        if x_m < left - tolerance_m or x_m > right + tolerance_m:
            continue

        result = results[beam.member_id]
        if nj.x_m > ni.x_m:
            x_i = ni.x_m
            x_j = nj.x_m
            moment_i = -result.i_vertical_bending_moment_knm
            moment_j = result.j_vertical_bending_moment_knm
        else:
            x_i = nj.x_m
            x_j = ni.x_m
            moment_i = result.j_vertical_bending_moment_knm
            moment_j = -result.i_vertical_bending_moment_knm

        ratio = (x_m - x_i) / (x_j - x_i)
        ratio = min(max(ratio, 0.0), 1.0)
        # The native element end-action convention is opposite to the
        # sagging-positive bridge-section convention used by the design
        # workflows. Convert here so a downward FLM3 vehicle on a simple span
        # produces positive sagging moment.
        moment = -(moment_i + ratio * (moment_j - moment_i))
        if abs(moment) <= 1.0e-10:
            moment = 0.0
        candidates.append((moment, beam.member_id))

    if not candidates:
        raise RuntimeError(
            f"Native FLM3 moment recovery found no longitudinal member at x={x_m:.6g} m."
        )
    return tuple(candidates)


def run_project_native_flm3_grillage_search(
    project: ProjectInput,
    *,
    vehicle_centre_y_m: float,
    transverse_stations_m: tuple[float, ...],
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...] | None = None,
    transverse_section: GrillageSectionProperties | None = None,
    axle_load_factor: float = 1.0,
    movement_step_m: float = 0.5,
    section_step_m: float = 0.5,
    name: str = "EN 1991-2 FLM3 native grillage search",
) -> ProjectNativeFLM3GrillageSearchResult:
    """Move FLM3 across the full bridge grillage and recover per-girder M ranges.

    The fatigue vehicle transverse centre is explicit. This routine does not
    substitute an LM1 distribution factor and does not silently choose a
    National-Annex fatigue-lane position. Each 120 kN axle line is represented
    by two equal wheel loads at the FLM3 2.0 m transverse wheel spacing.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native FLM3 fatigue analysis currently supports Eurocode only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("Native FLM3 fatigue analysis currently supports simple spans only.")
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError("Native FLM3 fatigue analysis currently requires exactly one span.")
    if movement_step_m <= 0.0 or section_step_m <= 0.0:
        raise ValueError("FLM3 movement and section steps must be positive.")

    span_m = float(project.geometry.span_lengths_m[0])
    vehicle = fatigue_load_model_3(axle_load_factor=axle_load_factor)
    half_wheel_spacing = vehicle.transverse_wheel_spacing_m / 2.0
    wheel_y = (
        float(vehicle_centre_y_m) - half_wheel_spacing,
        float(vehicle_centre_y_m) + half_wheel_spacing,
    )
    carriageway_left = float(project.geometry.carriageway_left_edge_m)
    carriageway_right = float(project.geometry.carriageway_right_edge_m)
    if (
        wheel_y[0] < carriageway_left - 1.0e-9
        or wheel_y[1] > carriageway_right + 1.0e-9
    ):
        raise ValueError(
            "FLM3 wheel centres must lie inside the physical carriageway; choose an "
            "explicit fatigue-lane vehicle centre consistent with the project/NA."
        )

    leads = _flm3_lead_positions(
        span_m=span_m,
        train_length_m=vehicle.axle_train.train_length_m,
        axle_offsets_m=vehicle.axle_offsets_m,
        movement_step_m=movement_step_m,
    )
    reporting_stations = _section_positions(
        span_m=span_m,
        section_step_m=section_step_m,
        additional_stations_m=transverse_stations_m,
    )

    cases: list[NativeFLM3CaseResult] = []
    for lead in leads:
        active_axles = positioned_axles(vehicle.axle_train, lead, span_m)
        if not any(
            1.0e-9 < axle.position_m < span_m - 1.0e-9
            for axle in active_axles
        ):
            # A vehicle state carried only directly at simple supports has zero
            # longitudinal bending and is already represented by the explicit
            # unloaded zero baseline used when forming fatigue ranges. Skipping
            # it also avoids creating a degenerate support-only grillage slice.
            continue
        case_id = len(cases) + 1
        point_loads = tuple(
            GrillagePointLoad(
                x_m=axle.position_m,
                y_m=y_m,
                magnitude_kn=axle.magnitude_kn / 2.0,
                label=(
                    f"FLM3 case {case_id} {axle.label} "
                    f"{'left' if wheel_index == 1 else 'right'} wheel"
                ),
            )
            for axle in active_axles
            for wheel_index, y_m in enumerate(wheel_y, start=1)
        )
        load_case = GrillageVerificationLoadCase(
            name=f"{name} case {case_id}",
            point_loads=point_loads,
        )
        model = build_project_grillage_verification_model(
            project,
            longitudinal_sections_by_span=longitudinal_sections_by_span,
            transverse_section=transverse_section,
            transverse_stations_m=transverse_stations_m,
            load_case=load_case,
        )
        analysis = solve_vertical_grillage(model)
        cases.append(
            NativeFLM3CaseResult(
                case_id=case_id,
                lead_position_m=lead,
                model=model,
                analysis=analysis,
            )
        )

    y_coordinates = _girder_y_coordinates(project)
    girder_ranges: list[NativeFLM3GirderMomentRange] = []
    for girder_index, y_m in enumerate(y_coordinates, start=1):
        states = {x_m: _RangeState() for x_m in reporting_stations}
        for case in cases:
            for x_m in reporting_stations:
                for moment, member_id in _signed_longitudinal_moment_candidates(
                    case,
                    target_y_m=y_m,
                    x_m=x_m,
                ):
                    state = states[x_m]
                    if moment < state.minimum_moment_knm:
                        state.minimum_moment_knm = moment
                        state.minimum_case_id = case.case_id
                        state.minimum_lead_position_m = case.lead_position_m
                        state.minimum_member_id = member_id
                    if moment > state.maximum_moment_knm:
                        state.maximum_moment_knm = moment
                        state.maximum_case_id = case.case_id
                        state.maximum_lead_position_m = case.lead_position_m
                        state.maximum_member_id = member_id

        governing_x = max(
            reporting_stations,
            key=lambda value: (
                states[value].maximum_moment_knm - states[value].minimum_moment_knm
            ),
        )
        state = states[governing_x]
        girder_ranges.append(
            NativeFLM3GirderMomentRange(
                girder_index=girder_index,
                y_m=y_m,
                section_position_m=governing_x,
                minimum_moment_knm=state.minimum_moment_knm,
                maximum_moment_knm=state.maximum_moment_knm,
                moment_range_knm=(
                    state.maximum_moment_knm - state.minimum_moment_knm
                ),
                minimum_case_id=state.minimum_case_id,
                maximum_case_id=state.maximum_case_id,
                minimum_lead_position_m=state.minimum_lead_position_m,
                maximum_lead_position_m=state.maximum_lead_position_m,
                minimum_member_id=state.minimum_member_id,
                maximum_member_id=state.maximum_member_id,
            )
        )

    return ProjectNativeFLM3GrillageSearchResult(
        cases=tuple(cases),
        girders=tuple(girder_ranges),
        span_m=span_m,
        vehicle_centre_y_m=float(vehicle_centre_y_m),
        axle_load_factor=axle_load_factor,
        movement_step_m=movement_step_m,
        section_step_m=section_step_m,
        status=(
            "Full-width native EN 1991-2 FLM3 moving-vehicle grillage search; "
            "fatigue-lane transverse position and axle adjustment remain explicit "
            "project/National-Annex inputs. Independent external validation remains pending."
        ),
    )


def run_project_t_girder_fatigue_from_native_flm3(
    project: ProjectInput,
    *,
    search: ProjectNativeFLM3GrillageSearchResult,
    girder_index: int,
    section: TGirderDesignInput,
    lambda_s: float,
    characteristic_fatigue_strength_mpa: float,
    additional_permanent: UniformPermanentLoadInput | None = None,
    gamma_s_fat: float = 1.15,
    phi_fat: float = 1.0,
    es_mpa: float = 200000.0,
    check_concrete: bool = True,
    concrete_gamma_c: float = 1.50,
    concrete_alpha_cc: float = 1.0,
    concrete_k1: float = 0.85,
    concrete_beta_cc_t0: float = 1.0,
) -> NativeFLM3TGirderFatigueResult:
    """Run T-girder longitudinal reinforcement/concrete fatigue from native FLM3.

    The reinforcement stress range is recovered from the cracked transformed
    section at the same physical section that governs the native FLM3 moment
    range. Permanent moment establishes the concrete minimum/maximum compression
    stress but does not get misused as cyclic traffic range.

    Moment reversal that drives the total section into hogging is rejected
    because this first simple-span adapter models only positive-bending bottom
    reinforcement fatigue.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native FLM3 fatigue design currently supports Eurocode only.")
    if abs(search.span_m - float(project.geometry.span_lengths_m[0])) > 1.0e-9:
        raise ValueError("Native FLM3 search span does not match the project.")
    if len(search.girders) != int(project.geometry.girder_count):
        raise ValueError("Native FLM3 search girder count does not match the project.")
    expected_total_depth = (
        float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    )
    if abs(section.total_depth_m - expected_total_depth) > 1.0e-9:
        raise ValueError(
            "T-girder total depth must match project girder depth plus physical deck depth."
        )

    traffic = search.range_for_girder(girder_index)
    permanent_moment = girder_permanent_moments_knm_at(
        project,
        girder_index=girder_index,
        stations_m=(traffic.section_position_m,),
        additional=additional_permanent,
    )[0]
    minimum_total = permanent_moment + traffic.minimum_moment_knm
    maximum_total = permanent_moment + traffic.maximum_moment_knm
    if minimum_total < -1.0e-8:
        raise ValueError(
            "Native FLM3 fatigue range causes total moment reversal; the current "
            "positive-bending T-girder fatigue section model is not valid for hogging."
        )
    minimum_total = max(minimum_total, 0.0)
    maximum_total = max(maximum_total, minimum_total)

    materials = project_eurocode_material_input(project, es_mpa=es_mpa)
    modular_ratio = materials.es_mpa / materials.ecm_mpa
    minimum_state = cracked_t_section_sls(
        section.effective_flange_width_m,
        section.flange_thickness_m,
        section.web_width_m,
        section.total_depth_m,
        section.steel_area_mm2,
        section.effective_depth_m,
        modular_ratio,
        minimum_total,
    )
    maximum_state = cracked_t_section_sls(
        section.effective_flange_width_m,
        section.flange_thickness_m,
        section.web_width_m,
        section.total_depth_m,
        section.steel_area_mm2,
        section.effective_depth_m,
        modular_ratio,
        maximum_total,
    )
    steel_range = max(
        maximum_state.steel_stress_mpa - minimum_state.steel_stress_mpa,
        0.0,
    )

    x_mm = maximum_state.neutral_axis_from_top_mm
    inertia_mm4 = maximum_state.second_moment_mm4
    concrete_min = minimum_total * 1.0e6 * x_mm / inertia_mm4
    concrete_max = maximum_total * 1.0e6 * x_mm / inertia_mm4

    minimum_case = (
        "unloaded-zero baseline"
        if traffic.minimum_case_id is None
        else f"case {traffic.minimum_case_id}"
    )
    maximum_case = (
        "unloaded-zero baseline"
        if traffic.maximum_case_id is None
        else f"case {traffic.maximum_case_id}"
    )
    source = (
        f"Native full-width EN 1991-2 FLM3 grillage, girder {girder_index}, "
        f"x={traffic.section_position_m:.6g} m, vehicle centre "
        f"y={search.vehicle_centre_y_m:.6g} m; range {minimum_case} to {maximum_case}"
    )
    concrete_input = (
        ConcreteFatigueInput(
            sigma_c_max_mpa=concrete_max,
            sigma_c_min_mpa=concrete_min,
            gamma_c=concrete_gamma_c,
            alpha_cc=concrete_alpha_cc,
            k1=concrete_k1,
            beta_cc_t0=concrete_beta_cc_t0,
        )
        if check_concrete
        else None
    )
    fatigue = run_project_eurocode_fatigue(
        project,
        fatigue=ProjectFatigueInput(
            source_description=source,
            reinforcement=ReinforcementFatigueInput(
                reference_stress_range_mpa=steel_range,
                lambda_s=lambda_s,
                characteristic_fatigue_strength_mpa=characteristic_fatigue_strength_mpa,
                gamma_s_fat=gamma_s_fat,
                phi_fat=phi_fat,
            ),
            concrete=concrete_input,
        ),
    )
    return NativeFLM3TGirderFatigueResult(
        girder_index=girder_index,
        traffic_range=traffic,
        permanent_moment_knm=permanent_moment,
        minimum_total_moment_knm=minimum_total,
        maximum_total_moment_knm=maximum_total,
        reference_steel_stress_range_mpa=steel_range,
        minimum_concrete_compression_mpa=concrete_min,
        maximum_concrete_compression_mpa=concrete_max,
        fatigue=fatigue,
        status=(
            "Simple-span T-girder fatigue derived from a dedicated native full-width FLM3 "
            "moving analysis, not LM1. Longitudinal reinforcement and concrete compression "
            "are checked; fatigue-lane/NA choices, shear-reinforcement fatigue, local deck "
            "fatigue and independent MIDAS/STAAD validation remain explicit later scope."
        ),
    )
