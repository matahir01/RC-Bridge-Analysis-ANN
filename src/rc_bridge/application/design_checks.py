from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    composite_section_total_depth_m,
    girder_bottom_width_m,
    girder_tributary_slab_widths_m,
    girder_web_width_m,
)
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
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_deflection import SimpleSpanMomentDiagram
from rc_bridge.design.eurocode_demand import check_shear
from rc_bridge.design.eurocode_detailing import (
    LinkArrangement,
    LongitudinalBarArrangement,
    beam_detailing_requirements,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
from rc_bridge.design.eurocode_layered_section import required_tension_steel_layered
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
    status: str

    @property
    def passes_current_checks(self) -> bool:
        checks = (
            self.design.uls_design.flexure.utilization <= 1.0 + 1.0e-9,
            self.design.shear_utilization <= 1.0 + 1.0e-9,
            self.design.crack.utilization <= 1.0 + 1.0e-9,
            self.design.deflection.utilization <= 1.0 + 1.0e-9,
            self.detailing.cage_fit.passes,
            self.detailing.cover_and_durability.satisfies_nominal_cover,
        )
        return all(checks)


@dataclass(frozen=True)
class ApplicationDesignInterpretationSuite:
    girders: tuple[ApplicationGirderDesignInterpretation, ...]
    status: str

    @property
    def all_current_checks_pass(self) -> bool:
        return all(item.passes_current_checks for item in self.girders)


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


def _design_one_girder(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    girder_index: int,
    slab_width_m: float,
    uls_factors: EurocodeFactors,
    sls_factors: ServiceabilityPsiFactors,
    crack_limit_mm: float,
    deflection_limit_span_ratio: float,
    settings: ApplicationDesignSettings,
) -> ApplicationGirderDesignInterpretation:
    span_m = float(project.geometry.span_lengths_m[0])
    total_depth_m = composite_section_total_depth_m(project.geometry)
    materials = project_eurocode_material_input(project)

    permanent = girder_characteristic_permanent_effects(
        project,
        girder_index=girder_index,
    )
    envelope = search.girders[girder_index - 1]
    traffic = LoadEffects(
        moment_knm=envelope.moment_knm.value,
        shear_kn=envelope.shear_kn.value,
        torsion_knm=envelope.torsion_knm.value,
    )
    uls = persistent_uls(permanent, traffic, uls_factors)
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
            required_asw_per_s_mm2_per_m=(
                requirements.shear.governing_required_asw_per_s_mm2_per_m
            ),
            web_width_mm=web_width_m * 1000.0,
            maximum_longitudinal_spacing_mm=(
                requirements.shear.maximum_longitudinal_link_spacing_mm
            ),
            maximum_transverse_leg_spacing_mm=(
                requirements.shear.maximum_transverse_leg_spacing_mm
            ),
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
        case_id=envelope.moment_knm.case_id,
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
    crack_service_moment = max(abs(value) for value in crack_diagram.moments_knm)
    deflection_service_moment = max(
        abs(value) for value in deflection_diagram.moments_knm
    )
    serviceability = EurocodeServiceabilityInput(
        service_moment_knm=crack_service_moment,
        equivalent_full_span_udl_kn_m=(
            8.0 * deflection_service_moment / span_m**2
        ),
        crack_limit_mm=crack_limit_mm,
        allowable_deflection_mm=(
            span_m * 1000.0 / deflection_limit_span_ratio
        ),
        creep_coefficient=settings.creep_coefficient,
        deflection_beta=settings.deflection_beta,
        crack_kt=settings.crack_kt,
        deflection_moment_diagram=deflection_diagram,
        deflection_service_moment_knm=deflection_service_moment,
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

    if not all(
        isfinite(value)
        for value in (
            design.uls_design.flexure.utilization,
            design.shear_utilization,
            design.crack.utilization,
            design.deflection.utilization,
        )
    ):
        raise RuntimeError("Design interpretation produced a non-finite utilization.")

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
        status=(
            "Analysis-derived EC2 positive-bending design interpretation using the "
            "physical layered rectangular/T/I section, discrete reinforcement selection, "
            "crack-width and co-located native-LM1 service-deflection checks. It is not "
            "production-certified until the native solver/load actions pass Stage 7 "
            "independent verification and the remaining project actions are in scope."
        ),
    )


def run_application_design_interpretation(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    uls_factors: EurocodeFactors,
    sls_factors: ServiceabilityPsiFactors,
    crack_limit_mm: float,
    deflection_limit_span_ratio: float,
    settings: ApplicationDesignSettings | None = None,
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
        )
        for index in range(1, int(project.geometry.girder_count) + 1)
    )
    return ApplicationDesignInterpretationSuite(
        girders=girders,
        status=(
            "PRELIMINARY / VERIFICATION-GATED: flexure, shear, crack width, "
            "deflection, reinforcement selection, anchorage/detailing and cover checks "
            "are calculated from the current native analysis. Stage 7 independent "
            "MIDAS/STAAD validation and completion of applicable traffic/environmental/"
            "accidental actions remain mandatory before production acceptance."
        ),
    )
