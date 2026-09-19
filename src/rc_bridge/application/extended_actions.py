from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import ceil

from rc_bridge.analysis.grillage_effects import native_grillage_traffic_envelope
from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
)
from rc_bridge.analysis.simple_span import (
    DistributedLoadSegment,
    simple_span_distributed_load_response,
)
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    lm1_characteristic_lane_load,
    notional_lane_layout,
)
from rc_bridge.codes.eurocode.materials import secant_elastic_modulus_mpa
from rc_bridge.core.models import PermanentActionStage, ProjectInput, SupportSystem
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillagePointLoad,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    run_project_native_lm1_grillage_search,
)
from rc_bridge.workflow.project_bridge import (
    girder_deck_tributary_width_m,
    girder_permanent_load_segments,
)


@dataclass(frozen=True)
class ExtendedActionSettings:
    """Application settings for the six additional bridge-action families.

    Recommended first-generation Eurocode reference values are used only where
    they are stable and transparent (LM2, pedestrian UDL, braking bounds and the
    simple 100 kN safety-barrier reference action). Climate, restraint and
    construction execution values remain explicit project inputs.
    """

    # 1. Braking / acceleration
    braking_enabled: bool = True
    braking_alpha_q1: float = 1.0
    braking_alpha_Q1: float = 1.0
    braking_loaded_length_m: float | None = None

    # 2. Thermal actions
    thermal_enabled: bool = True
    thermal_alpha_per_c: float = 10.0e-6
    thermal_uniform_expansion_delta_c: float = 0.0
    thermal_uniform_contraction_delta_c: float = 0.0
    thermal_gradient_heat_c: float = 15.0
    thermal_gradient_cool_c: float = 8.0
    thermal_longitudinal_restraint_fraction: float = 0.0

    # 3. Pedestrian / footway loading
    pedestrian_enabled: bool = True
    pedestrian_load_kn_m2: float = 5.0
    pedestrian_reduced_with_lm1_kn_m2: float = 3.0
    left_footway_width_m: float = 0.0
    right_footway_width_m: float = 0.0

    # EN 1991-2 gr2 frequent LM1 component accompanying horizontal traffic.
    gr2_lm1_tandem_factor: float = 0.75
    gr2_lm1_udl_factor: float = 0.40

    # 4. LM2 local axle
    lm2_enabled: bool = True
    lm2_beta_Q: float = 1.0
    lm2_axle_load_kn: float = 400.0
    lm2_wheel_track_m: float = 2.0
    lm2_contact_length_m: float = 0.35
    lm2_contact_width_m: float = 0.60
    lm2_longitudinal_step_m: float = 1.0
    lm2_transverse_step_m: float = 0.5

    # 5. Vehicle impact on safety barrier
    barrier_impact_enabled: bool = True
    barrier_transverse_force_kn: float = 100.0
    barrier_load_height_m: float = 0.50
    barrier_vertical_factor: float = 0.75
    barrier_alpha_Q1: float = 1.0

    # Simple longitudinal bearing/restraint design path. Zero capacity means
    # demand-only reporting rather than a fabricated pass/fail check.
    bearing_longitudinal_capacity_per_bearing_kn: float = 0.0
    bearing_movement_capacity_mm: float = 0.0
    barrier_transverse_resistance_kn: float = 0.0
    barrier_base_moment_resistance_knm: float = 0.0

    # Wind action assessment. The project/basic wind speed is deliberately an
    # explicit input; zero means not yet specified.
    wind_enabled: bool = True
    wind_basic_velocity_m_s: float = 0.0
    wind_air_density_kg_m3: float = 1.25
    wind_exposure_factor: float = 1.0
    wind_transverse_force_coefficient: float = 1.30
    wind_vertical_force_coefficient: float = 0.0
    wind_loaded_height_m: float = 0.0
    bearing_transverse_capacity_per_bearing_kn: float = 0.0

    # 6. Construction-stage actions
    construction_enabled: bool = True
    construction_execution_udl_kn_m2: float = 0.0

    def __post_init__(self) -> None:
        positive = (
            self.braking_alpha_q1,
            self.braking_alpha_Q1,
            self.thermal_alpha_per_c,
            self.pedestrian_load_kn_m2,
            self.pedestrian_reduced_with_lm1_kn_m2,
            self.gr2_lm1_tandem_factor,
            self.gr2_lm1_udl_factor,
            self.lm2_beta_Q,
            self.lm2_axle_load_kn,
            self.lm2_wheel_track_m,
            self.lm2_contact_length_m,
            self.lm2_contact_width_m,
            self.lm2_longitudinal_step_m,
            self.lm2_transverse_step_m,
            self.barrier_transverse_force_kn,
            self.barrier_load_height_m,
            self.barrier_vertical_factor,
            self.barrier_alpha_Q1,
            self.wind_air_density_kg_m3,
            self.wind_exposure_factor,
            self.wind_transverse_force_coefficient,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("Enabled bridge-action reference values must be positive.")
        nonnegative = (
            self.thermal_uniform_expansion_delta_c,
            self.thermal_uniform_contraction_delta_c,
            self.thermal_gradient_heat_c,
            self.thermal_gradient_cool_c,
            self.left_footway_width_m,
            self.right_footway_width_m,
            self.construction_execution_udl_kn_m2,
            self.bearing_longitudinal_capacity_per_bearing_kn,
            self.bearing_movement_capacity_mm,
            self.barrier_transverse_resistance_kn,
            self.barrier_base_moment_resistance_knm,
            self.wind_basic_velocity_m_s,
            self.wind_vertical_force_coefficient,
            self.wind_loaded_height_m,
            self.bearing_transverse_capacity_per_bearing_kn,
        )
        if any(value < 0.0 for value in nonnegative):
            raise ValueError("Bridge-action magnitudes/widths cannot be negative.")
        if self.braking_loaded_length_m is not None and self.braking_loaded_length_m <= 0.0:
            raise ValueError("braking_loaded_length_m must be positive when supplied.")
        if not 0.0 <= self.thermal_longitudinal_restraint_fraction <= 1.0:
            raise ValueError(
                "thermal_longitudinal_restraint_fraction must lie between 0 and 1."
            )


@dataclass(frozen=True)
class BrakingActionResult:
    characteristic_force_kn: float
    uncapped_force_kn: float
    minimum_force_kn: float
    maximum_force_kn: float
    loaded_length_m: float
    lane_width_m: float
    status: str


@dataclass(frozen=True)
class ThermalActionResult:
    expansion_movement_mm: float
    contraction_movement_mm: float
    heat_gradient_curvature_per_m: float
    cool_gradient_curvature_per_m: float
    heat_gradient_free_midspan_mm: float
    cool_gradient_free_midspan_mm: float
    full_restraint_expansion_force_kn: float
    full_restraint_contraction_force_kn: float
    modelled_restraint_expansion_force_kn: float
    modelled_restraint_contraction_force_kn: float
    climate_input_complete: bool
    status: str


@dataclass(frozen=True)
class GirderActionEnvelope:
    girder_index: int
    y_m: float
    effects: LoadEffects
    case_id: int


@dataclass(frozen=True)
class PedestrianActionResult:
    applied: bool
    loaded_area_m2: float
    total_characteristic_load_kn: float
    girders: tuple[GirderActionEnvelope, ...]
    status: str
    model: VerificationModel | None = None


@dataclass(frozen=True)
class Gr2FrequentLM1Result:
    search: ProjectNativeLM1GrillageSearchResult
    tandem_factor: float
    udl_factor: float
    status: str


@dataclass(frozen=True)
class LM2ActionResult:
    evaluated_case_count: int
    wheel_load_kn: float
    axle_load_kn: float
    contact_pressure_kn_m2: float
    girders: tuple[GirderActionEnvelope, ...]
    governing_positions: tuple[tuple[int, float, float], ...]
    governing_moment_positions: tuple[tuple[int, float, float], ...]
    governing_shear_positions: tuple[tuple[int, float, float], ...]
    governing_torsion_positions: tuple[tuple[int, float, float], ...]
    status: str
    governing_models: tuple[VerificationModel, ...] = ()


@dataclass(frozen=True)
class BarrierImpactResult:
    transverse_characteristic_force_kn: float
    accompanying_vertical_wheel_load_kn: float
    barrier_base_moment_knm: float
    status: str


@dataclass(frozen=True)
class WindActionResult:
    basic_velocity_m_s: float
    basic_dynamic_pressure_kn_m2: float
    effective_pressure_kn_m2: float
    projected_height_m: float
    transverse_characteristic_force_kn: float
    transverse_line_load_kn_m: float
    vertical_characteristic_force_kn: float
    vertical_pressure_kn_m2: float
    overturning_reference_moment_knm: float
    input_complete: bool
    status: str


@dataclass(frozen=True)
class ConstructionStageGirderResult:
    girder_index: int
    stage: PermanentActionStage
    characteristic_max_moment_knm: float
    characteristic_max_abs_shear_kn: float
    execution_udl_kn_m: float
    status: str


@dataclass(frozen=True)
class ConstructionActionResult:
    girders: tuple[ConstructionStageGirderResult, ...]
    status: str


@dataclass(frozen=True)
class ExtendedActionSuite:
    braking: BrakingActionResult | None
    thermal: ThermalActionResult | None
    pedestrian: PedestrianActionResult | None
    gr2_frequent_lm1: Gr2FrequentLM1Result | None
    lm2: LM2ActionResult | None
    barrier_impact: BarrierImpactResult | None
    wind: WindActionResult | None
    construction: ConstructionActionResult | None

    @property
    def unresolved_inputs(self) -> tuple[str, ...]:
        items: list[str] = []
        if self.thermal is not None and not self.thermal.climate_input_complete:
            items.append("thermal uniform expansion/contraction ranges")
        if self.pedestrian is not None and not self.pedestrian.applied:
            items.append("footway widths for pedestrian loading")
        if self.wind is not None and not self.wind.input_complete:
            items.append("project/basic wind speed")
        return tuple(items)


def _grid_stations(total_length_m: float, spacing_m: float) -> tuple[float, ...]:
    if total_length_m <= 0.0 or spacing_m <= 0.0:
        raise ValueError("Bridge length and grid spacing must be positive.")
    count = max(1, ceil(total_length_m / spacing_m))
    values = {0.0, 0.5 * total_length_m, total_length_m}
    for index in range(1, count):
        values.add(min(total_length_m, index * spacing_m))
    return tuple(sorted(round(value, 12) for value in values))


def braking_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
) -> BrakingActionResult:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    loaded_length = settings.braking_loaded_length_m or total_length
    if loaded_length > total_length + 1.0e-9:
        raise ValueError("Braking loaded length cannot exceed the bridge length.")
    layout = notional_lane_layout(float(project.geometry.carriageway_width_m))
    factors = LM1AdjustmentFactors(
        alpha_q1=settings.braking_alpha_q1,
        alpha_Q1=settings.braking_alpha_Q1,
    )
    lane1 = lm1_characteristic_lane_load(1, factors)
    raw = (
        0.6 * (2.0 * lane1.axle_load_kn)
        + 0.10 * lane1.udl_kn_m2 * layout.lane_width_m * loaded_length
    )
    minimum = 180.0 * settings.braking_alpha_Q1
    maximum = 900.0
    characteristic = min(max(raw, minimum), maximum)
    return BrakingActionResult(
        characteristic_force_kn=characteristic,
        uncapped_force_kn=raw,
        minimum_force_kn=minimum,
        maximum_force_kn=maximum,
        loaded_length_m=loaded_length,
        lane_width_m=layout.lane_width_m,
        status=(
            "EN 1991-2 first-generation braking/acceleration characteristic action. "
            "Force acts longitudinally at carriageway level; the current vertical grillage "
            "does not convert it to deck/bearing/substructure stresses. Both signs are required."
        ),
    )


