from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from rc_bridge.analysis.grillage_solver import (
    GrillageAnalysisResult,
    solve_vertical_grillage,
)
from rc_bridge.analysis.moving_loads import positioned_axles
from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    composite_section_total_depth_m,
)
from rc_bridge.codes.eurocode.fatigue_traffic import (
    fatigue_load_model_3,
    notional_fatigue_lane_placements,
)
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_cracking import cracked_t_section_sls
from rc_bridge.design.eurocode_fatigue import (
    ReinforcementFatigueResult,
    reinforcement_fatigue_check,
)
from rc_bridge.design.eurocode_layered_section import cracked_layered_section_sls
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import (
    GrillagePointLoad,
    GrillageSectionProperties,
    GrillageStiffnessModifiers,
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
    vehicle_centre_y_m: float
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
class NativeFLM3GirderShearRange:
    """Governing signed FLM3 shear range at one physical girder section."""

    girder_index: int
    y_m: float
    section_position_m: float
    minimum_shear_kn: float
    maximum_shear_kn: float
    shear_range_kn: float
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
    vehicle_centre_y_m: float | None
    axle_load_factor: float
    movement_step_m: float
    section_step_m: float
    status: str
    shears: tuple[NativeFLM3GirderShearRange, ...] = ()
    vehicle_centres_y_m: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.vehicle_centres_y_m and self.vehicle_centre_y_m is not None:
            object.__setattr__(
                self,
                "vehicle_centres_y_m",
                (float(self.vehicle_centre_y_m),),
            )

    def range_for_girder(self, girder_index: int) -> NativeFLM3GirderMomentRange:
        match = next(
            (item for item in self.girders if item.girder_index == girder_index),
            None,
        )
        if match is None:
            raise IndexError("girder_index is outside the native FLM3 result.")
        return match

    def shear_range_for_girder(self, girder_index: int) -> NativeFLM3GirderShearRange:
        match = next(
            (item for item in self.shears if item.girder_index == girder_index),
            None,
        )
        if match is None:
            raise IndexError("girder_index is outside the native FLM3 shear result.")
        return match


@dataclass(frozen=True)
class NativeFLM3ShearLinkFatigueResult:
    """Conservative vertical-link fatigue check from the native FLM3 shear range."""

    traffic_range: NativeFLM3GirderShearRange
    provided_asw_per_s_mm2_per_m: float
    lever_arm_m: float
    cot_theta: float
    reference_link_stress_range_mpa: float
    fatigue: ReinforcementFatigueResult
    status: str


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
    shear_links: NativeFLM3ShearLinkFatigueResult | None
    status: str


@dataclass(frozen=True)
class NativeFLM3LayeredGirderFatigueResult:
    """EC2 fatigue result for a physical rectangular/T/I layered girder."""

    girder_index: int
    traffic_range: NativeFLM3GirderMomentRange
    permanent_moment_knm: float
    minimum_total_moment_knm: float
    maximum_total_moment_knm: float
    reference_steel_stress_range_mpa: float
    minimum_concrete_compression_mpa: float
    maximum_concrete_compression_mpa: float
    fatigue: ProjectFatigueResult
    shear_links: NativeFLM3ShearLinkFatigueResult | None
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
    shear_link_characteristic_fatigue_strength_mpa: float | None = None
    shear_link_lambda_s: float | None = None
    shear_link_phi_fat: float = 1.0
    shear_link_z_factor: float = 0.9
    shear_link_cot_theta: float = 2.0

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
            self.shear_link_phi_fat,
            self.shear_link_z_factor,
            self.shear_link_cot_theta,
        ) <= 0.0:
            raise ValueError("Native FLM3 fatigue design factors must be positive.")
        if (
            self.shear_link_characteristic_fatigue_strength_mpa is not None
            and self.shear_link_characteristic_fatigue_strength_mpa <= 0.0
        ):
            raise ValueError("Shear-link fatigue strength must be positive when supplied.")
        if self.shear_link_lambda_s is not None and self.shear_link_lambda_s <= 0.0:
            raise ValueError("Shear-link lambda_s must be positive when supplied.")


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


@dataclass
class _ShearRangeState:
    minimum_shear_kn: float = 0.0
    maximum_shear_kn: float = 0.0
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


