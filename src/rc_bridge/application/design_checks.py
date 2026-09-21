from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    composite_section_total_depth_m,
    deck_construction_concrete_layers,
    girder_bottom_width_m,
    girder_tributary_slab_widths_m,
    girder_web_width_m,
    precast_concrete_layers,
)
from rc_bridge.application.action_combinations import (
    GirderActionEnvelope,
    IntegratedActionCombinationSuite,
)
from rc_bridge.application.extended_actions import ExtendedActionSuite
from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import (
    DesignCode,
    PermanentActionStage,
    ProjectInput,
    SupportSystem,
)
from rc_bridge.design.eurocode_deflection import SimpleSpanMomentDiagram
from rc_bridge.design.eurocode_demand import check_shear
from rc_bridge.design.eurocode_detailing import (
    LinkArrangement,
    LongitudinalBarArrangement,
    beam_detailing_requirements,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
from rc_bridge.design.eurocode_layered_section import (
    layered_singly_reinforced_resistance,
    required_tension_steel_layered,
)
from rc_bridge.design.eurocode_shear import provided_vertical_shear_resistance
from rc_bridge.workflow.eurocode_girder import EurocodeServiceabilityInput
from rc_bridge.workflow.eurocode_layered_girder import (
    EurocodeLayeredGirderWorkflowResult,
    LayeredGirderDesignInput,
    run_eurocode_layered_girder_case,
)
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    native_lm1_girder_moment_diagram,
)
from rc_bridge.workflow.project_bridge import (
    SLSCombinationChoice,
    girder_characteristic_permanent_effects,
    girder_permanent_moments_knm_at,
    project_eurocode_material_input,
)
from rc_bridge.workflow.project_layered_detailing import (
    ProjectLayeredGirderDetailingResult,
    run_project_layered_girder_detailing,
)

EC2_MAXIMUM_DESIGN_LEVER_ARM_RATIO = 0.95