def thermal_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
) -> ThermalActionResult:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    total_depth = (
        float(project.geometry.girder_depth_m)
        + float(project.geometry.physical_deck_depth_m)
    )
    if total_depth <= 0.0:
        raise ValueError("Thermal action requires a positive structural depth.")
    profile_area = project.geometry.girder_profile_area_m2
    if profile_area is None or profile_area <= 0.0:
        raise ValueError("Thermal action requires a complete physical girder profile.")
    tributary_widths = tuple(
        girder_deck_tributary_width_m(project, girder_index=index)
        for index in range(1, int(project.geometry.girder_count) + 1)
    )
    deck_depth = float(project.geometry.composite_flange_depth_m)
    total_area = (
        int(project.geometry.girder_count) * float(profile_area)
        + deck_depth * sum(tributary_widths)
    )
    e_mpa = (
        float(project.materials.elastic_modulus_mpa)
        if project.materials.elastic_modulus_mpa is not None
        else secant_elastic_modulus_mpa(float(project.materials.fck_mpa))
    )
    e_kn_m2 = e_mpa * 1000.0
    alpha = settings.thermal_alpha_per_c
    expansion = alpha * settings.thermal_uniform_expansion_delta_c * total_length
    contraction = alpha * settings.thermal_uniform_contraction_delta_c * total_length
    k_heat = alpha * settings.thermal_gradient_heat_c / total_depth
    k_cool = alpha * settings.thermal_gradient_cool_c / total_depth
    heat_camber = k_heat * total_length**2 / 8.0
    cool_camber = k_cool * total_length**2 / 8.0
    full_exp = (
        e_kn_m2
        * total_area
        * alpha
        * settings.thermal_uniform_expansion_delta_c
    )
    full_con = (
        e_kn_m2
        * total_area
        * alpha
        * settings.thermal_uniform_contraction_delta_c
    )
    restraint = settings.thermal_longitudinal_restraint_fraction
    climate_complete = (
        settings.thermal_uniform_expansion_delta_c > 0.0
        and settings.thermal_uniform_contraction_delta_c > 0.0
    )
    return ThermalActionResult(
        expansion_movement_mm=expansion * 1000.0,
        contraction_movement_mm=contraction * 1000.0,
        heat_gradient_curvature_per_m=k_heat,
        cool_gradient_curvature_per_m=k_cool,
        heat_gradient_free_midspan_mm=heat_camber * 1000.0,
        cool_gradient_free_midspan_mm=cool_camber * 1000.0,
        full_restraint_expansion_force_kn=full_exp,
        full_restraint_contraction_force_kn=full_con,
        modelled_restraint_expansion_force_kn=restraint * full_exp,
        modelled_restraint_contraction_force_kn=restraint * full_con,
        climate_input_complete=climate_complete,
        status=(
            "EN 1991-1-5 thermal kinematics. Concrete-beam linear gradients default to "
            "15 C top-warm / 8 C bottom-warm reference values; surfacing/National Annex "
            "and project climate ranges must be confirmed. Uniform restraint force is a "
            "transparent benchmark using the user-specified restraint fraction, not a "
            "bearing/substructure analysis."
        ),
    )


