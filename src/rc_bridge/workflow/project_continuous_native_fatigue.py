from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_fatigue import (
    ConcreteCompressionFatigueResult,
    ReinforcementFatigueResult,
    concrete_compression_fatigue_check,
    reinforcement_fatigue_check,
)
from rc_bridge.design.eurocode_layered_cracking import HorizontalSectionLayer
from rc_bridge.design.eurocode_layered_fatigue_section import (
    TransformedSteelLayer,
    cracked_layered_multi_steel_section,
)
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.project_continuous_native import (
    ProjectContinuousNativeLM1EnvelopeResult,
)
from rc_bridge.workflow.project_continuous_sls import support_layers_from_project
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3ContinuousStationRange,
    NativeFLM3FatigueDesignInput,
    ProjectNativeFLM3ContinuousGrillageSearchResult,
)


@dataclass(frozen=True)
class ContinuousTopSteelFatigueInput:
    effective_deck_width_m: float
    steel_area_mm2: float
    steel_depth_from_bottom_m: float

    def __post_init__(self) -> None:
        if min(
            self.effective_deck_width_m,
            self.steel_area_mm2,
            self.steel_depth_from_bottom_m,
        ) <= 0.0:
            raise ValueError("Continuous top-steel fatigue inputs must be positive.")


@dataclass(frozen=True)
class ContinuousFatigueStationResult:
    x_m: float
    permanent_moment_knm: float
    traffic_minimum_moment_knm: float
    traffic_maximum_moment_knm: float
    minimum_total_moment_knm: float
    maximum_total_moment_knm: float
    bottom_steel_stress_min_mpa: float
    bottom_steel_stress_max_mpa: float
    top_steel_stress_min_mpa: float
    top_steel_stress_max_mpa: float
    bottom_reinforcement: ReinforcementFatigueResult
    top_reinforcement: ReinforcementFatigueResult
    top_concrete: ConcreteCompressionFatigueResult
    bottom_concrete: ConcreteCompressionFatigueResult
    minimum_case_id: int | None
    maximum_case_id: int | None


@dataclass(frozen=True)
class ProjectContinuousNativeFatigueResult:
    girder_index: int
    stations: tuple[ContinuousFatigueStationResult, ...]
    governing_bottom_reinforcement: ContinuousFatigueStationResult
    governing_top_reinforcement: ContinuousFatigueStationResult
    governing_top_concrete: ContinuousFatigueStationResult
    governing_bottom_concrete: ContinuousFatigueStationResult
    status: str

    @property
    def passes(self) -> bool:
        return all(
            item.bottom_reinforcement.passes
            and item.top_reinforcement.passes
            and item.top_concrete.passes
            and item.bottom_concrete.passes
            for item in self.stations
        )


def _reverse_layers(
    layers_from_bottom: tuple[HorizontalSectionLayer, ...],
    *,
    total_depth_m: float,
) -> tuple[HorizontalSectionLayer, ...]:
    return tuple(
        HorizontalSectionLayer(
            width_m=item.width_m,
            start_depth_m=total_depth_m - item.end_depth_m,
            end_depth_m=total_depth_m - item.start_depth_m,
            label=item.label,
            active=item.active,
        )
        for item in reversed(layers_from_bottom)
    )


def _permanent_moments_by_x(
    production: ProjectContinuousNativeLM1EnvelopeResult,
) -> dict[float, float]:
    values: dict[float, float] = {}
    for station in production.envelope.stations:
        key = round(station.global_position_m, 12)
        previous = values.get(key)
        if previous is None:
            values[key] = station.permanent_moment_knm
        elif abs(previous - station.permanent_moment_knm) > 1.0e-7:
            raise ValueError(
                "Continuous permanent moment is discontinuous between station sides; "
                "fatigue section design requires one physical bending moment at each x."
            )
    return values


def _range_by_x(
    fatigue: ProjectNativeFLM3ContinuousGrillageSearchResult,
    *,
    girder_index: int,
) -> dict[float, NativeFLM3ContinuousStationRange]:
    return {
        round(item.x_m, 12): item
        for item in fatigue.ranges_for_girder(girder_index)
    }


