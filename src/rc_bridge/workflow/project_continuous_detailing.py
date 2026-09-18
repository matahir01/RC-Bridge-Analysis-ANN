from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    girder_bottom_width_m,
    girder_web_width_m,
)
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import (
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    TGirderProfile,
)
from rc_bridge.design.eurocode_detailing import (
    ContinuousBarCorePlan,
    LinkArrangement,
    LongitudinalBarArrangement,
    anchorage_and_lap_lengths_mm,
    continuous_bar_core_plan,
    maximum_vertical_link_spacings_mm,
    minimum_tension_reinforcement_mm2,
    minimum_vertical_shear_reinforcement,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
from rc_bridge.design.eurocode_layered_section import required_tension_steel_layered
from rc_bridge.design.eurocode_oriented_demand import (
    required_tension_steel_oriented_flanged,
)
from rc_bridge.design.eurocode_shear import (
    concrete_shear_resistance,
    required_vertical_shear_reinforcement,
)
from rc_bridge.design.eurocode_torsion_detailing import (
    TorsionCageDetailingResult,
    select_torsion_cage_detailing,
)
from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.workflow.project_continuous_native import (
    ProjectContinuousNativeLM1EnvelopeResult,
)
from rc_bridge.workflow.project_continuous_native_torsion import (
    ProjectContinuousNativeShearTorsionResult,
)


@dataclass(frozen=True)
class ContinuousLongitudinalDetailingInput:
    bottom_composite_slab_width_m: float
    bottom_effective_depth_from_top_m: float
    bottom_cover_mm: float
    top_effective_deck_width_m: float
    top_effective_depth_from_bottom_m: float
    top_cover_mm: float
    nominal_link_diameter_mm: float = 12.0
    aggregate_size_mm: float = 20.0
    cot_theta: float = 2.0
    z_factor: float = 0.9

    def __post_init__(self) -> None:
        if min(
            self.bottom_composite_slab_width_m,
            self.bottom_effective_depth_from_top_m,
            self.bottom_cover_mm,
            self.top_effective_deck_width_m,
            self.top_effective_depth_from_bottom_m,
            self.top_cover_mm,
            self.nominal_link_diameter_mm,
            self.aggregate_size_mm,
            self.cot_theta,
            self.z_factor,
        ) <= 0.0:
            raise ValueError("Continuous detailing geometry and factors must be positive.")
        if not 1.0 <= self.cot_theta <= 2.5:
            raise ValueError("cot_theta must lie between 1.0 and 2.5.")


@dataclass(frozen=True)
class ContinuousDetailingStation:
    x_m: float
    positive_design_moment_knm: float
    negative_design_moment_knm: float
    design_shear_kn: float
    raw_bottom_required_area_mm2: float
    shifted_bottom_required_area_mm2: float
    bottom_bars: LongitudinalBarArrangement
    raw_top_required_area_mm2: float
    shifted_top_required_area_mm2: float
    top_bars: LongitudinalBarArrangement
    concrete_shear_resistance_kn: float
    required_asw_per_s_mm2_per_m: float
    links: LinkArrangement


@dataclass(frozen=True)
class ContinuousLongitudinalBarZone:
    face: Literal["bottom", "top"]
    x_start_m: float
    x_end_m: float
    anchored_start_m: float
    anchored_end_m: float
    governing_required_area_mm2: float
    arrangement: LongitudinalBarArrangement
    continuous_bar_count: int
    additional_curtailable_bar_count: int
    anchorage_length_mm: float


@dataclass(frozen=True)
class ContinuousLinkSpacingZone:
    x_start_m: float
    x_end_m: float
    governing_design_shear_kn: float
    governing_required_asw_per_s_mm2_per_m: float
    arrangement: LinkArrangement


@dataclass(frozen=True)
class ProjectContinuousDetailingResult:
    stations: tuple[ContinuousDetailingStation, ...]
    bottom_zones: tuple[ContinuousLongitudinalBarZone, ...]
    top_zones: tuple[ContinuousLongitudinalBarZone, ...]
    link_zones: tuple[ContinuousLinkSpacingZone, ...]
    bottom_continuous_core: ContinuousBarCorePlan
    top_continuous_core: ContinuousBarCorePlan
    tension_shift_m: float
    torsion_cage: TorsionCageDetailingResult | None
    status: str


@dataclass(frozen=True)
class _CollapsedDemand:
    x_m: float
    positive_moment_knm: float
    negative_moment_knm: float
    shear_kn: float


def _collapse_station_side_demands(
    production: ProjectContinuousNativeLM1EnvelopeResult,
) -> tuple[_CollapsedDemand, ...]:
    by_x: dict[float, list] = {}
    for station in production.envelope.stations:
        by_x.setdefault(round(station.global_position_m, 12), []).append(station)

    collapsed: list[_CollapsedDemand] = []
    for x_m, stations in sorted(by_x.items()):
        collapsed.append(
            _CollapsedDemand(
                x_m=x_m,
                positive_moment_knm=max(
                    0.0,
                    max(
                        item.moment_combinations.positive_uls_effect
                        for item in stations
                    ),
                ),
                negative_moment_knm=max(
                    0.0,
                    max(
                        -item.moment_combinations.negative_uls_effect
                        for item in stations
                    ),
                ),
                shear_kn=max(
                    max(
                        abs(item.shear_combinations.positive_uls_effect),
                        abs(item.shear_combinations.negative_uls_effect),
                    )
                    for item in stations
                ),
            )
        )
    if len(collapsed) < 2:
        raise ValueError("Continuous detailing requires at least two longitudinal stations.")
    return tuple(collapsed)


def _required_top_area_mm2(
    project: ProjectInput,
    *,
    moment_knm: float,
    effective_depth_from_bottom_m: float,
) -> float:
    if moment_knm <= 0.0:
        return 0.0
    profile = project.geometry.girder_profile
    if profile is None:
        raise ValueError("Continuous detailing requires a physical girder profile.")
    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)
    if isinstance(profile, IGirderProfile):
        return required_tension_steel_oriented_flanged(
            moment_knm,
            float(profile.bottom_flange_width_m),
            float(profile.bottom_flange_thickness_m),
            float(profile.web_width_m),
            effective_depth_from_bottom_m,
            fck_mpa,
            fyk_mpa,
            compression_face="bottom",
        )
    if isinstance(profile, TGirderProfile):
        compression_width_m = float(profile.web_width_m)
    elif isinstance(profile, RectangularGirderProfile):
        compression_width_m = float(profile.width_m)
    else:
        raise TypeError("Unsupported physical girder profile.")
    return required_tension_steel_rectangular(
        moment_knm,
        compression_width_m,
        effective_depth_from_bottom_m,
        fck_mpa,
        fyk_mpa,
    )