def _effects_from_native_envelope(
    model,
    analysis,
    *,
    case_id: int,
) -> tuple[GirderActionEnvelope, ...]:
    envelope = native_grillage_traffic_envelope(model, analysis)
    return tuple(
        GirderActionEnvelope(
            girder_index=item.girder_index,
            y_m=item.y_m,
            effects=item.effects,
            case_id=case_id,
        )
        for item in envelope.details
    )


def pedestrian_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
    *,
    grid_spacing_m: float,
) -> PedestrianActionResult:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    left_width = settings.left_footway_width_m
    right_width = settings.right_footway_width_m
    if left_width <= 0.0 and right_width <= 0.0:
        return PedestrianActionResult(
            applied=False,
            loaded_area_m2=0.0,
            total_characteristic_load_kn=0.0,
            girders=(),
            status=(
                "Pedestrian load engine is available, but no footway width is defined. "
                "Enter the usable left/right footway widths; barrier/parapet zones are not "
                "silently treated as pedestrian area."
            ),
        )

    deck_left = -float(project.geometry.deck_width_m) / 2.0
    deck_right = -deck_left
    carriageway_left = float(project.geometry.carriageway_left_edge_m)
    carriageway_right = float(project.geometry.carriageway_right_edge_m)
    patches: list[GrillageAreaLoad] = []
    loaded_area = 0.0
    if left_width > 0.0:
        y_end = carriageway_left
        y_start = y_end - left_width
        if y_start < deck_left - 1.0e-9:
            raise ValueError("Left footway width extends outside the physical deck.")
        patches.append(
            GrillageAreaLoad(
                0.0,
                total_length,
                y_start,
                y_end,
                settings.pedestrian_load_kn_m2,
                "EN 1991-2 left footway pedestrian UDL",
            )
        )
        loaded_area += left_width * total_length
    if right_width > 0.0:
        y_start = carriageway_right
        y_end = y_start + right_width
        if y_end > deck_right + 1.0e-9:
            raise ValueError("Right footway width extends outside the physical deck.")
        patches.append(
            GrillageAreaLoad(
                0.0,
                total_length,
                y_start,
                y_end,
                settings.pedestrian_load_kn_m2,
                "EN 1991-2 right footway pedestrian UDL",
            )
        )
        loaded_area += right_width * total_length

    model = build_project_grillage_verification_model(
        project,
        transverse_stations_m=_grid_stations(total_length, grid_spacing_m),
        load_case=GrillageVerificationLoadCase(
            name="EN 1991-2 pedestrian footway UDL",
            area_loads=tuple(patches),
        ),
    )
    prepared = prepare_vertical_grillage(model)
    analysis = solve_prepared_vertical_grillage(prepared, model)
    return PedestrianActionResult(
        applied=True,
        loaded_area_m2=loaded_area,
        total_characteristic_load_kn=loaded_area * settings.pedestrian_load_kn_m2,
        girders=_effects_from_native_envelope(model, analysis, case_id=1),
        status=(
            "Characteristic pedestrian/footway UDL solved on the physical final-stage "
            "vertical grillage. Traffic-group simultaneity and combination factors remain "
            "separate from this characteristic load case."
        ),
        model=model,
    )