def _signed_longitudinal_section_candidates(
    case: NativeFLM3CaseResult,
    *,
    target_y_m: float,
    x_m: float,
    tolerance_m: float = 1.0e-9,
) -> tuple[tuple[float, float, int], ...]:
    """Return sagging-positive moment and signed dM/dx shear for one girder."""
    nodes = {node.node_id: node for node in case.model.nodes}
    results = {item.member_id: item for item in case.analysis.members}
    candidates: list[tuple[float, float, int]] = []

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
            raw_i = -result.i_vertical_bending_moment_knm
            raw_j = result.j_vertical_bending_moment_knm
        else:
            x_i = nj.x_m
            x_j = ni.x_m
            raw_i = result.j_vertical_bending_moment_knm
            raw_j = -result.i_vertical_bending_moment_knm

        ratio = (x_m - x_i) / (x_j - x_i)
        ratio = min(max(ratio, 0.0), 1.0)
        moment = -(raw_i + ratio * (raw_j - raw_i))
        shear = -(raw_j - raw_i) / (x_j - x_i)
        if abs(moment) <= 1.0e-10:
            moment = 0.0
        if abs(shear) <= 1.0e-10:
            shear = 0.0
        candidates.append((moment, shear, beam.member_id))

    if not candidates:
        raise RuntimeError(
            f"Native FLM3 section recovery found no longitudinal member at x={x_m:.6g} m."
        )
    return tuple(candidates)


def _signed_longitudinal_moment_candidates(
    case: NativeFLM3CaseResult,
    *,
    target_y_m: float,
    x_m: float,
    tolerance_m: float = 1.0e-9,
) -> tuple[tuple[float, int], ...]:
    return tuple(
        (moment, member_id)
        for moment, _, member_id in _signed_longitudinal_section_candidates(
            case,
            target_y_m=target_y_m,
            x_m=x_m,
            tolerance_m=tolerance_m,
        )
    )