def _shift_demands(
    x_values: tuple[float, ...],
    raw: tuple[float, ...],
    shift_m: float,
) -> tuple[float, ...]:
    return tuple(
        max(
            raw[index]
            for index, candidate_x in enumerate(x_values)
            if abs(candidate_x - x_m) <= shift_m + 1.0e-9
        )
        for x_m in x_values
    )


def _groups(values, signature):
    groups: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(values)):
        if signature(values[index]) != signature(values[index - 1]):
            groups.append((start, index - 1))
            start = index
    groups.append((start, len(values) - 1))
    return tuple(groups)


def _zone_bounds(
    stations: tuple[ContinuousDetailingStation, ...],
    start_index: int,
    end_index: int,
    total_length_m: float,
) -> tuple[float, float]:
    start = (
        0.0
        if start_index == 0
        else 0.5 * (stations[start_index - 1].x_m + stations[start_index].x_m)
    )
    end = (
        total_length_m
        if end_index == len(stations) - 1
        else 0.5 * (stations[end_index].x_m + stations[end_index + 1].x_m)
    )
    return start, end


def _longitudinal_zones(
    *,
    stations: tuple[ContinuousDetailingStation, ...],
    face: Literal["bottom", "top"],
    core: ContinuousBarCorePlan,
    total_length_m: float,
    fyk_mpa: float,
    fctm_mpa: float,
) -> tuple[ContinuousLongitudinalBarZone, ...]:
    arrangement_of = (
        (lambda item: item.bottom_bars)
        if face == "bottom"
        else (lambda item: item.top_bars)
    )
    required_of = (
        (lambda item: item.shifted_bottom_required_area_mm2)
        if face == "bottom"
        else (lambda item: item.shifted_top_required_area_mm2)
    )
    zones: list[ContinuousLongitudinalBarZone] = []
    for start_index, end_index in _groups(
        stations,
        lambda item: (
            arrangement_of(item).bar_diameter_mm,
            arrangement_of(item).bar_count,
            arrangement_of(item).layer_count,
            arrangement_of(item).bars_per_layer,
        ),
    ):
        arrangement = arrangement_of(stations[start_index])
        start, end = _zone_bounds(
            stations,
            start_index,
            end_index,
            total_length_m,
        )
        anchorage = anchorage_and_lap_lengths_mm(
            bar_diameter_mm=arrangement.bar_diameter_mm,
            fyk_mpa=fyk_mpa,
            fctd_mpa=0.7 * fctm_mpa / 1.5,
        )
        extension_m = anchorage.design_anchorage_length_mm / 1000.0
        zones.append(
            ContinuousLongitudinalBarZone(
                face=face,
                x_start_m=start,
                x_end_m=end,
                anchored_start_m=max(0.0, start - extension_m),
                anchored_end_m=min(total_length_m, end + extension_m),
                governing_required_area_mm2=max(
                    required_of(item)
                    for item in stations[start_index : end_index + 1]
                ),
                arrangement=arrangement,
                continuous_bar_count=core.bar_count,
                additional_curtailable_bar_count=max(
                    arrangement.bar_count - core.bar_count,
                    0,
                ),
                anchorage_length_mm=anchorage.design_anchorage_length_mm,
            )
        )
    return tuple(zones)