def _scan_positions(
    start: float,
    end: float,
    step: float,
) -> tuple[float, ...]:
    if end < start:
        return ()
    values = {start, end, 0.5 * (start + end)}
    current = start
    while current <= end + 1.0e-9:
        values.add(min(current, end))
        current += step
    return tuple(sorted(round(value, 12) for value in values))


def gr2_frequent_lm1_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
    *,
    grid_spacing_m: float,
    longitudinal_step_m: float,
    max_exhaustive_tandem_combinations: int,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Gr2FrequentLM1Result:
    """Run the EN 1991-2 gr2 accompanying frequent LM1 vertical component.

    TS and UDL are reduced independently; this is intentionally a new native
    search rather than scaling a characteristic LM1 envelope after the fact,
    because the different TS/UDL factors can change the governing placement.
    """

    f_ts = settings.gr2_lm1_tandem_factor
    f_udl = settings.gr2_lm1_udl_factor
    factors = LM1AdjustmentFactors(
        alpha_q1=f_udl,
        alpha_q2=f_udl,
        alpha_q3=f_udl,
        alpha_q_other=f_udl,
        alpha_q_remaining=f_udl,
        alpha_Q1=f_ts,
        alpha_Q2=f_ts,
        alpha_Q3=f_ts,
    )
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    search = run_project_native_lm1_grillage_search(
        project,
        transverse_stations_m=_grid_stations(total_length, grid_spacing_m),
        factors=factors,
        longitudinal_step_m=longitudinal_step_m,
        max_exhaustive_tandem_combinations=max_exhaustive_tandem_combinations,
        progress_callback=progress_callback,
        retain_all_cases=False,
        name="EN 1991-2 gr2 frequent LM1 vertical component",
    )
    return Gr2FrequentLM1Result(
        search=search,
        tandem_factor=f_ts,
        udl_factor=f_udl,
        status=(
            "Native full-width EN 1991-2 gr2 frequent LM1 vertical component; "
            "TS and UDL are reduced separately before moving-load search."
        ),
    )