def run_project_continuous_native_fatigue(
    project: ProjectInput,
    *,
    production: ProjectContinuousNativeLM1EnvelopeResult,
    fatigue_search: ProjectNativeFLM3ContinuousGrillageSearchResult,
    girder_index: int,
    bottom_section: LayeredGirderDesignInput,
    top_section: ContinuousTopSteelFatigueInput,
    fatigue_design: NativeFLM3FatigueDesignInput,
    es_mpa: float = 200000.0,
) -> ProjectContinuousNativeFatigueResult:
    """Check continuous top/bottom steel and concrete fatigue through moment reversal.

    Two reinforcement layers are retained in the cracked transformed section.
    At sagging stations the physical section is measured from the top compression
    face; at hogging stations the same physical section is reversed and measured
    from the bottom compression face. This allows each physical steel layer to
    move between tension and compression over the FLM3 cycle instead of being
    replaced by a zero-stress assumption when the bending sign reverses.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Continuous native fatigue currently supports Eurocode only.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous native fatigue requires CONTINUOUS supports.")
    if fatigue_search.total_length_m != sum(
        float(value) for value in project.geometry.span_lengths_m
    ):
        raise ValueError("Continuous FLM3 search length does not match the project.")
    if es_mpa <= 0.0:
        raise ValueError("es_mpa must be positive.")
    if girder_index != production.trace[0].girder_index:
        raise ValueError("Fatigue girder must match the native continuous production girder.")

    total_depth_m = (
        float(project.geometry.girder_depth_m)
        + float(project.geometry.physical_deck_depth_m)
    )
    if not 0.0 < bottom_section.effective_depth_m < total_depth_m:
        raise ValueError("Bottom reinforcement depth must lie inside the section.")
    if not 0.0 < top_section.steel_depth_from_bottom_m < total_depth_m:
        raise ValueError("Top reinforcement depth must lie inside the section.")

    negative_layers = support_layers_from_project(
        project,
        effective_deck_width_m=top_section.effective_deck_width_m,
    )
    positive_layers = _reverse_layers(
        support_layers_from_project(
            project,
            effective_deck_width_m=bottom_section.composite_slab_width_m,
        ),
        total_depth_m=total_depth_m,
    )
    concrete = concrete_properties_ec2(float(project.materials.fck_mpa))
    modular_ratio = es_mpa / concrete.ecm_mpa

    permanent_by_x = _permanent_moments_by_x(production)
    fatigue_by_x = _range_by_x(fatigue_search, girder_index=girder_index)
    missing = tuple(sorted(set(permanent_by_x) - set(fatigue_by_x)))
    if missing:
        raise ValueError(
            "Continuous FLM3 search is missing production design stations: "
            + ", ".join(f"{value:.6g}" for value in missing)
        )

    bottom_depth_from_top = bottom_section.effective_depth_m
    top_depth_from_top = total_depth_m - top_section.steel_depth_from_bottom_m
    bottom_depth_from_bottom = total_depth_m - bottom_depth_from_top
    top_depth_from_bottom = top_section.steel_depth_from_bottom_m

    def state(moment_knm: float) -> tuple[float, float, float, float]:
        if abs(moment_knm) <= 1.0e-12:
            return 0.0, 0.0, 0.0, 0.0
        if moment_knm > 0.0:
            section = cracked_layered_multi_steel_section(
                layers=positive_layers,
                total_depth_m=total_depth_m,
                steel_layers=(
                    TransformedSteelLayer(
                        "bottom",
                        bottom_section.steel_area_mm2,
                        bottom_depth_from_top,
                    ),
                    TransformedSteelLayer(
                        "top",
                        top_section.steel_area_mm2,
                        top_depth_from_top,
                    ),
                ),
                modular_ratio=modular_ratio,
                moment_magnitude_knm=moment_knm,
            )
            return (
                section.steel_stress_mpa("bottom"),
                section.steel_stress_mpa("top"),
                section.compression_face_stress_mpa,
                0.0,
            )

        section = cracked_layered_multi_steel_section(
            layers=negative_layers,
            total_depth_m=total_depth_m,
            steel_layers=(
                TransformedSteelLayer(
                    "bottom",
                    bottom_section.steel_area_mm2,
                    bottom_depth_from_bottom,
                ),
                TransformedSteelLayer(
                    "top",
                    top_section.steel_area_mm2,
                    top_depth_from_bottom,
                ),
            ),
            modular_ratio=modular_ratio,
            moment_magnitude_knm=abs(moment_knm),
        )
        return (
            section.steel_stress_mpa("bottom"),
            section.steel_stress_mpa("top"),
            0.0,
            section.compression_face_stress_mpa,
        )

    stations: list[ContinuousFatigueStationResult] = []
    for x_key, permanent_moment in sorted(permanent_by_x.items()):
        traffic = fatigue_by_x[x_key]
        minimum_total = permanent_moment + traffic.minimum_moment_knm
        maximum_total = permanent_moment + traffic.maximum_moment_knm
        bottom_min, top_min, top_concrete_min_state, bottom_concrete_min_state = state(
            minimum_total
        )
        bottom_max, top_max, top_concrete_max_state, bottom_concrete_max_state = state(
            maximum_total
        )

        bottom_range = abs(bottom_max - bottom_min)
        top_range = abs(top_max - top_min)
        bottom_fatigue = reinforcement_fatigue_check(
            reference_stress_range_mpa=bottom_range,
            lambda_s=fatigue_design.lambda_s,
            characteristic_fatigue_strength_mpa=(
                fatigue_design.characteristic_fatigue_strength_mpa
            ),
            gamma_s_fat=fatigue_design.gamma_s_fat,
            phi_fat=fatigue_design.phi_fat,
        )
        top_fatigue = reinforcement_fatigue_check(
            reference_stress_range_mpa=top_range,
            lambda_s=fatigue_design.lambda_s,
            characteristic_fatigue_strength_mpa=(
                fatigue_design.characteristic_fatigue_strength_mpa
            ),
            gamma_s_fat=fatigue_design.gamma_s_fat,
            phi_fat=fatigue_design.phi_fat,
        )

        top_c_min = min(top_concrete_min_state, top_concrete_max_state)
        top_c_max = max(top_concrete_min_state, top_concrete_max_state)
        bottom_c_min = min(bottom_concrete_min_state, bottom_concrete_max_state)
        bottom_c_max = max(bottom_concrete_min_state, bottom_concrete_max_state)
        top_concrete = concrete_compression_fatigue_check(
            sigma_c_max_mpa=top_c_max,
            sigma_c_min_mpa=top_c_min,
            fck_mpa=float(project.materials.fck_mpa),
            gamma_c=fatigue_design.concrete_gamma_c,
            alpha_cc=fatigue_design.concrete_alpha_cc,
            k1=fatigue_design.concrete_k1,
            beta_cc_t0=fatigue_design.concrete_beta_cc_t0,
        )
        bottom_concrete = concrete_compression_fatigue_check(
            sigma_c_max_mpa=bottom_c_max,
            sigma_c_min_mpa=bottom_c_min,
            fck_mpa=float(project.materials.fck_mpa),
            gamma_c=fatigue_design.concrete_gamma_c,
            alpha_cc=fatigue_design.concrete_alpha_cc,
            k1=fatigue_design.concrete_k1,
            beta_cc_t0=fatigue_design.concrete_beta_cc_t0,
        )
        stations.append(
            ContinuousFatigueStationResult(
                x_m=traffic.x_m,
                permanent_moment_knm=permanent_moment,
                traffic_minimum_moment_knm=traffic.minimum_moment_knm,
                traffic_maximum_moment_knm=traffic.maximum_moment_knm,
                minimum_total_moment_knm=minimum_total,
                maximum_total_moment_knm=maximum_total,
                bottom_steel_stress_min_mpa=bottom_min,
                bottom_steel_stress_max_mpa=bottom_max,
                top_steel_stress_min_mpa=top_min,
                top_steel_stress_max_mpa=top_max,
                bottom_reinforcement=bottom_fatigue,
                top_reinforcement=top_fatigue,
                top_concrete=top_concrete,
                bottom_concrete=bottom_concrete,
                minimum_case_id=traffic.minimum_moment_case_id,
                maximum_case_id=traffic.maximum_moment_case_id,
            )
        )

    station_tuple = tuple(stations)
    if not station_tuple:
        raise ValueError("Continuous fatigue design produced no stations.")
    return ProjectContinuousNativeFatigueResult(
        girder_index=girder_index,
        stations=station_tuple,
        governing_bottom_reinforcement=max(
            station_tuple,
            key=lambda item: item.bottom_reinforcement.utilization,
        ),
        governing_top_reinforcement=max(
            station_tuple,
            key=lambda item: item.top_reinforcement.utilization,
        ),
        governing_top_concrete=max(
            station_tuple,
            key=lambda item: item.top_concrete.utilization,
        ),
        governing_bottom_concrete=max(
            station_tuple,
            key=lambda item: item.bottom_concrete.utilization,
        ),
        status=(
            "Continuous FLM3 fatigue uses signed staged permanent moment plus native "
            "full-width traffic ranges at every production station. A two-reinforcement-"
            "layer cracked transformed section retains top and bottom steel stresses "
            "through sagging, hogging and sign reversal. Final clause/project parameter "
            "verification and independent external acceptance remain Stage 7 tasks."
        ),
    )