def run_project_continuous_native_detailing(
    project: ProjectInput,
    *,
    production: ProjectContinuousNativeLM1EnvelopeResult,
    detailing: ContinuousLongitudinalDetailingInput,
    torsion: ProjectContinuousNativeShearTorsionResult | None = None,
) -> ProjectContinuousDetailingResult:
    """Generate continuous top/bottom bar zones and link zones from native ULS demand."""
    if project.geometry.girder_profile is None:
        raise ValueError("Continuous detailing requires a physical girder profile.")
    total_depth_m = (
        float(project.geometry.girder_depth_m)
        + float(project.geometry.physical_deck_depth_m)
    )
    if detailing.bottom_effective_depth_from_top_m >= total_depth_m:
        raise ValueError("Bottom effective depth must lie inside the physical section.")
    if detailing.top_effective_depth_from_bottom_m >= total_depth_m:
        raise ValueError("Top effective depth must lie inside the physical section.")
    if detailing.top_effective_deck_width_m > float(project.geometry.deck_width_m) + 1.0e-9:
        raise ValueError("Top effective deck width cannot exceed the physical deck width.")

    demands = _collapse_station_side_demands(production)
    x_values = tuple(item.x_m for item in demands)
    total_length_m = sum(float(value) for value in project.geometry.span_lengths_m)
    if abs(x_values[0]) > 1.0e-9 or abs(x_values[-1] - total_length_m) > 1.0e-9:
        raise ValueError("Continuous detailing stations must cover the full bridge length.")

    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)
    concrete = concrete_properties_ec2(fck_mpa)
    positive_layers = composite_concrete_layers(
        project.geometry,
        slab_width_m=detailing.bottom_composite_slab_width_m,
    )
    bottom_width_m = girder_bottom_width_m(project.geometry)
    web_width_m = girder_web_width_m(project.geometry)

    bottom_minimum, _ = minimum_tension_reinforcement_mm2(
        fctm_mpa=concrete.fctm_mpa,
        fyk_mpa=fyk_mpa,
        tension_zone_width_m=bottom_width_m,
        effective_depth_m=detailing.bottom_effective_depth_from_top_m,
    )
    top_minimum, _ = minimum_tension_reinforcement_mm2(
        fctm_mpa=concrete.fctm_mpa,
        fyk_mpa=fyk_mpa,
        tension_zone_width_m=detailing.top_effective_deck_width_m,
        effective_depth_m=detailing.top_effective_depth_from_bottom_m,
    )

    raw_bottom = tuple(
        max(
            bottom_minimum,
            required_tension_steel_layered(
                med_knm=item.positive_moment_knm,
                layers=positive_layers,
                effective_depth_m=detailing.bottom_effective_depth_from_top_m,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
            ),
        )
        for item in demands
    )
    raw_top = tuple(
        max(
            top_minimum,
            _required_top_area_mm2(
                project,
                moment_knm=item.negative_moment_knm,
                effective_depth_from_bottom_m=(
                    detailing.top_effective_depth_from_bottom_m
                ),
            ),
        )
        for item in demands
    )

    shear_effective_depth_m = min(
        detailing.bottom_effective_depth_from_top_m,
        detailing.top_effective_depth_from_bottom_m,
    )
    tension_shift_m = (
        0.5
        * detailing.z_factor
        * shear_effective_depth_m
        * detailing.cot_theta
    )
    shifted_bottom = _shift_demands(x_values, raw_bottom, tension_shift_m)
    shifted_top = _shift_demands(x_values, raw_top, tension_shift_m)

    governing_bottom = select_longitudinal_bar_arrangement(
        required_area_mm2=max(shifted_bottom),
        web_width_mm=bottom_width_m * 1000.0,
        cover_mm=detailing.bottom_cover_mm,
        link_diameter_mm=detailing.nominal_link_diameter_mm,
        aggregate_size_mm=detailing.aggregate_size_mm,
    )
    governing_top = select_longitudinal_bar_arrangement(
        required_area_mm2=max(shifted_top),
        web_width_mm=detailing.top_effective_deck_width_m * 1000.0,
        cover_mm=detailing.top_cover_mm,
        link_diameter_mm=detailing.nominal_link_diameter_mm,
        aggregate_size_mm=detailing.aggregate_size_mm,
    )
    bottom_bars = tuple(
        select_longitudinal_bar_arrangement(
            required_area_mm2=value,
            web_width_mm=bottom_width_m * 1000.0,
            cover_mm=detailing.bottom_cover_mm,
            link_diameter_mm=detailing.nominal_link_diameter_mm,
            available_diameters_mm=(governing_bottom.bar_diameter_mm,),
            aggregate_size_mm=detailing.aggregate_size_mm,
        )
        for value in shifted_bottom
    )
    top_bars = tuple(
        select_longitudinal_bar_arrangement(
            required_area_mm2=value,
            web_width_mm=detailing.top_effective_deck_width_m * 1000.0,
            cover_mm=detailing.top_cover_mm,
            link_diameter_mm=detailing.nominal_link_diameter_mm,
            available_diameters_mm=(governing_top.bar_diameter_mm,),
            aggregate_size_mm=detailing.aggregate_size_mm,
        )
        for value in shifted_top
    )
    bottom_core = continuous_bar_core_plan(
        required_continuous_area_mm2=bottom_minimum,
        bar_diameter_mm=governing_bottom.bar_diameter_mm,
        governing_arrangement_bar_count=governing_bottom.bar_count,
    )
    top_core = continuous_bar_core_plan(
        required_continuous_area_mm2=top_minimum,
        bar_diameter_mm=governing_top.bar_diameter_mm,
        governing_arrangement_bar_count=governing_top.bar_count,
    )
    if any(item.bar_count < bottom_core.bar_count for item in bottom_bars):
        raise ValueError("Bottom bar selection would curtail below the continuous core.")
    if any(item.bar_count < top_core.bar_count for item in top_bars):
        raise ValueError("Top bar selection would curtail below the continuous core.")

    _, _, minimum_asw = minimum_vertical_shear_reinforcement(
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        web_width_m=web_width_m,
    )
    max_longitudinal_spacing, max_transverse_spacing = (
        maximum_vertical_link_spacings_mm(
            effective_depth_m=shear_effective_depth_m,
        )
    )
    required_asw: list[float] = []
    concrete_resistance: list[float] = []
    for demand, bottom, top in zip(
        demands,
        bottom_bars,
        top_bars,
        strict=True,
    ):
        conservative_longitudinal_area = min(
            bottom.provided_area_mm2,
            top.provided_area_mm2,
        )
        vrdc = concrete_shear_resistance(
            web_width_m,
            shear_effective_depth_m,
            conservative_longitudinal_area,
            fck_mpa,
        )
        concrete_resistance.append(vrdc.vrdc_kn)
        design_required = 0.0
        if demand.shear_kn > vrdc.vrdc_kn:
            reinforced = required_vertical_shear_reinforcement(
                demand.shear_kn,
                web_width_m,
                shear_effective_depth_m,
                fck_mpa,
                fyk_mpa,
                cot_theta=detailing.cot_theta,
                z_factor=detailing.z_factor,
            )
            if demand.shear_kn > reinforced.vrdmax_kn + 1.0e-9:
                raise ValueError(
                    "Continuous ULS shear exceeds V_Rd,max at "
                    f"x={demand.x_m:.6g} m; revise the physical section."
                )
            design_required = reinforced.asw_per_s_mm2_per_m
        required_asw.append(max(minimum_asw, design_required))

    governing_links = select_vertical_link_arrangement(
        required_asw_per_s_mm2_per_m=max(required_asw),
        web_width_mm=web_width_m * 1000.0,
        maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
        maximum_transverse_leg_spacing_mm=max_transverse_spacing,
        cover_mm=max(detailing.bottom_cover_mm, detailing.top_cover_mm),
    )
    links = tuple(
        select_vertical_link_arrangement(
            required_asw_per_s_mm2_per_m=value,
            web_width_mm=web_width_m * 1000.0,
            maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
            maximum_transverse_leg_spacing_mm=max_transverse_spacing,
            cover_mm=max(detailing.bottom_cover_mm, detailing.top_cover_mm),
            available_diameters_mm=(governing_links.link_diameter_mm,),
            available_legs=(governing_links.leg_count,),
        )
        for value in required_asw
    )

    stations = tuple(
        ContinuousDetailingStation(
            x_m=demand.x_m,
            positive_design_moment_knm=demand.positive_moment_knm,
            negative_design_moment_knm=demand.negative_moment_knm,
            design_shear_kn=demand.shear_kn,
            raw_bottom_required_area_mm2=raw_bottom[index],
            shifted_bottom_required_area_mm2=shifted_bottom[index],
            bottom_bars=bottom_bars[index],
            raw_top_required_area_mm2=raw_top[index],
            shifted_top_required_area_mm2=shifted_top[index],
            top_bars=top_bars[index],
            concrete_shear_resistance_kn=concrete_resistance[index],
            required_asw_per_s_mm2_per_m=required_asw[index],
            links=links[index],
        )
        for index, demand in enumerate(demands)
    )

    bottom_zones = _longitudinal_zones(
        stations=stations,
        face="bottom",
        core=bottom_core,
        total_length_m=total_length_m,
        fyk_mpa=fyk_mpa,
        fctm_mpa=concrete.fctm_mpa,
    )
    top_zones = _longitudinal_zones(
        stations=stations,
        face="top",
        core=top_core,
        total_length_m=total_length_m,
        fyk_mpa=fyk_mpa,
        fctm_mpa=concrete.fctm_mpa,
    )

    link_zones: list[ContinuousLinkSpacingZone] = []
    for start_index, end_index in _groups(
        stations,
        lambda item: (
            item.links.link_diameter_mm,
            item.links.leg_count,
            item.links.spacing_mm,
        ),
    ):
        start, end = _zone_bounds(
            stations,
            start_index,
            end_index,
            total_length_m,
        )
        link_zones.append(
            ContinuousLinkSpacingZone(
                x_start_m=start,
                x_end_m=end,
                governing_design_shear_kn=max(
                    item.design_shear_kn
                    for item in stations[start_index : end_index + 1]
                ),
                governing_required_asw_per_s_mm2_per_m=max(
                    item.required_asw_per_s_mm2_per_m
                    for item in stations[start_index : end_index + 1]
                ),
                arrangement=stations[start_index].links,
            )
        )

    torsion_cage = None
    if torsion is not None:
        production_girder = production.trace[0].girder_index
        if torsion.girder_index != production_girder:
            raise ValueError("Torsion result girder does not match continuous detailing.")
        required_shear = max(
            max(required_asw),
            max(
                item.shear_strut.asw_per_s_mm2_per_m
                for item in torsion.evaluated_points
            ),
        )
        required_torsion_links = max(
            item.torsion.transverse_asw_per_s_mm2_per_m
            for item in torsion.evaluated_points
        )
        required_torsion_longitudinal = max(
            item.torsion.longitudinal_asl_mm2
            for item in torsion.evaluated_points
        )
        torsion_cage = select_torsion_cage_detailing(
            required_shear_asw_per_s_mm2_per_m=required_shear,
            required_torsion_leg_asw_per_s_mm2_per_m=required_torsion_links,
            required_torsion_longitudinal_area_mm2=required_torsion_longitudinal,
            torsion_cell_perimeter_m=torsion.torsion_cell.uk_m,
            web_width_mm=web_width_m * 1000.0,
            cover_mm=max(detailing.bottom_cover_mm, detailing.top_cover_mm),
            maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
            maximum_transverse_leg_spacing_mm=max_transverse_spacing,
            maximum_torsion_link_spacing_mm=(
                torsion.torsion_cell.uk_m * 1000.0 / 8.0
            ),
            maximum_longitudinal_torsion_bar_spacing_mm=350.0,
        )

    return ProjectContinuousDetailingResult(
        stations=stations,
        bottom_zones=bottom_zones,
        top_zones=top_zones,
        link_zones=tuple(link_zones),
        bottom_continuous_core=bottom_core,
        top_continuous_core=top_core,
        tension_shift_m=tension_shift_m,
        torsion_cage=torsion_cage,
        status=(
            "Continuous native ULS detailing retains full-length minimum top and bottom "
            "bar cores, applies bilateral tension-force shifting, creates anchorage-extended "
            "additional-bar zones and constant-family link spacing zones across the bridge. "
            "When a matched continuous V-T result is supplied, a conservative full-length "
            "closed-link/perimeter-bar torsion cage family is also selected. Exact bends, "
            "couplers, stock-length optimisation and local end/support congestion remain "
            "final drawing tasks."
        ),
    )