def lm2_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
    *,
    grid_spacing_m: float,
    progress_callback: Callable[[int, int], None] | None = None,
) -> LM2ActionResult:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    carriageway_left = float(project.geometry.carriageway_left_edge_m)
    carriageway_right = float(project.geometry.carriageway_right_edge_m)
    half_track = 0.5 * settings.lm2_wheel_track_m
    center_left = carriageway_left + half_track
    center_right = carriageway_right - half_track
    if center_right < center_left - 1.0e-9:
        raise ValueError("Carriageway is too narrow for the configured LM2 wheel track.")

    x_positions = _scan_positions(
        0.0,
        total_length,
        settings.lm2_longitudinal_step_m,
    )
    y_centers = _scan_positions(
        center_left,
        center_right,
        settings.lm2_transverse_step_m,
    )
    union_x = tuple(
        sorted(
            {
                *_grid_stations(total_length, grid_spacing_m),
                *x_positions,
            }
        )
    )
    wheel_load = 0.5 * settings.lm2_axle_load_kn * settings.lm2_beta_Q
    axle_load = 2.0 * wheel_load
    contact_pressure = wheel_load / (
        settings.lm2_contact_length_m * settings.lm2_contact_width_m
    )
    cases = tuple(
        (case_id, x_m, y_center)
        for case_id, (x_m, y_center) in enumerate(
            (
                (x_value, y_value)
                for x_value in x_positions
                for y_value in y_centers
            ),
            start=1,
        )
    )
    if not cases:
        raise ValueError("No LM2 scan positions were generated.")

    girder_y: dict[int, float] = {}
    best_moment: dict[int, float] = {}
    best_shear: dict[int, float] = {}
    best_torsion: dict[int, float] = {}
    moment_positions: dict[int, tuple[int, float, float]] = {}
    shear_positions: dict[int, tuple[int, float, float]] = {}
    torsion_positions: dict[int, tuple[int, float, float]] = {}
    prepared = None
    case_models: dict[int, VerificationModel] = {}
    total_cases = len(cases)
    for completed, (case_id, x_m, y_center) in enumerate(cases, start=1):
        load_case = GrillageVerificationLoadCase(
            name=f"EN 1991-2 LM2 case {case_id}",
            point_loads=(
                GrillagePointLoad(
                    x_m=x_m,
                    y_m=y_center - half_track,
                    magnitude_kn=wheel_load,
                    label="LM2 wheel left",
                ),
                GrillagePointLoad(
                    x_m=x_m,
                    y_m=y_center + half_track,
                    magnitude_kn=wheel_load,
                    label="LM2 wheel right",
                ),
            ),
        )
        model = build_project_grillage_verification_model(
            project,
            transverse_stations_m=union_x,
            load_case=load_case,
        )
        case_models[case_id] = model
        if prepared is None:
            prepared = prepare_vertical_grillage(model)
        analysis = solve_prepared_vertical_grillage(prepared, model)
        for item in _effects_from_native_envelope(model, analysis, case_id=case_id):
            index = item.girder_index
            girder_y[index] = item.y_m
            moment = abs(item.effects.moment_knm)
            shear = abs(item.effects.shear_kn)
            torsion = abs(item.effects.torsion_knm)
            if moment > best_moment.get(index, -1.0):
                best_moment[index] = moment
                moment_positions[index] = (case_id, x_m, y_center)
            if shear > best_shear.get(index, -1.0):
                best_shear[index] = shear
                shear_positions[index] = (case_id, x_m, y_center)
            if torsion > best_torsion.get(index, -1.0):
                best_torsion[index] = torsion
                torsion_positions[index] = (case_id, x_m, y_center)
        if progress_callback is not None:
            progress_callback(completed, total_cases)

    indices = tuple(sorted(girder_y))
    girders = tuple(
        GirderActionEnvelope(
            girder_index=index,
            y_m=girder_y[index],
            effects=LoadEffects(
                moment_knm=best_moment[index],
                shear_kn=best_shear[index],
                torsion_knm=best_torsion[index],
            ),
            case_id=moment_positions[index][0],
        )
        for index in indices
    )
    return LM2ActionResult(
        evaluated_case_count=total_cases,
        wheel_load_kn=wheel_load,
        axle_load_kn=axle_load,
        contact_pressure_kn_m2=contact_pressure,
        girders=girders,
        governing_positions=tuple(moment_positions[index] for index in indices),
        governing_moment_positions=tuple(
            moment_positions[index] for index in indices
        ),
        governing_shear_positions=tuple(
            shear_positions[index] for index in indices
        ),
        governing_torsion_positions=tuple(
            torsion_positions[index] for index in indices
        ),
        status=(
            "EN 1991-2 LM2 scan with independent per-girder M/V/T envelopes. "
            "Each response component retains its own governing axle placement; "
            "the 0.35 m x 0.60 m contact patch remains an explicit local-design "
            "pressure, while slab punching/local plate stress is not relabelled "
            "from the beam-grillage response."
        ),
        governing_models=tuple(
            replace(
                case_models[case_id],
                load_cases=(
                    replace(
                        case_models[case_id].load_cases[0],
                        load_case_id=case_id,
                    ),
                ),
                metadata={
                    **case_models[case_id].metadata,
                    "lm2_case_id": str(case_id),
                },
            )
            for case_id in sorted(
                {
                    *(item[0] for item in moment_positions.values()),
                    *(item[0] for item in shear_positions.values()),
                    *(item[0] for item in torsion_positions.values()),
                }
            )
        ),
    )


