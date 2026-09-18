from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    girder_bottom_width_m,
    girder_web_width_m,
)
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
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
from rc_bridge.design.eurocode_shear import (
    concrete_shear_resistance,
    required_vertical_shear_reinforcement,
)
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.project_envelope_detailing import ULSDetailingEnvelopePoint


@dataclass(frozen=True)
class LayeredEnvelopeDetailingStation:
    x_m: float
    design_moment_knm: float
    design_shear_kn: float
    raw_required_longitudinal_area_mm2: float
    shifted_required_longitudinal_area_mm2: float
    selected_bars: LongitudinalBarArrangement
    concrete_shear_resistance_kn: float
    required_asw_per_s_mm2_per_m: float
    selected_links: LinkArrangement
    moment_case_id: int
    shear_case_id: int


@dataclass(frozen=True)
class LayeredLongitudinalBarZone:
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
class LayeredLinkSpacingZone:
    x_start_m: float
    x_end_m: float
    governing_design_shear_kn: float
    governing_required_asw_per_s_mm2_per_m: float
    arrangement: LinkArrangement


@dataclass(frozen=True)
class ProjectLayeredGirderEnvelopeDetailingResult:
    envelope: tuple[ULSDetailingEnvelopePoint, ...]
    stations: tuple[LayeredEnvelopeDetailingStation, ...]
    longitudinal_zones: tuple[LayeredLongitudinalBarZone, ...]
    link_zones: tuple[LayeredLinkSpacingZone, ...]
    continuous_longitudinal_core: ContinuousBarCorePlan
    tension_shift_m: float
    status: str


def _contiguous_groups(values, signature):
    groups: list[tuple[int, int]] = []
    start = 0
    for index in range(1, len(values)):
        if signature(values[index]) != signature(values[index - 1]):
            groups.append((start, index - 1))
            start = index
    groups.append((start, len(values) - 1))
    return tuple(groups)


def _zone_bounds(
    stations: tuple[LayeredEnvelopeDetailingStation, ...],
    start_index: int,
    end_index: int,
    span_m: float,
) -> tuple[float, float]:
    start = (
        0.0
        if start_index == 0
        else 0.5 * (stations[start_index - 1].x_m + stations[start_index].x_m)
    )
    end = (
        span_m
        if end_index == len(stations) - 1
        else 0.5 * (stations[end_index].x_m + stations[end_index + 1].x_m)
    )
    return start, end