@dataclass(frozen=True)
class ApplicationDesignSettings:
    """Editable assumptions for the desktop analysis-derived design interpretation."""

    cover_mm: float = 50.0
    durability_minimum_cover_mm: float = 40.0
    cover_deviation_mm: float = 10.0
    aggregate_size_mm: float = 20.0
    nominal_link_diameter_mm: float = 12.0
    crack_combination: SLSCombinationChoice = SLSCombinationChoice.FREQUENT
    deflection_combination: SLSCombinationChoice = SLSCombinationChoice.FREQUENT
    creep_coefficient: float = 0.0
    deflection_beta: float = 0.5
    crack_kt: float = 0.4
    cot_theta: float = 2.0

    def __post_init__(self) -> None:
        positive = (
            self.cover_mm,
            self.durability_minimum_cover_mm,
            self.aggregate_size_mm,
            self.nominal_link_diameter_mm,
            self.cot_theta,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("Design geometry/detailing settings must be positive.")
        if self.cover_deviation_mm < 0.0 or self.creep_coefficient < 0.0:
            raise ValueError("Cover deviation and creep coefficient cannot be negative.")
        if not 0.0 < self.deflection_beta <= 1.0:
            raise ValueError("deflection_beta must lie in (0, 1].")
        if not 0.0 < self.crack_kt <= 1.0:
            raise ValueError("crack_kt must lie in (0, 1].")
        if not 1.0 <= self.cot_theta <= 2.5:
            raise ValueError("cot_theta must lie between 1.0 and 2.5.")


@dataclass(frozen=True)
class _ConstructionStageDemand:
    stage: PermanentActionStage
    design_moment_knm: float
    design_shear_kn: float
    layers: tuple
    section_depth_m: float


@dataclass(frozen=True)
class ConstructionStageDesignCheck:
    stage: PermanentActionStage
    design_moment_knm: float
    design_shear_kn: float
    effective_depth_m: float
    flexural_resistance_knm: float
    flexural_utilization: float
    shear_resistance_kn: float
    shear_utilization: float
    required_steel_area_mm2: float
    provided_steel_area_mm2: float
    passes: bool
    status: str


@dataclass(frozen=True)
class ApplicationGirderDesignInterpretation:
    girder_index: int
    slab_width_m: float
    effective_depth_m: float
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    uls: FactoredCombination
    design: EurocodeLayeredGirderWorkflowResult
    detailing: ProjectLayeredGirderDetailingResult
    selected_bars: LongitudinalBarArrangement
    selected_links: LinkArrangement
    crack_combination: SLSCombinationChoice
    deflection_combination: SLSCombinationChoice
    governing_uls_moment_situation: str
    governing_uls_shear_situation: str
    governing_sls_crack_situation: str
    governing_sls_deflection_situation: str
    construction_stage_checks: tuple[ConstructionStageDesignCheck, ...]
    status: str

    @property
    def passes_current_checks(self) -> bool:
        deflection_pass = self.design.deflection.passes
        checks = (
            self.design.uls_design.flexure.utilization <= 1.0 + 1.0e-9,
            self.design.shear_utilization <= 1.0 + 1.0e-9,
            self.design.crack.utilization <= 1.0 + 1.0e-9,
            True if deflection_pass is None else deflection_pass,
            self.detailing.cage_fit.passes,
            self.detailing.cover_and_durability.satisfies_nominal_cover,
            all(item.passes for item in self.construction_stage_checks),
        )
        return all(checks)


@dataclass(frozen=True)
class ApplicationDesignInterpretationSuite:
    girders: tuple[ApplicationGirderDesignInterpretation, ...]
    action_combinations: IntegratedActionCombinationSuite | None
    coverage_blockers: tuple[str, ...]
    status: str

    @property
    def all_current_checks_pass(self) -> bool:
        return (
            all(item.passes_current_checks for item in self.girders)
            and not self.coverage_blockers
        )


def _selected_sls(
    permanent: LoadEffects,
    traffic: LoadEffects,
    *,
    choice: SLSCombinationChoice,
    factors: ServiceabilityPsiFactors,
) -> FactoredCombination:
    if choice is SLSCombinationChoice.CHARACTERISTIC:
        return characteristic_sls(permanent, traffic)
    if choice is SLSCombinationChoice.FREQUENT:
        return frequent_sls(permanent, traffic, factors)
    if choice is SLSCombinationChoice.QUASI_PERMANENT:
        return quasi_permanent_sls(permanent, traffic, factors)
    raise ValueError(f"Unsupported SLS combination: {choice}")


def _combined_native_moment_diagram(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    girder_index: int,
    case_id: int,
    combination: FactoredCombination,
    label: str,
) -> SimpleSpanMomentDiagram:
    traffic = native_lm1_girder_moment_diagram(
        search,
        girder_index=girder_index,
        case_id=case_id,
    )
    permanent = girder_permanent_moments_knm_at(
        project,
        girder_index=girder_index,
        stations_m=traffic.stations_m,
    )
    g_factor = combination.factors["G"]
    q_factor = combination.factors["Q_traffic"]
    moments = tuple(
        g_factor * g_moment - q_factor * q_moment
        for g_moment, q_moment in zip(
            permanent,
            traffic.moments_knm,
            strict=True,
        )
    )
    return SimpleSpanMomentDiagram(
        stations_m=traffic.stations_m,
        moments_knm=moments,
        source=(
            f"{label}; native LM1 case {case_id}; girder {girder_index}; "
            f"G={g_factor:.6g}; Q_traffic={q_factor:.6g}; "
            "native traffic moment mapped to sagging-positive"
        ),
    )


def _bar_centroid_effective_depth_m(
    *,
    total_depth_m: float,
    arrangement: LongitudinalBarArrangement,
    cover_mm: float,
    link_diameter_mm: float,
) -> float:
    phi = arrangement.bar_diameter_mm
    layer_pitch = phi + arrangement.clear_vertical_spacing_mm
    weighted = 0.0
    count = 0
    for layer_index, layer_count in enumerate(arrangement.bars_per_layer):
        centre_from_bottom = (
            cover_mm
            + link_diameter_mm
            + phi / 2.0
            + layer_index * layer_pitch
        )
        weighted += layer_count * centre_from_bottom
        count += layer_count
    if count <= 0:
        raise ValueError("Selected longitudinal arrangement contains no bars.")
    centroid_from_bottom_mm = weighted / count
    d_m = total_depth_m - centroid_from_bottom_mm / 1000.0
    if not 0.0 < d_m < total_depth_m:
        raise ValueError("Selected reinforcement produces an invalid effective depth.")
    return d_m


def _bar_spacing_mm(arrangement: LongitudinalBarArrangement) -> float:
    return arrangement.bar_diameter_mm + arrangement.clear_horizontal_spacing_mm


def _service_effect_from_integrated_envelope(
    envelope: GirderActionEnvelope,
    choice: SLSCombinationChoice,
) -> tuple[LoadEffects, str]:
    if choice is SLSCombinationChoice.CHARACTERISTIC:
        return (
            envelope.characteristic_sls_effects,
            envelope.governing_characteristic_moment_situation,
        )
    if choice is SLSCombinationChoice.FREQUENT:
        return (
            envelope.frequent_sls_effects,
            envelope.governing_frequent_moment_situation,
        )
    if choice is SLSCombinationChoice.QUASI_PERMANENT:
        return (
            envelope.quasi_permanent_sls_effects,
            "quasi-permanent permanent-action envelope",
        )
    raise ValueError(f"Unsupported SLS combination: {choice}")


def _construction_stage_demands(
    project: ProjectInput,
    actions: ExtendedActionSuite | None,
    *,
    girder_index: int,
    slab_width_m: float,
    uls_factors: EurocodeFactors,
    gamma_q_nontraffic: float,
) -> tuple[_ConstructionStageDemand, ...]:
    if actions is None or actions.construction is None:
        return ()

    span_m = float(project.geometry.span_lengths_m[0])
    rows = {
        item.stage: item
        for item in actions.construction.girders
        if item.girder_index == girder_index
    }
    precast_row = rows.get(PermanentActionStage.PRECAST_GIRDER)
    deck_row = rows.get(PermanentActionStage.DECK_CONSTRUCTION)
    if precast_row is None or deck_row is None:
        return ()

    def split_stage(row) -> tuple[float, float, float, float]:
        q_line = row.execution_udl_kn_m
        q_m = q_line * span_m**2 / 8.0
        q_v = q_line * span_m / 2.0
        g_m = max(row.characteristic_max_moment_knm - q_m, 0.0)
        g_v = max(row.characteristic_max_abs_shear_kn - q_v, 0.0)
        return g_m, g_v, q_m, q_v

    precast_g_m, precast_g_v, _, _ = split_stage(precast_row)
    deck_g_m, deck_g_v, deck_q_m, deck_q_v = split_stage(deck_row)

    profile = project.geometry.girder_profile
    if profile is None:
        return ()
    false_depth = float(
        project.geometry.deck_construction.precast_false_slab_depth_m
    )

    cases = (
        (
            PermanentActionStage.PRECAST_GIRDER,
            precast_g_m,
            precast_g_v,
            0.0,
            0.0,
            precast_concrete_layers(project.geometry),
            float(profile.total_depth_m),
        ),
        (
            PermanentActionStage.DECK_CONSTRUCTION,
            precast_g_m + deck_g_m,
            precast_g_v + deck_g_v,
            deck_q_m,
            deck_q_v,
            deck_construction_concrete_layers(
                project.geometry,
                slab_width_m=slab_width_m,
            ),
            (
                float(profile.total_depth_m) + false_depth
                if project.geometry.deck_construction.false_slab_composite_participation
                else float(profile.total_depth_m)
            ),
        ),
    )
    return tuple(
        _ConstructionStageDemand(
            stage=stage,
            design_moment_knm=(
                uls_factors.gamma_g_unfavourable * g_m
                + gamma_q_nontraffic * q_m
            ),
            design_shear_kn=abs(
                uls_factors.gamma_g_unfavourable * g_v
                + gamma_q_nontraffic * q_v
            ),
            layers=layers,
            section_depth_m=stage_depth,
        )
        for stage, g_m, g_v, q_m, q_v, layers, stage_depth in cases
    )


def _construction_stage_checks(
    project: ProjectInput,
    actions: ExtendedActionSuite | None,
    *,
    girder_index: int,
    slab_width_m: float,
    selected_bars: LongitudinalBarArrangement,
    selected_links: LinkArrangement,
    settings: ApplicationDesignSettings,
    uls_factors: EurocodeFactors,
    gamma_q_nontraffic: float,
) -> tuple[ConstructionStageDesignCheck, ...]:
    demands = _construction_stage_demands(
        project,
        actions,
        girder_index=girder_index,
        slab_width_m=slab_width_m,
        uls_factors=uls_factors,
        gamma_q_nontraffic=gamma_q_nontraffic,
    )
    if not demands:
        return ()

    checks: list[ConstructionStageDesignCheck] = []
    for demand in demands:
        d_stage = _bar_centroid_effective_depth_m(
            total_depth_m=demand.section_depth_m,
            arrangement=selected_bars,
            cover_mm=settings.cover_mm,
            link_diameter_mm=selected_links.link_diameter_mm,
        )
        med = demand.design_moment_knm
        ved = demand.design_shear_kn
        required = required_tension_steel_layered(
            med_knm=max(med, 0.0),
            layers=demand.layers,
            effective_depth_m=d_stage,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            maximum_design_lever_arm_ratio=EC2_MAXIMUM_DESIGN_LEVER_ARM_RATIO,
        )
        flexure = layered_singly_reinforced_resistance(
            layers=demand.layers,
            effective_depth_m=d_stage,
            steel_area_mm2=selected_bars.provided_area_mm2,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
        )
        flex_util = (
            med / flexure.resistance_knm
            if flexure.resistance_knm > 0.0
            else float("inf")
        )
        shear = check_shear(
            ved_kn=abs(ved),
            web_width_m=girder_web_width_m(project.geometry),
            effective_depth_m=d_stage,
            longitudinal_steel_area_mm2=selected_bars.provided_area_mm2,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            cot_theta=settings.cot_theta,
        )
        if abs(ved) <= shear.concrete_resistance_kn:
            shear_resistance = shear.concrete_resistance_kn
        else:
            provided = provided_vertical_shear_resistance(
                provided_asw_per_s_mm2_per_m=(
                    selected_links.provided_asw_per_s_mm2_per_m
                ),
                web_width_m=girder_web_width_m(project.geometry),
                effective_depth_m=d_stage,
                fck_mpa=float(project.materials.fck_mpa),
                fyk_mpa=float(project.materials.fyk_mpa),
                cot_theta=settings.cot_theta,
            )
            shear_resistance = provided.governing_resistance_kn
        shear_util = (
            abs(ved) / shear_resistance
            if shear_resistance > 0.0
            else float("inf")
        )
        checks.append(
            ConstructionStageDesignCheck(
                stage=demand.stage,
                design_moment_knm=med,
                design_shear_kn=abs(ved),
                effective_depth_m=d_stage,
                flexural_resistance_knm=flexure.resistance_knm,
                flexural_utilization=flex_util,
                shear_resistance_kn=shear_resistance,
                shear_utilization=shear_util,
                required_steel_area_mm2=required,
                provided_steel_area_mm2=selected_bars.provided_area_mm2,
                passes=(
                    flex_util <= 1.0 + 1.0e-9
                    and shear_util <= 1.0 + 1.0e-9
                    and selected_bars.provided_area_mm2 + 1.0e-9 >= required
                ),
                status=(
                    "Construction-stage EC2 check using the physical section active "
                    "when the load arrives; wet in-situ concrete is not credited to "
                    "stiffness/resistance before hardening."
                ),
            )
        )
    return tuple(checks)


def _design_one_girder(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    girder_index: int,
    slab_width_m: float,
    uls_factors: EurocodeFactors,
    sls_factors: ServiceabilityPsiFactors,
    crack_limit_mm: float,
    deflection_limit_span_ratio: float | None,
    settings: ApplicationDesignSettings,
    action_envelope: GirderActionEnvelope | None = None,
    extended_actions: ExtendedActionSuite | None = None,
    gamma_q_nontraffic: float = 1.50,
) -> ApplicationGirderDesignInterpretation:
    span_m = float(project.geometry.span_lengths_m[0])
    total_depth_m = composite_section_total_depth_m(project.geometry)
    materials = project_eurocode_material_input(project)

    native_envelope = search.girders[girder_index - 1]
    permanent = girder_characteristic_permanent_effects(
        project,
        girder_index=girder_index,
    )
    if action_envelope is None:
        traffic = LoadEffects(
            moment_knm=native_envelope.moment_knm.value,
            shear_kn=native_envelope.shear_kn.value,
            torsion_knm=native_envelope.torsion_knm.value,
        )
        uls = persistent_uls(permanent, traffic, uls_factors)
        governing_uls_moment = "gr1a LM1"
        governing_uls_shear = "gr1a LM1"
    else:
        permanent = action_envelope.permanent
        traffic = action_envelope.equivalent_variable_for_uls(uls_factors)
        uls = FactoredCombination(
            name="EN 1990 compatible traffic-group ULS envelope",
            effects=action_envelope.uls_effects,
            factors={
                "G": uls_factors.gamma_g_unfavourable,
                "Q_traffic": uls_factors.gamma_q_traffic,
            },
        )
        governing_uls_moment = (
            action_envelope.governing_uls_moment_situation
        )
        governing_uls_shear = (
            action_envelope.governing_uls_shear_situation
        )
    if uls.effects.moment_knm < -1.0e-9:
        raise ValueError(
            "The application simple-span design interpretation cannot process hogging ULS."
        )

    layers = composite_concrete_layers(
        project.geometry,
        slab_width_m=slab_width_m,
    )
    web_width_m = girder_web_width_m(project.geometry)
    bottom_width_m = girder_bottom_width_m(project.geometry)
    concrete_area_m2 = sum(layer.area_m2 for layer in layers)
    concrete = concrete_properties_ec2(float(project.materials.fck_mpa))

    stage_demands = _construction_stage_demands(
        project,
        extended_actions,
        girder_index=girder_index,
        slab_width_m=slab_width_m,
        uls_factors=uls_factors,
        gamma_q_nontraffic=gamma_q_nontraffic,
    )

    # First estimate d from the nominated cover/link cage, then iterate after
    # discrete bar/link selection.
    d_m = total_depth_m - (
        settings.cover_mm + settings.nominal_link_diameter_mm + 12.5
    ) / 1000.0
    if not 0.0 < d_m < total_depth_m:
        raise ValueError("Cover/link assumptions leave no valid effective depth.")

    selected_bars: LongitudinalBarArrangement | None = None
    selected_links: LinkArrangement | None = None
    minimum_required_area_mm2 = 0.0
    for _ in range(12):
        required_flexural = required_tension_steel_layered(
            med_knm=max(uls.effects.moment_knm, 0.0),
            layers=layers,
            effective_depth_m=d_m,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            maximum_design_lever_arm_ratio=EC2_MAXIMUM_DESIGN_LEVER_ARM_RATIO,
        )
        centroid_from_bottom_m = total_depth_m - d_m
        for stage_demand in stage_demands:
            stage_d = stage_demand.section_depth_m - centroid_from_bottom_m
            if stage_d <= 0.0:
                raise ValueError(
                    "Selected reinforcement lies outside a construction-stage section."
                )
            required_flexural = max(
                required_flexural,
                required_tension_steel_layered(
                    med_knm=max(stage_demand.design_moment_knm, 0.0),
                    layers=stage_demand.layers,
                    effective_depth_m=stage_d,
                    fck_mpa=float(project.materials.fck_mpa),
                    fyk_mpa=float(project.materials.fyk_mpa),
                ),
            )
        trial_as = max(
            required_flexural,
            minimum_required_area_mm2,
            (
                1.0
                if selected_bars is None
                else selected_bars.provided_area_mm2
            ),
        )
        shear = check_shear(
            ved_kn=abs(uls.effects.shear_kn),
            web_width_m=web_width_m,
            effective_depth_m=d_m,
            longitudinal_steel_area_mm2=trial_as,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            cot_theta=settings.cot_theta,
        )
        required_asw = (
            0.0
            if shear.shear_reinforcement is None
            else shear.shear_reinforcement.asw_per_s_mm2_per_m
        )
        for stage_demand in stage_demands:
            stage_d = stage_demand.section_depth_m - centroid_from_bottom_m
            stage_shear = check_shear(
                ved_kn=stage_demand.design_shear_kn,
                web_width_m=web_width_m,
                effective_depth_m=stage_d,
                longitudinal_steel_area_mm2=trial_as,
                fck_mpa=float(project.materials.fck_mpa),
                fyk_mpa=float(project.materials.fyk_mpa),
                cot_theta=settings.cot_theta,
            )
            if stage_shear.shear_reinforcement is not None:
                required_asw = max(
                    required_asw,
                    stage_shear.shear_reinforcement.asw_per_s_mm2_per_m,
                )
        requirements = beam_detailing_requirements(
            fctm_mpa=concrete.fctm_mpa,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            tension_zone_width_m=bottom_width_m,
            web_width_m=web_width_m,
            effective_depth_m=d_m,
            concrete_area_m2=concrete_area_m2,
            provided_longitudinal_steel_mm2=trial_as,
            design_required_asw_per_s_mm2_per_m=required_asw,
        )
        governing_required_asw = (
            requirements.shear.governing_required_asw_per_s_mm2_per_m
        )
        maximum_link_spacing = (
            requirements.shear.maximum_longitudinal_link_spacing_mm
        )
        maximum_leg_spacing = (
            requirements.shear.maximum_transverse_leg_spacing_mm
        )
        for stage_demand in stage_demands:
            stage_d = stage_demand.section_depth_m - centroid_from_bottom_m
            stage_shear = check_shear(
                ved_kn=stage_demand.design_shear_kn,
                web_width_m=web_width_m,
                effective_depth_m=stage_d,
                longitudinal_steel_area_mm2=trial_as,
                fck_mpa=float(project.materials.fck_mpa),
                fyk_mpa=float(project.materials.fyk_mpa),
                cot_theta=settings.cot_theta,
            )
            stage_asw = (
                0.0
                if stage_shear.shear_reinforcement is None
                else stage_shear.shear_reinforcement.asw_per_s_mm2_per_m
            )
            stage_requirements = beam_detailing_requirements(
                fctm_mpa=concrete.fctm_mpa,
                fck_mpa=float(project.materials.fck_mpa),
                fyk_mpa=float(project.materials.fyk_mpa),
                tension_zone_width_m=bottom_width_m,
                web_width_m=web_width_m,
                effective_depth_m=stage_d,
                concrete_area_m2=sum(
                    layer.area_m2 for layer in stage_demand.layers
                ),
                provided_longitudinal_steel_mm2=trial_as,
                design_required_asw_per_s_mm2_per_m=stage_asw,
            )
            governing_required_asw = max(
                governing_required_asw,
                stage_requirements.shear.governing_required_asw_per_s_mm2_per_m,
            )
            maximum_link_spacing = min(
                maximum_link_spacing,
                stage_requirements.shear.maximum_longitudinal_link_spacing_mm,
            )
            maximum_leg_spacing = min(
                maximum_leg_spacing,
                stage_requirements.shear.maximum_transverse_leg_spacing_mm,
            )
        governing_longitudinal = max(
            required_flexural,
            requirements.longitudinal.minimum_tension_steel_mm2,
            minimum_required_area_mm2,
        )
        candidate_bars = select_longitudinal_bar_arrangement(
            required_area_mm2=governing_longitudinal,
            web_width_mm=bottom_width_m * 1000.0,
            cover_mm=settings.cover_mm,
            link_diameter_mm=settings.nominal_link_diameter_mm,
            aggregate_size_mm=settings.aggregate_size_mm,
        )
        # Prevent a discrete bar/d-depth two-cycle: once an arrangement proves
        # insufficient at its own refined effective depth, only move upward in
        # provided area on subsequent iterations.
        if (
            selected_bars is not None
            and candidate_bars.provided_area_mm2
            < selected_bars.provided_area_mm2 - 1.0e-9
        ):
            candidate_bars = selected_bars

        candidate_links = select_vertical_link_arrangement(
            required_asw_per_s_mm2_per_m=governing_required_asw,
            web_width_mm=web_width_m * 1000.0,
            maximum_longitudinal_spacing_mm=maximum_link_spacing,
            maximum_transverse_leg_spacing_mm=maximum_leg_spacing,
            cover_mm=settings.cover_mm,
        )
        refined_d = _bar_centroid_effective_depth_m(
            total_depth_m=total_depth_m,
            arrangement=candidate_bars,
            cover_mm=settings.cover_mm,
            link_diameter_mm=candidate_links.link_diameter_mm,
        )
        required_at_refined_d = required_tension_steel_layered(
            med_knm=max(uls.effects.moment_knm, 0.0),
            layers=layers,
            effective_depth_m=refined_d,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            maximum_design_lever_arm_ratio=EC2_MAXIMUM_DESIGN_LEVER_ARM_RATIO,
        )
        refined_centroid_from_bottom_m = total_depth_m - refined_d
        for stage_demand in stage_demands:
            stage_d = (
                stage_demand.section_depth_m
                - refined_centroid_from_bottom_m
            )
            required_at_refined_d = max(
                required_at_refined_d,
                required_tension_steel_layered(
                    med_knm=max(stage_demand.design_moment_knm, 0.0),
                    layers=stage_demand.layers,
                    effective_depth_m=stage_d,
                    fck_mpa=float(project.materials.fck_mpa),
                    fyk_mpa=float(project.materials.fyk_mpa),
                ),
            )
        selected_bars = candidate_bars
        selected_links = candidate_links
        if (
            selected_bars.provided_area_mm2 + 1.0e-9
            < required_at_refined_d
        ):
            minimum_required_area_mm2 = max(
                minimum_required_area_mm2,
                selected_bars.provided_area_mm2 + 1.0e-6,
                required_at_refined_d,
            )
            d_m = refined_d
            continue
        if abs(refined_d - d_m) <= 1.0e-6:
            d_m = refined_d
            break
        d_m = refined_d
    else:
        raise RuntimeError(
            "Discrete longitudinal reinforcement selection did not converge."
        )

    if selected_bars is None or selected_links is None:
        raise RuntimeError("Unable to select reinforcement for the design interpretation.")

    if action_envelope is None:
        crack_combination = _selected_sls(
            permanent,
            traffic,
            choice=settings.crack_combination,
            factors=sls_factors,
        )
        deflection_combination = _selected_sls(
            permanent,
            traffic,
            choice=settings.deflection_combination,
            factors=sls_factors,
        )
        crack_diagram = _combined_native_moment_diagram(
            project,
            search,
            girder_index=girder_index,
            case_id=native_envelope.moment_knm.case_id,
            combination=crack_combination,
            label=f"{settings.crack_combination.value} crack-action diagram",
        )
        deflection_case = search.deflection_for_girder(girder_index)
        deflection_diagram = _combined_native_moment_diagram(
            project,
            search,
            girder_index=girder_index,
            case_id=deflection_case.case_id,
            combination=deflection_combination,
            label=f"{settings.deflection_combination.value} deflection-action diagram",
        )
        crack_service_moment = max(
            abs(value) for value in crack_diagram.moments_knm
        )
        deflection_service_moment = max(
            abs(value) for value in deflection_diagram.moments_knm
        )
        governing_sls_crack = "native LM1 co-located service diagram"
        governing_sls_deflection = "native LM1 co-located service diagram"
    else:
        crack_effects, governing_sls_crack = (
            _service_effect_from_integrated_envelope(
                action_envelope,
                settings.crack_combination,
            )
        )
        deflection_effects, governing_sls_deflection = (
            _service_effect_from_integrated_envelope(
                action_envelope,
                settings.deflection_combination,
            )
        )
        crack_service_moment = abs(crack_effects.moment_knm)
        deflection_service_moment = abs(deflection_effects.moment_knm)
        crack_diagram = None
        deflection_diagram = None
    serviceability = EurocodeServiceabilityInput(
        service_moment_knm=crack_service_moment,
        equivalent_full_span_udl_kn_m=(
            8.0 * deflection_service_moment / span_m**2
        ),
        crack_limit_mm=crack_limit_mm,
        allowable_deflection_mm=(
            None
            if deflection_limit_span_ratio is None
            else span_m * 1000.0 / deflection_limit_span_ratio
        ),
        creep_coefficient=settings.creep_coefficient,
        deflection_beta=settings.deflection_beta,
        crack_kt=settings.crack_kt,
        deflection_moment_diagram=deflection_diagram,
        deflection_service_moment_knm=(
            deflection_service_moment
            if deflection_diagram is not None
            else None
        ),
    )
    section = LayeredGirderDesignInput(
        composite_slab_width_m=slab_width_m,
        effective_depth_m=d_m,
        steel_area_mm2=selected_bars.provided_area_mm2,
        bar_diameter_mm=selected_bars.bar_diameter_mm,
        bar_spacing_mm=_bar_spacing_mm(selected_bars),
        cover_mm=settings.cover_mm,
        provided_shear_asw_per_s_mm2_per_m=(
            selected_links.provided_asw_per_s_mm2_per_m
        ),
    )
    design = run_eurocode_layered_girder_case(
        project,
        girder_index=girder_index,
        span_m=span_m,
        permanent_effects=permanent,
        traffic_effects=traffic,
        section=section,
        materials=materials,
        serviceability=serviceability,
        uls_factors=uls_factors,
        cot_theta=settings.cot_theta,
    )
    detailing = run_project_layered_girder_detailing(
        project,
        section=section,
        design=design,
        durability_minimum_cover_mm=settings.durability_minimum_cover_mm,
        cover_deviation_mm=settings.cover_deviation_mm,
        nominal_link_diameter_mm=selected_links.link_diameter_mm,
        aggregate_size_mm=settings.aggregate_size_mm,
    )

    utilizations = (
        design.uls_design.flexure.utilization,
        design.shear_utilization,
        design.crack.utilization,
        design.deflection.utilization,
    )
    if not all(
        isfinite(value)
        for value in utilizations
        if value is not None
    ):
        raise RuntimeError("Design interpretation produced a non-finite utilization.")

    construction_checks = _construction_stage_checks(
        project,
        extended_actions,
        girder_index=girder_index,
        slab_width_m=slab_width_m,
        selected_bars=selected_bars,
        selected_links=selected_links,
        settings=settings,
        uls_factors=uls_factors,
        gamma_q_nontraffic=gamma_q_nontraffic,
    )

    return ApplicationGirderDesignInterpretation(
        girder_index=girder_index,
        slab_width_m=slab_width_m,
        effective_depth_m=d_m,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        uls=uls,
        design=design,
        detailing=detailing,
        selected_bars=selected_bars,
        selected_links=selected_links,
        crack_combination=settings.crack_combination,
        deflection_combination=settings.deflection_combination,
        governing_uls_moment_situation=governing_uls_moment,
        governing_uls_shear_situation=governing_uls_shear,
        governing_sls_crack_situation=governing_sls_crack,
        governing_sls_deflection_situation=governing_sls_deflection,
        construction_stage_checks=construction_checks,
        status=(
            "Analysis-derived EC2 positive-bending design interpretation using the "
            "physical layered rectangular/T/I section, discrete reinforcement selection, "
            "compatible traffic-group ULS/SLS envelopes, construction-stage checks, "
            "crack-width checks and service-deflection calculation; a deflection "
            "PASS/CHECK is assigned only when a project/client limit is supplied. "
            "Production acceptance remains "
            "locked until Stage 7 independent verification and any explicit coverage "
            "blockers are closed."
        ),
    )


def run_application_design_interpretation(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    uls_factors: EurocodeFactors,
    sls_factors: ServiceabilityPsiFactors,
    crack_limit_mm: float,
    deflection_limit_span_ratio: float | None,
    settings: ApplicationDesignSettings | None = None,
    action_combinations: IntegratedActionCombinationSuite | None = None,
    extended_actions: ExtendedActionSuite | None = None,
    gamma_q_nontraffic: float = 1.50,
) -> ApplicationDesignInterpretationSuite:
    """Run real EC2 checks without bypassing the application's verification gate."""

    if project.design_code is not DesignCode.EUROCODE:
        raise ValueError("Design interpretation currently supports Eurocode projects only.")
    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Desktop design interpretation currently supports one simple span only; "
            "continuous bridges must use the signed continuous design workflow."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError("Desktop design interpretation currently requires one span.")
    if project.geometry.girder_profile is None:
        raise ValueError("A complete physical girder profile is required for design.")
    if project.geometry.composite_flange_depth_m <= 0.0:
        raise ValueError("A participating deck layer is required for composite design.")

    design_settings = settings or ApplicationDesignSettings()
    slab_widths = girder_tributary_slab_widths_m(project.geometry)
    girders = tuple(
        _design_one_girder(
            project,
            search,
            girder_index=index,
            slab_width_m=slab_widths[index - 1],
            uls_factors=uls_factors,
            sls_factors=sls_factors,
            crack_limit_mm=crack_limit_mm,
            deflection_limit_span_ratio=deflection_limit_span_ratio,
            settings=design_settings,
            action_envelope=(
                None
                if action_combinations is None
                else action_combinations.girders[index - 1]
            ),
            extended_actions=extended_actions,
            gamma_q_nontraffic=gamma_q_nontraffic,
        )
        for index in range(1, int(project.geometry.girder_count) + 1)
    )
    blockers = list(
        ()
        if action_combinations is None
        else action_combinations.blockers
    )
    if deflection_limit_span_ratio is None:
        blockers.append(
            "Road-bridge deflection acceptance limit is not specified. "
            "EN 1990 Annex A2 does not impose a universal span/deflection ratio; "
            "the frequent combination is used by default, but a client/project "
            "criterion is required before PASS/CHECK can be assigned."
        )
    return ApplicationDesignInterpretationSuite(
        girders=girders,
        action_combinations=action_combinations,
        coverage_blockers=tuple(blockers),
        status=(
            "PRELIMINARY / VERIFICATION-GATED: flexure, shear, crack width, "
            "deflection, reinforcement selection, anchorage/detailing and cover checks "
            "are calculated from the current native analysis and compatible implemented "
            "action groups. The road-bridge deflection criterion remains an explicit "
            "project/client input rather than a hardcoded Eurocode span ratio. "
            "Independent verification and unresolved bearing/barrier/local-deck items "
            "remain explicit project blockers rather than hidden omissions."
        ),
    )