def barrier_impact_action(
    settings: ExtendedActionSettings,
) -> BarrierImpactResult:
    adjusted_q1 = 300.0 * settings.barrier_alpha_Q1
    vertical = settings.barrier_vertical_factor * adjusted_q1
    return BarrierImpactResult(
        transverse_characteristic_force_kn=settings.barrier_transverse_force_kn,
        accompanying_vertical_wheel_load_kn=vertical,
        barrier_base_moment_knm=(
            settings.barrier_transverse_force_kn * settings.barrier_load_height_m
        ),
        status=(
            "First-generation EN 1991-2 safety-barrier accidental-action reference. "
            "The transverse force and associated base moment are local restraint/deck-edge "
            "demands; verify the actual restraint-system class, anchorage and project/National "
            "Annex values. The current vertical grillage does not analyse the horizontal force."
        ),
    )


def wind_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
) -> WindActionResult:
    """Calculate transparent bridge wind resultants from explicit project inputs.

    This is an action generator/assessment, not an aerodynamic instability model.
    q = 0.5*rho*v^2 is converted to kN/m2 and multiplied by the explicit exposure
    and force coefficients. The transverse resultant feeds the bearing/support
    path; an optional vertical coefficient exposes a deck-area vertical resultant.
    """

    velocity = settings.wind_basic_velocity_m_s
    pressure = 0.0005 * settings.wind_air_density_kg_m3 * velocity**2
    effective = pressure * settings.wind_exposure_factor
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    deck_width = float(project.geometry.deck_width_m)
    automatic_height = (
        float(project.geometry.girder_depth_m)
        + float(project.geometry.physical_deck_depth_m)
    )
    height = settings.wind_loaded_height_m or automatic_height
    transverse = (
        effective
        * settings.wind_transverse_force_coefficient
        * height
        * total_length
    )
    vertical = (
        effective
        * settings.wind_vertical_force_coefficient
        * deck_width
        * total_length
    )
    vertical_pressure = (
        vertical / (deck_width * total_length)
        if deck_width > 0.0 and total_length > 0.0
        else 0.0
    )
    return WindActionResult(
        basic_velocity_m_s=velocity,
        basic_dynamic_pressure_kn_m2=pressure,
        effective_pressure_kn_m2=effective,
        projected_height_m=height,
        transverse_characteristic_force_kn=transverse,
        transverse_line_load_kn_m=(
            transverse / total_length if total_length > 0.0 else 0.0
        ),
        vertical_characteristic_force_kn=vertical,
        vertical_pressure_kn_m2=vertical_pressure,
        overturning_reference_moment_knm=transverse * height / 2.0,
        input_complete=velocity > 0.0,
        status=(
            "Bridge wind action from explicit basic/project wind speed, air density, "
            "exposure and force coefficients. The transverse resultant is intended for "
            "the bearing/lateral-restraint path; the optional vertical coefficient gives "
            "a deck-area resultant. Aerodynamic instability and site-specific terrain/"
            "orography derivation remain outside this first static wind-action module."
        ),
    )