def run_project_native_flm3_grillage_search(
    project: ProjectInput,
    *,
    transverse_stations_m: tuple[float, ...],
    vehicle_centre_y_m: float | None = None,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...] | None = None,
    transverse_section: GrillageSectionProperties | None = None,
    axle_load_factor: float = 1.0,
    stiffness_modifiers: GrillageStiffnessModifiers | None = None,
    movement_step_m: float = 0.5,
    section_step_m: float = 0.5,
    name: str = "EN 1991-2 FLM3 native grillage search",
) -> ProjectNativeFLM3GrillageSearchResult:
    """Move FLM3 across the full bridge grillage and recover per-girder M ranges.

    A supplied vehicle centre analyses one physical transverse line. If it is
    omitted, the solver envelopes every unique left-packed/right-packed
    notional-lane centre that can accommodate the FLM3 wheel pair. This
    automates deterministic lane-centre candidates without pretending to know
    a project-specific slow-lane/National-Annex designation. Each 120 kN axle
    line is represented by two equal wheel loads at 2.0 m wheel spacing.
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
    carriageway_left = float(project.geometry.carriageway_left_edge_m)
    carriageway_right = float(project.geometry.carriageway_right_edge_m)
    if vehicle_centre_y_m is None:
        placements = notional_fatigue_lane_placements(
            carriageway_width_m=float(project.geometry.carriageway_width_m),
            carriageway_offset_m=float(project.geometry.carriageway_offset_m),
            transverse_wheel_spacing_m=vehicle.transverse_wheel_spacing_m,
        )
        vehicle_centres = tuple(item.centre_y_m for item in placements)
    else:
        centre = float(vehicle_centre_y_m)
        wheel_y = (centre - half_wheel_spacing, centre + half_wheel_spacing)
        if (
            wheel_y[0] < carriageway_left - 1.0e-9
            or wheel_y[1] > carriageway_right + 1.0e-9
        ):
            raise ValueError(
                "FLM3 wheel centres must lie inside the physical carriageway; choose an "
                "explicit fatigue-lane vehicle centre consistent with the project/NA."
            )
        vehicle_centres = (centre,)

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
    for centre in vehicle_centres:
        wheel_y = (centre - half_wheel_spacing, centre + half_wheel_spacing)
        for lead in leads:
            active_axles = positioned_axles(vehicle.axle_train, lead, span_m)
            if not any(
                1.0e-9 < axle.position_m < span_m - 1.0e-9
                for axle in active_axles
            ):
                continue
            case_id = len(cases) + 1
            point_loads = tuple(
                GrillagePointLoad(
                    x_m=axle.position_m,
                    y_m=y_m,
                    magnitude_kn=axle.magnitude_kn / 2.0,
                    label=(
                        f"FLM3 case {case_id} centre {centre:.6g} m {axle.label} "
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
                stiffness_modifiers=stiffness_modifiers,
            )
            analysis = solve_vertical_grillage(model)
            cases.append(
                NativeFLM3CaseResult(
                    case_id=case_id,
                    lead_position_m=lead,
                    vehicle_centre_y_m=centre,
                    model=model,
                    analysis=analysis,
                )
            )

    y_coordinates = _girder_y_coordinates(project)
    girder_ranges: list[NativeFLM3GirderMomentRange] = []
    shear_ranges: list[NativeFLM3GirderShearRange] = []
    for girder_index, y_m in enumerate(y_coordinates, start=1):
        moment_states = {x_m: _RangeState() for x_m in reporting_stations}
        shear_states = {x_m: _ShearRangeState() for x_m in reporting_stations}
        for case in cases:
            for x_m in reporting_stations:
                for moment, shear, member_id in _signed_longitudinal_section_candidates(
                    case,
                    target_y_m=y_m,
                    x_m=x_m,
                ):
                    moment_state = moment_states[x_m]
                    if moment < moment_state.minimum_moment_knm:
                        moment_state.minimum_moment_knm = moment
                        moment_state.minimum_case_id = case.case_id
                        moment_state.minimum_lead_position_m = case.lead_position_m
                        moment_state.minimum_member_id = member_id
                    if moment > moment_state.maximum_moment_knm:
                        moment_state.maximum_moment_knm = moment
                        moment_state.maximum_case_id = case.case_id
                        moment_state.maximum_lead_position_m = case.lead_position_m
                        moment_state.maximum_member_id = member_id

                    shear_state = shear_states[x_m]
                    if shear < shear_state.minimum_shear_kn:
                        shear_state.minimum_shear_kn = shear
                        shear_state.minimum_case_id = case.case_id
                        shear_state.minimum_lead_position_m = case.lead_position_m
                        shear_state.minimum_member_id = member_id
                    if shear > shear_state.maximum_shear_kn:
                        shear_state.maximum_shear_kn = shear
                        shear_state.maximum_case_id = case.case_id
                        shear_state.maximum_lead_position_m = case.lead_position_m
                        shear_state.maximum_member_id = member_id

        governing_x = max(
            reporting_stations,
            key=lambda value: (
                moment_states[value].maximum_moment_knm
                - moment_states[value].minimum_moment_knm
            ),
        )
        state = moment_states[governing_x]
        girder_ranges.append(
            NativeFLM3GirderMomentRange(
                girder_index=girder_index,
                y_m=y_m,
                section_position_m=governing_x,
                minimum_moment_knm=state.minimum_moment_knm,
                maximum_moment_knm=state.maximum_moment_knm,
                moment_range_knm=state.maximum_moment_knm - state.minimum_moment_knm,
                minimum_case_id=state.minimum_case_id,
                maximum_case_id=state.maximum_case_id,
                minimum_lead_position_m=state.minimum_lead_position_m,
                maximum_lead_position_m=state.maximum_lead_position_m,
                minimum_member_id=state.minimum_member_id,
                maximum_member_id=state.maximum_member_id,
            )
        )

        governing_shear_x = max(
            reporting_stations,
            key=lambda value: (
                shear_states[value].maximum_shear_kn
                - shear_states[value].minimum_shear_kn
            ),
        )
        shear_state = shear_states[governing_shear_x]
        shear_ranges.append(
            NativeFLM3GirderShearRange(
                girder_index=girder_index,
                y_m=y_m,
                section_position_m=governing_shear_x,
                minimum_shear_kn=shear_state.minimum_shear_kn,
                maximum_shear_kn=shear_state.maximum_shear_kn,
                shear_range_kn=shear_state.maximum_shear_kn - shear_state.minimum_shear_kn,
                minimum_case_id=shear_state.minimum_case_id,
                maximum_case_id=shear_state.maximum_case_id,
                minimum_lead_position_m=shear_state.minimum_lead_position_m,
                maximum_lead_position_m=shear_state.maximum_lead_position_m,
                minimum_member_id=shear_state.minimum_member_id,
                maximum_member_id=shear_state.maximum_member_id,
            )
        )

    explicit_centre = vehicle_centres[0] if len(vehicle_centres) == 1 else None
    return ProjectNativeFLM3GrillageSearchResult(
        cases=tuple(cases),
        girders=tuple(girder_ranges),
        shears=tuple(shear_ranges),
        span_m=span_m,
        vehicle_centre_y_m=explicit_centre,
        vehicle_centres_y_m=vehicle_centres,
        axle_load_factor=axle_load_factor,
        movement_step_m=movement_step_m,
        section_step_m=section_step_m,
        status=(
            "Full-width native EN 1991-2 FLM3 moving-vehicle grillage search with "
            "per-girder moment and shear ranges. A supplied vehicle centre is preserved; "
            "otherwise every unique left/right-packed notional-lane centre is enveloped. "
            "The candidate envelope does not replace project/National-Annex slow-lane "
            "identification. Independent external validation remains pending."
        ),
    )


def _run_native_flm3_shear_link_fatigue(
    *,
    search: ProjectNativeFLM3GrillageSearchResult,
    girder_index: int,
    provided_asw_per_s_mm2_per_m: float | None,
    effective_depth_m: float,
    characteristic_fatigue_strength_mpa: float | None,
    lambda_s: float,
    gamma_s_fat: float,
    phi_fat: float,
    z_factor: float,
    cot_theta: float,
) -> NativeFLM3ShearLinkFatigueResult | None:
    """Recover a conservative vertical-link stress range from the FLM3 V range."""
    if characteristic_fatigue_strength_mpa is None:
        return None
    if provided_asw_per_s_mm2_per_m is None or provided_asw_per_s_mm2_per_m <= 0.0:
        raise ValueError(
            "Shear-link fatigue requires the actual provided A_sw/s for the girder."
        )
    if not search.shears:
        raise ValueError(
            "Shear-link fatigue requires native FLM3 shear ranges; legacy moment-only "
            "fatigue fixtures cannot be used for this check."
        )
    if min(effective_depth_m, lambda_s, gamma_s_fat, phi_fat, z_factor, cot_theta) <= 0.0:
        raise ValueError("Shear-link fatigue geometry and factors must be positive.")

    traffic = search.shear_range_for_girder(girder_index)
    lever_arm_m = z_factor * effective_depth_m
    asw_per_s_mm2_per_mm = provided_asw_per_s_mm2_per_m / 1000.0
    reference_stress = (
        traffic.shear_range_kn
        * 1000.0
        / (asw_per_s_mm2_per_mm * lever_arm_m * 1000.0 * cot_theta)
    )
    fatigue = reinforcement_fatigue_check(
        reference_stress_range_mpa=reference_stress,
        lambda_s=lambda_s,
        characteristic_fatigue_strength_mpa=characteristic_fatigue_strength_mpa,
        gamma_s_fat=gamma_s_fat,
        phi_fat=phi_fat,
    )
    return NativeFLM3ShearLinkFatigueResult(
        traffic_range=traffic,
        provided_asw_per_s_mm2_per_m=provided_asw_per_s_mm2_per_m,
        lever_arm_m=lever_arm_m,
        cot_theta=cot_theta,
        reference_link_stress_range_mpa=reference_stress,
        fatigue=fatigue,
        status=(
            "Native FLM3 vertical-link fatigue using the full cyclic shear range and "
            "actual provided A_sw/s. The full-truss stress-range assumption is "
            "conservative; independent clause/software validation remains required."
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
    shear_link_characteristic_fatigue_strength_mpa: float | None = None,
    shear_link_lambda_s: float | None = None,
    shear_link_phi_fat: float = 1.0,
    shear_link_z_factor: float = 0.9,
    shear_link_cot_theta: float = 2.0,
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

    concrete_min = (
        minimum_total
        * 1.0e6
        * minimum_state.neutral_axis_from_top_mm
        / minimum_state.second_moment_mm4
    )
    concrete_max = (
        maximum_total
        * 1.0e6
        * maximum_state.neutral_axis_from_top_mm
        / maximum_state.second_moment_mm4
    )

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
        f"x={traffic.section_position_m:.6g} m, vehicle centres "
        f"{','.join(f'{value:.6g}' for value in search.vehicle_centres_y_m)} m; "
        f"range {minimum_case} to {maximum_case}"
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
    shear_links = _run_native_flm3_shear_link_fatigue(
        search=search,
        girder_index=girder_index,
        provided_asw_per_s_mm2_per_m=section.provided_shear_asw_per_s_mm2_per_m,
        effective_depth_m=section.effective_depth_m,
        characteristic_fatigue_strength_mpa=(
            shear_link_characteristic_fatigue_strength_mpa
        ),
        lambda_s=shear_link_lambda_s or lambda_s,
        gamma_s_fat=gamma_s_fat,
        phi_fat=shear_link_phi_fat,
        z_factor=shear_link_z_factor,
        cot_theta=shear_link_cot_theta,
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
        shear_links=shear_links,
        status=(
            "Simple-span T-girder fatigue derived from a dedicated native full-width FLM3 "
            "moving analysis, not LM1. Longitudinal reinforcement and concrete compression "
            "are checked; vertical-link fatigue is also checked when an actual A_sw/s and "
            "link fatigue category are supplied. Local deck fatigue and independent "
            "MIDAS/STAAD validation remain explicit later scope."
        ),
    )



def run_project_layered_girder_fatigue_from_native_flm3(
    project: ProjectInput,
    *,
    search: ProjectNativeFLM3GrillageSearchResult,
    girder_index: int,
    section: LayeredGirderDesignInput,
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
    shear_link_characteristic_fatigue_strength_mpa: float | None = None,
    shear_link_lambda_s: float | None = None,
    shear_link_phi_fat: float = 1.0,
    shear_link_z_factor: float = 0.9,
    shear_link_cot_theta: float = 2.0,
) -> NativeFLM3LayeredGirderFatigueResult:
    """Run longitudinal reinforcement/concrete fatigue for rectangular/T/I profiles.

    The native FLM3 range is evaluated at one co-located girder section. Cracked
    transformed properties are recovered from the same physical layered section
    used by the generic ULS/SLS workflow, including any nonparticipating deck
    gap. This remains a positive-bending simple-span adapter.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native FLM3 layered fatigue design currently supports Eurocode only.")
    if project.geometry.girder_profile is None:
        raise ValueError("Layered FLM3 fatigue requires a complete physical girder profile.")
    if abs(search.span_m - float(project.geometry.span_lengths_m[0])) > 1.0e-9:
        raise ValueError("Native FLM3 search span does not match the project.")
    if len(search.girders) != int(project.geometry.girder_count):
        raise ValueError("Native FLM3 search girder count does not match the project.")
    total_depth_m = composite_section_total_depth_m(project.geometry)
    if section.effective_depth_m >= total_depth_m:
        raise ValueError("Fatigue tension steel depth must lie inside the physical section.")

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
            "layered positive-bending fatigue model is not valid for hogging."
        )
    minimum_total = max(minimum_total, 0.0)
    maximum_total = max(maximum_total, minimum_total)

    materials = project_eurocode_material_input(project, es_mpa=es_mpa)
    modular_ratio = materials.es_mpa / materials.ecm_mpa
    layers = composite_concrete_layers(
        project.geometry,
        slab_width_m=section.composite_slab_width_m,
    )
    minimum_state = cracked_layered_section_sls(
        layers=layers,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=minimum_total,
    )
    maximum_state = cracked_layered_section_sls(
        layers=layers,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=maximum_total,
    )
    steel_range = max(
        maximum_state.steel_stress_mpa - minimum_state.steel_stress_mpa,
        0.0,
    )
    concrete_min = (
        minimum_total
        * 1.0e6
        * minimum_state.neutral_axis_from_top_mm
        / minimum_state.second_moment_mm4
    )
    concrete_max = (
        maximum_total
        * 1.0e6
        * maximum_state.neutral_axis_from_top_mm
        / maximum_state.second_moment_mm4
    )

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
        f"Native full-width EN 1991-2 FLM3 layered {project.geometry.section_type.value} "
        f"girder {girder_index}, x={traffic.section_position_m:.6g} m, vehicle centres "
        f"{','.join(f'{value:.6g}' for value in search.vehicle_centres_y_m)} m; "
        f"range {minimum_case} to {maximum_case}"
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
    shear_links = _run_native_flm3_shear_link_fatigue(
        search=search,
        girder_index=girder_index,
        provided_asw_per_s_mm2_per_m=section.provided_shear_asw_per_s_mm2_per_m,
        effective_depth_m=section.effective_depth_m,
        characteristic_fatigue_strength_mpa=(
            shear_link_characteristic_fatigue_strength_mpa
        ),
        lambda_s=shear_link_lambda_s or lambda_s,
        gamma_s_fat=gamma_s_fat,
        phi_fat=shear_link_phi_fat,
        z_factor=shear_link_z_factor,
        cot_theta=shear_link_cot_theta,
    )
    return NativeFLM3LayeredGirderFatigueResult(
        girder_index=girder_index,
        traffic_range=traffic,
        permanent_moment_knm=permanent_moment,
        minimum_total_moment_knm=minimum_total,
        maximum_total_moment_knm=maximum_total,
        reference_steel_stress_range_mpa=steel_range,
        minimum_concrete_compression_mpa=concrete_min,
        maximum_concrete_compression_mpa=concrete_max,
        fatigue=fatigue,
        shear_links=shear_links,
        status=(
            "Simple-span rectangular/T/I layered-section fatigue derived from dedicated "
            "native full-width FLM3 traffic, not LM1. Longitudinal reinforcement and "
            "concrete compression are checked; vertical-link fatigue is also checked when "
            "actual A_sw/s and a link fatigue category are supplied. Local deck fatigue "
            "and independent external validation remain explicit scope."
        ),
    )