def run_project_layered_girder_envelope_detailing(
    project,
    *,
    section: LayeredGirderDesignInput,
    envelope: tuple[ULSDetailingEnvelopePoint, ...],
    cot_theta: float = 2.0,
    z_factor: float = 0.9,
    nominal_link_diameter_mm: float = 12.0,
    aggregate_size_mm: float = 20.0,
) -> ProjectLayeredGirderEnvelopeDetailingResult:
    """Create envelope-driven EC2 bar/link zones for rectangular, T and I profiles.

    The same co-located native LM1 ULS envelope used by the legacy T adapter is
    retained. Longitudinal demand is solved against the actual layered concrete
    section, bottom-bar fit uses the physical bottom width, and shear/link fit
    uses the physical web width.
    """
    if not envelope:
        raise ValueError("Envelope detailing requires at least one station.")
    if any(
        envelope[index + 1].x_m <= envelope[index].x_m
        for index in range(len(envelope) - 1)
    ):
        raise ValueError("Envelope stations must be strictly increasing.")
    span_m = float(project.geometry.span_lengths_m[0])
    if abs(envelope[0].x_m) > 1.0e-9 or abs(envelope[-1].x_m - span_m) > 1.0e-9:
        raise ValueError("Envelope detailing must cover the full simple span.")
    if z_factor <= 0.0:
        raise ValueError("z_factor must be positive.")

    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)
    concrete = concrete_properties_ec2(fck_mpa)
    layers = composite_concrete_layers(
        project.geometry, slab_width_m=section.composite_slab_width_m
    )
    tension_width_m = girder_bottom_width_m(project.geometry)
    web_width_m = girder_web_width_m(project.geometry)
    minimum_as, _ = minimum_tension_reinforcement_mm2(
        fctm_mpa=concrete.fctm_mpa,
        fyk_mpa=fyk_mpa,
        tension_zone_width_m=tension_width_m,
        effective_depth_m=section.effective_depth_m,
    )
    raw_required = tuple(
        max(
            minimum_as,
            required_tension_steel_layered(
                med_knm=point.design_moment_knm,
                layers=layers,
                effective_depth_m=section.effective_depth_m,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
            ),
        )
        for point in envelope
    )
    tension_shift_m = 0.5 * z_factor * section.effective_depth_m * cot_theta
    shifted_required = tuple(
        max(
            raw_required[index]
            for index, candidate in enumerate(envelope)
            if abs(candidate.x_m - point.x_m) <= tension_shift_m + 1.0e-9
        )
        for point in envelope
    )

    governing_bars = select_longitudinal_bar_arrangement(
        required_area_mm2=max(shifted_required),
        web_width_mm=tension_width_m * 1000.0,
        cover_mm=section.cover_mm,
        link_diameter_mm=nominal_link_diameter_mm,
        aggregate_size_mm=aggregate_size_mm,
    )
    selected_bars = tuple(
        select_longitudinal_bar_arrangement(
            required_area_mm2=required,
            web_width_mm=tension_width_m * 1000.0,
            cover_mm=section.cover_mm,
            link_diameter_mm=nominal_link_diameter_mm,
            available_diameters_mm=(governing_bars.bar_diameter_mm,),
            aggregate_size_mm=aggregate_size_mm,
        )
        for required in shifted_required
    )

    continuous_core = continuous_bar_core_plan(
        required_continuous_area_mm2=minimum_as,
        bar_diameter_mm=governing_bars.bar_diameter_mm,
        governing_arrangement_bar_count=governing_bars.bar_count,
    )
    if any(item.bar_count < continuous_core.bar_count for item in selected_bars):
        raise ValueError(
            "Envelope bar selection would curtail below the required continuous core."
        )

    _, _, minimum_asw = minimum_vertical_shear_reinforcement(
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        web_width_m=web_width_m,
    )
    max_longitudinal_spacing, max_transverse_spacing = maximum_vertical_link_spacings_mm(
        effective_depth_m=section.effective_depth_m,
    )
    required_asw: list[float] = []
    concrete_resistances: list[float] = []
    for point, bars in zip(envelope, selected_bars, strict=True):
        concrete_shear = concrete_shear_resistance(
            web_width_m,
            section.effective_depth_m,
            bars.provided_area_mm2,
            fck_mpa,
        )
        concrete_resistances.append(concrete_shear.vrdc_kn)
        design_required = 0.0
        if point.design_shear_kn > concrete_shear.vrdc_kn:
            reinforced = required_vertical_shear_reinforcement(
                point.design_shear_kn,
                web_width_m,
                section.effective_depth_m,
                fck_mpa,
                fyk_mpa,
                cot_theta=cot_theta,
                z_factor=z_factor,
            )
            if point.design_shear_kn > reinforced.vrdmax_kn + 1.0e-9:
                raise ValueError(
                    "ULS envelope shear exceeds V_Rd,max at "
                    f"x={point.x_m:.6g} m; revise the physical section before detailing."
                )
            design_required = reinforced.asw_per_s_mm2_per_m
        required_asw.append(max(minimum_asw, design_required))

    governing_links = select_vertical_link_arrangement(
        required_asw_per_s_mm2_per_m=max(required_asw),
        web_width_mm=web_width_m * 1000.0,
        maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
        maximum_transverse_leg_spacing_mm=max_transverse_spacing,
        cover_mm=section.cover_mm,
    )
    selected_links = tuple(
        select_vertical_link_arrangement(
            required_asw_per_s_mm2_per_m=required,
            web_width_mm=web_width_m * 1000.0,
            maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
            maximum_transverse_leg_spacing_mm=max_transverse_spacing,
            cover_mm=section.cover_mm,
            available_diameters_mm=(governing_links.link_diameter_mm,),
            available_legs=(governing_links.leg_count,),
        )
        for required in required_asw
    )

    stations = tuple(
        LayeredEnvelopeDetailingStation(
            x_m=point.x_m,
            design_moment_knm=point.design_moment_knm,
            design_shear_kn=point.design_shear_kn,
            raw_required_longitudinal_area_mm2=raw,
            shifted_required_longitudinal_area_mm2=shifted,
            selected_bars=bars,
            concrete_shear_resistance_kn=vrdc,
            required_asw_per_s_mm2_per_m=asw,
            selected_links=links,
            moment_case_id=point.moment_case_id,
            shear_case_id=point.shear_case_id,
        )
        for point, raw, shifted, bars, vrdc, asw, links in zip(
            envelope, raw_required, shifted_required, selected_bars,
            concrete_resistances, required_asw, selected_links, strict=True,
        )
    )

    longitudinal_zones: list[LayeredLongitudinalBarZone] = []
    for start_index, end_index in _contiguous_groups(
        stations,
        lambda item: (
            item.selected_bars.bar_diameter_mm,
            item.selected_bars.bar_count,
            item.selected_bars.layer_count,
            item.selected_bars.bars_per_layer,
        ),
    ):
        arrangement = stations[start_index].selected_bars
        start, end = _zone_bounds(stations, start_index, end_index, span_m)
        anchorage = anchorage_and_lap_lengths_mm(
            bar_diameter_mm=arrangement.bar_diameter_mm,
            fyk_mpa=fyk_mpa,
            fctd_mpa=0.7 * concrete.fctm_mpa / 1.5,
        )
        extension_m = anchorage.design_anchorage_length_mm / 1000.0
        longitudinal_zones.append(
            LayeredLongitudinalBarZone(
                x_start_m=start,
                x_end_m=end,
                anchored_start_m=max(0.0, start - extension_m),
                anchored_end_m=min(span_m, end + extension_m),
                governing_required_area_mm2=max(
                    item.shifted_required_longitudinal_area_mm2
                    for item in stations[start_index : end_index + 1]
                ),
                arrangement=arrangement,
                continuous_bar_count=continuous_core.bar_count,
                additional_curtailable_bar_count=max(
                    arrangement.bar_count - continuous_core.bar_count,
                    0,
                ),
                anchorage_length_mm=anchorage.design_anchorage_length_mm,
            )
        )

    link_zones: list[LayeredLinkSpacingZone] = []
    for start_index, end_index in _contiguous_groups(
        stations,
        lambda item: (
            item.selected_links.link_diameter_mm,
            item.selected_links.leg_count,
            item.selected_links.spacing_mm,
        ),
    ):
        arrangement = stations[start_index].selected_links
        start, end = _zone_bounds(stations, start_index, end_index, span_m)
        link_zones.append(
            LayeredLinkSpacingZone(
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
                arrangement=arrangement,
            )
        )

    return ProjectLayeredGirderEnvelopeDetailingResult(
        envelope=envelope,
        stations=stations,
        longitudinal_zones=tuple(longitudinal_zones),
        link_zones=tuple(link_zones),
        continuous_longitudinal_core=continuous_core,
        tension_shift_m=tension_shift_m,
        status=(
            "Physical rectangular/T/I simple-span envelope detailing: co-located native ULS "
            "M/V, bilateral tension-force shift, a full-span minimum continuous bar core, "
            "anchorage-extended extra-bar curtailment, and constant link-family spacing zones."
        ),
    )