def construction_action(
    project: ProjectInput,
    settings: ExtendedActionSettings,
) -> ConstructionActionResult:
    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Application construction-stage summary currently supports one simple span. "
            "Use the detailed project_construction workflow for continuous construction."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError("Construction-stage summary currently requires one simple span.")
    span_m = float(project.geometry.span_lengths_m[0])
    rows: list[ConstructionStageGirderResult] = []
    for girder_index in range(1, int(project.geometry.girder_count) + 1):
        segments = girder_permanent_load_segments(
            project,
            girder_index=girder_index,
        )
        execution_line = (
            settings.construction_execution_udl_kn_m2
            * girder_deck_tributary_width_m(project, girder_index=girder_index)
        )
        for stage in PermanentActionStage:
            loads = [
                DistributedLoadSegment(
                    magnitude_kn_m=segment.magnitude_kn_m,
                    start_m=segment.x_start_m,
                    end_m=segment.x_end_m,
                    label=segment.source,
                    stage=segment.stage.value,
                )
                for segment in segments
                if segment.stage is stage
            ]
            if (
                stage is PermanentActionStage.DECK_CONSTRUCTION
                and execution_line > 0.0
            ):
                loads.append(
                    DistributedLoadSegment(
                        magnitude_kn_m=execution_line,
                        start_m=0.0,
                        end_m=span_m,
                        label="explicit construction execution UDL",
                        stage=stage.value,
                    )
                )
            response = simple_span_distributed_load_response(span_m, loads)
            rows.append(
                ConstructionStageGirderResult(
                    girder_index=girder_index,
                    stage=stage,
                    characteristic_max_moment_knm=response.max_moment_knm,
                    characteristic_max_abs_shear_kn=response.max_abs_shear_kn,
                    execution_udl_kn_m=(
                        execution_line
                        if stage is PermanentActionStage.DECK_CONSTRUCTION
                        else 0.0
                    ),
                    status=(
                        "Stage characteristic action effect on a statically determinate girder. "
                        "The existing detailed construction grillage workflow remains required "
                        "when transverse temporary members, propping, changed supports/continuity "
                        "or time-dependent redistribution govern."
                    ),
                )
            )
    return ConstructionActionResult(
        girders=tuple(rows),
        status=(
            "Construction sequence separated into PRECAST_GIRDER, DECK_CONSTRUCTION and "
            "SUPERIMPOSED action stages. Physical girder/false-slab/wet-deck/superimposed "
            "weights are not reapplied to final composite stiffness."
        ),
    )


def run_extended_actions(
    project: ProjectInput,
    settings: ExtendedActionSettings,
    *,
    grid_spacing_m: float,
    traffic_step_m: float = 0.5,
    max_exhaustive_tandem_combinations: int = 5000,
    lm2_progress_callback: Callable[[int, int], None] | None = None,
    gr2_progress_callback: Callable[[int, int], None] | None = None,
) -> ExtendedActionSuite:
    """Run the required additional action families plus static wind assessment."""

    return ExtendedActionSuite(
        braking=(
            braking_action(project, settings)
            if settings.braking_enabled
            else None
        ),
        thermal=(
            thermal_action(project, settings)
            if settings.thermal_enabled
            else None
        ),
        pedestrian=(
            pedestrian_action(
                project,
                settings,
                grid_spacing_m=grid_spacing_m,
            )
            if settings.pedestrian_enabled
            else None
        ),
        gr2_frequent_lm1=(
            gr2_frequent_lm1_action(
                project,
                settings,
                grid_spacing_m=grid_spacing_m,
                longitudinal_step_m=traffic_step_m,
                max_exhaustive_tandem_combinations=(
                    max_exhaustive_tandem_combinations
                ),
                progress_callback=gr2_progress_callback,
            )
            if settings.braking_enabled
            else None
        ),
        lm2=(
            lm2_action(
                project,
                settings,
                grid_spacing_m=grid_spacing_m,
                progress_callback=lm2_progress_callback,
            )
            if settings.lm2_enabled
            else None
        ),
        barrier_impact=(
            barrier_impact_action(settings)
            if settings.barrier_impact_enabled
            else None
        ),
        wind=(
            wind_action(project, settings)
            if settings.wind_enabled
            else None
        ),
        construction=(
            construction_action(project, settings)
            if settings.construction_enabled
            else None
        ),
    )
