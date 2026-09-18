from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from rc_bridge.analysis.simple_span import simple_span_distributed_response_at_x
from rc_bridge.codes.eurocode.combinations import EurocodeFactors
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.design.eurocode_demand import required_tension_steel_t_section
from rc_bridge.design.eurocode_detailing import (
    LinkArrangement,
    LongitudinalBarArrangement,
    anchorage_and_lap_lengths_mm,
    maximum_vertical_link_spacings_mm,
    minimum_tension_reinforcement_mm2,
    minimum_vertical_shear_reinforcement,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
from rc_bridge.design.eurocode_shear import (
    concrete_shear_resistance,
    required_vertical_shear_reinforcement,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    girder_span_permanent_load_segments,
)


@dataclass(frozen=True)
class ULSDetailingEnvelopePoint:
    """Traceable simple-span ULS design effects at one longitudinal station."""

    x_m: float
    permanent_moment_knm: float
    permanent_shear_kn: float
    traffic_moment_knm: float
    traffic_shear_kn: float
    design_moment_knm: float
    design_shear_kn: float
    moment_case_id: int
    moment_member_id: int
    shear_case_id: int
    shear_member_id: int


@dataclass(frozen=True)
class EnvelopeDetailingStation:
    """Reinforcement demand and selected discrete detail at one station."""

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
class LongitudinalBarZone:
    """Constant total longitudinal-bar arrangement over one theoretical zone."""

    x_start_m: float
    x_end_m: float
    anchored_start_m: float
    anchored_end_m: float
    governing_required_area_mm2: float
    arrangement: LongitudinalBarArrangement
    anchorage_length_mm: float


@dataclass(frozen=True)
class LinkSpacingZone:
    """Constant link diameter/legs/spacing over one longitudinal zone."""

    x_start_m: float
    x_end_m: float
    governing_design_shear_kn: float
    governing_required_asw_per_s_mm2_per_m: float
    arrangement: LinkArrangement


@dataclass(frozen=True)
class ProjectTGirderEnvelopeDetailingResult:
    """Envelope-driven simple-span EC2 reinforcement schedule."""

    envelope: tuple[ULSDetailingEnvelopePoint, ...]
    stations: tuple[EnvelopeDetailingStation, ...]
    longitudinal_zones: tuple[LongitudinalBarZone, ...]
    link_zones: tuple[LinkSpacingZone, ...]
    tension_shift_m: float
    status: str


@dataclass(frozen=True)
class _NativeGirderSegment:
    x_start_m: float
    x_end_m: float
    member_id: int
    moment_start_knm: float
    moment_end_knm: float

    @property
    def shear_kn(self) -> float:
        return (self.moment_end_knm - self.moment_start_knm) / (
            self.x_end_m - self.x_start_m
        )

    def moment_at(self, x_m: float) -> float:
        ratio = (x_m - self.x_start_m) / (self.x_end_m - self.x_start_m)
        ratio = min(max(ratio, 0.0), 1.0)
        return self.moment_start_knm + ratio * (
            self.moment_end_knm - self.moment_start_knm
        )


def _native_girder_segments(
    case: object,
    *,
    target_y_m: float,
    coordinate_tolerance_m: float = 1.0e-9,
) -> tuple[_NativeGirderSegment, ...]:
    if not hasattr(case, "model") or not hasattr(case, "analysis"):
        raise RuntimeError(
            "Envelope-driven native LM1 detailing requires solved physical search cases."
        )
    model = case.model
    analysis = case.analysis
    nodes = {node.node_id: node for node in model.nodes}
    results = {item.member_id: item for item in analysis.members}
    segments: list[_NativeGirderSegment] = []
    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(ni.y_m - target_y_m) > coordinate_tolerance_m
            or abs(nj.y_m - target_y_m) > coordinate_tolerance_m
            or abs(nj.x_m - ni.x_m) <= coordinate_tolerance_m
        ):
            continue
        end = results[beam.member_id]
        # The solver's recovered internal longitudinal convention is negative
        # for simple-span sagging. Detailing uses the bridge convention of
        # sagging-positive M so that dM/dx also yields the usual signed shear.
        moment_i = end.i_vertical_bending_moment_knm
        moment_j = -end.j_vertical_bending_moment_knm
        if nj.x_m > ni.x_m:
            segments.append(
                _NativeGirderSegment(
                    x_start_m=ni.x_m,
                    x_end_m=nj.x_m,
                    member_id=beam.member_id,
                    moment_start_knm=moment_i,
                    moment_end_knm=moment_j,
                )
            )
        else:
            segments.append(
                _NativeGirderSegment(
                    x_start_m=nj.x_m,
                    x_end_m=ni.x_m,
                    member_id=beam.member_id,
                    moment_start_knm=moment_j,
                    moment_end_knm=moment_i,
                )
            )
    segments.sort(key=lambda item: (item.x_start_m, item.x_end_m, item.member_id))
    if not segments:
        raise RuntimeError("No longitudinal native grillage members found for the girder.")
    return tuple(segments)


def _section_candidates(
    segments: tuple[_NativeGirderSegment, ...],
    x_m: float,
    *,
    coordinate_tolerance_m: float = 1.0e-9,
) -> tuple[tuple[float, float, int], ...]:
    candidates = tuple(
        (segment.moment_at(x_m), segment.shear_kn, segment.member_id)
        for segment in segments
        if (
            segment.x_start_m - coordinate_tolerance_m
            <= x_m
            <= segment.x_end_m + coordinate_tolerance_m
        )
    )
    if not candidates:
        raise RuntimeError(
            f"Native girder force recovery found no member at x={x_m:.6g} m."
        )
    return candidates


def native_lm1_uls_detailing_envelope(
    project,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    girder_index: int,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    station_step_m: float = 0.25,
) -> tuple[ULSDetailingEnvelopePoint, ...]:
    """Build a signed, co-located simple-span ULS M/V envelope for detailing.

    Every native LM1 search case is interrogated at a common station set. Traffic
    moments are recovered by interpolation of the load-free longitudinal member
    end moments; traffic shear follows dM/dx within each member. Permanent M/V
    comes from the exact segmented permanent-load pattern. Shear uses directional
    favourable/unfavourable permanent factors before the absolute design envelope
    is selected, rather than adding unrelated absolute maxima.
    """
    if station_step_m <= 0.0:
        raise ValueError("station_step_m must be positive.")
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError("Envelope-driven native detailing currently requires one span.")
    if not search.cases:
        raise ValueError("Native LM1 search contains no cases.")
    target = next(
        (item for item in search.girders if item.girder_index == girder_index),
        None,
    )
    if target is None:
        raise IndexError("girder_index is outside the native LM1 search result.")

    span_m = float(project.geometry.span_lengths_m[0])
    permanent_loads = girder_span_permanent_load_segments(
        project,
        girder_index=girder_index,
        additional=additional_permanent,
    )
    case_segments = tuple(
        (
            case.placement.case_id,
            _native_girder_segments(case, target_y_m=target.y_m),
        )
        for case in search.cases
    )

    stations = {0.0, span_m}
    divisions = max(1, ceil(span_m / station_step_m))
    stations.update(min(index * station_step_m, span_m) for index in range(divisions + 1))
    for load in permanent_loads:
        stations.update((load.start_m, load.end_m))
    for _, segments in case_segments:
        for segment in segments:
            stations.update((segment.x_start_m, segment.x_end_m))
    ordered = tuple(sorted(round(value, 10) for value in stations))

    factors = uls_factors or EurocodeFactors()
    results: list[ULSDetailingEnvelopePoint] = []
    for x_m in ordered:
        permanent_moment, permanent_shear = simple_span_distributed_response_at_x(
            span_m,
            permanent_loads,
            x_m,
        )
        positive_gamma_g = (
            factors.gamma_g_unfavourable
            if permanent_moment >= 0.0
            else factors.gamma_g_favourable
        )
        shear_positive_gamma_g = (
            factors.gamma_g_unfavourable
            if permanent_shear >= 0.0
            else factors.gamma_g_favourable
        )
        shear_negative_gamma_g = (
            factors.gamma_g_unfavourable
            if permanent_shear <= 0.0
            else factors.gamma_g_favourable
        )

        best_moment = 0.0
        best_moment_q = 0.0
        best_moment_case = case_segments[0][0]
        best_moment_member = case_segments[0][1][0].member_id

        best_shear_magnitude = 0.0
        best_shear_q = 0.0
        best_shear_case = case_segments[0][0]
        best_shear_member = case_segments[0][1][0].member_id

        for case_id, segments in case_segments:
            for traffic_moment, traffic_shear, member_id in _section_candidates(
                segments,
                x_m,
            ):
                design_moment = (
                    positive_gamma_g * permanent_moment
                    + factors.gamma_q_traffic * traffic_moment
                )
                if design_moment > best_moment:
                    best_moment = design_moment
                    best_moment_q = traffic_moment
                    best_moment_case = case_id
                    best_moment_member = member_id

                positive_shear = (
                    shear_positive_gamma_g * permanent_shear
                    + factors.gamma_q_traffic * traffic_shear
                )
                negative_shear = (
                    shear_negative_gamma_g * permanent_shear
                    + factors.gamma_q_traffic * traffic_shear
                )
                for design_shear in (positive_shear, negative_shear):
                    if abs(design_shear) > best_shear_magnitude:
                        best_shear_magnitude = abs(design_shear)
                        best_shear_q = traffic_shear
                        best_shear_case = case_id
                        best_shear_member = member_id

        results.append(
            ULSDetailingEnvelopePoint(
                x_m=x_m,
                permanent_moment_knm=permanent_moment,
                permanent_shear_kn=permanent_shear,
                traffic_moment_knm=best_moment_q,
                traffic_shear_kn=best_shear_q,
                design_moment_knm=max(best_moment, 0.0),
                design_shear_kn=best_shear_magnitude,
                moment_case_id=best_moment_case,
                moment_member_id=best_moment_member,
                shear_case_id=best_shear_case,
                shear_member_id=best_shear_member,
            )
        )
    return tuple(results)


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
    stations: tuple[EnvelopeDetailingStation, ...],
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


def run_project_t_girder_envelope_detailing(
    project,
    *,
    section: TGirderDesignInput,
    envelope: tuple[ULSDetailingEnvelopePoint, ...],
    cot_theta: float = 2.0,
    z_factor: float = 0.9,
    nominal_link_diameter_mm: float = 12.0,
    aggregate_size_mm: float = 20.0,
) -> ProjectTGirderEnvelopeDetailingResult:
    """Turn a simple-span ULS envelope into practical bar and link zones.

    The longitudinal tension-force envelope is conservatively shifted both ways
    by a_l = z*cot(theta)/2 before bar selection. One governing bar diameter is
    retained along the span while total bar count/layers may reduce. Theoretical
    curtailment-zone limits are extended by the calculated straight-bar design
    anchorage length and clipped to the span.

    Links retain one governing diameter/leg count and vary only their spacing,
    producing constructible support-to-midspan spacing zones.
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

    concrete = concrete_properties_ec2(float(project.materials.fck_mpa))
    minimum_as, _ = minimum_tension_reinforcement_mm2(
        fctm_mpa=concrete.fctm_mpa,
        fyk_mpa=float(project.materials.fyk_mpa),
        tension_zone_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
    )
    raw_required = tuple(
        max(
            minimum_as,
            required_tension_steel_t_section(
                point.design_moment_knm,
                section.effective_flange_width_m,
                section.flange_thickness_m,
                section.web_width_m,
                section.effective_depth_m,
                float(project.materials.fck_mpa),
                float(project.materials.fyk_mpa),
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
        web_width_mm=section.web_width_m * 1000.0,
        cover_mm=section.cover_mm,
        link_diameter_mm=nominal_link_diameter_mm,
        aggregate_size_mm=aggregate_size_mm,
    )
    selected_bars = tuple(
        select_longitudinal_bar_arrangement(
            required_area_mm2=required,
            web_width_mm=section.web_width_m * 1000.0,
            cover_mm=section.cover_mm,
            link_diameter_mm=nominal_link_diameter_mm,
            available_diameters_mm=(governing_bars.bar_diameter_mm,),
            aggregate_size_mm=aggregate_size_mm,
        )
        for required in shifted_required
    )

    minimum_rho_w, _, minimum_asw = minimum_vertical_shear_reinforcement(
        fck_mpa=float(project.materials.fck_mpa),
        fyk_mpa=float(project.materials.fyk_mpa),
        web_width_m=section.web_width_m,
    )
    del minimum_rho_w
    max_longitudinal_spacing, max_transverse_spacing = maximum_vertical_link_spacings_mm(
        effective_depth_m=section.effective_depth_m,
    )

    required_asw: list[float] = []
    concrete_resistances: list[float] = []
    for point, bars in zip(envelope, selected_bars, strict=True):
        concrete_shear = concrete_shear_resistance(
            section.web_width_m,
            section.effective_depth_m,
            bars.provided_area_mm2,
            float(project.materials.fck_mpa),
        )
        concrete_resistances.append(concrete_shear.vrdc_kn)
        design_required = 0.0
        if point.design_shear_kn > concrete_shear.vrdc_kn:
            reinforced = required_vertical_shear_reinforcement(
                point.design_shear_kn,
                section.web_width_m,
                section.effective_depth_m,
                float(project.materials.fck_mpa),
                float(project.materials.fyk_mpa),
                cot_theta=cot_theta,
                z_factor=z_factor,
            )
            if point.design_shear_kn > reinforced.vrdmax_kn + 1.0e-9:
                raise ValueError(
                    "ULS envelope shear exceeds V_Rd,max at "
                    f"x={point.x_m:.6g} m; revise the section before detailing."
                )
            design_required = reinforced.asw_per_s_mm2_per_m
        required_asw.append(max(minimum_asw, design_required))

    governing_links = select_vertical_link_arrangement(
        required_asw_per_s_mm2_per_m=max(required_asw),
        web_width_mm=section.web_width_m * 1000.0,
        maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
        maximum_transverse_leg_spacing_mm=max_transverse_spacing,
        cover_mm=section.cover_mm,
    )
    selected_links = tuple(
        select_vertical_link_arrangement(
            required_asw_per_s_mm2_per_m=required,
            web_width_mm=section.web_width_m * 1000.0,
            maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
            maximum_transverse_leg_spacing_mm=max_transverse_spacing,
            cover_mm=section.cover_mm,
            available_diameters_mm=(governing_links.link_diameter_mm,),
            available_legs=(governing_links.leg_count,),
        )
        for required in required_asw
    )

    stations = tuple(
        EnvelopeDetailingStation(
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
            envelope,
            raw_required,
            shifted_required,
            selected_bars,
            concrete_resistances,
            required_asw,
            selected_links,
            strict=True,
        )
    )

    longitudinal_zones: list[LongitudinalBarZone] = []
    bar_groups = _contiguous_groups(
        stations,
        lambda item: (
            item.selected_bars.bar_diameter_mm,
            item.selected_bars.bar_count,
            item.selected_bars.layer_count,
            item.selected_bars.bars_per_layer,
        ),
    )
    for start_index, end_index in bar_groups:
        arrangement = stations[start_index].selected_bars
        start, end = _zone_bounds(stations, start_index, end_index, span_m)
        anchorage = anchorage_and_lap_lengths_mm(
            bar_diameter_mm=arrangement.bar_diameter_mm,
            fyk_mpa=float(project.materials.fyk_mpa),
            fctd_mpa=0.7 * concrete.fctm_mpa / 1.5,
        )
        extension_m = anchorage.design_anchorage_length_mm / 1000.0
        longitudinal_zones.append(
            LongitudinalBarZone(
                x_start_m=start,
                x_end_m=end,
                anchored_start_m=max(0.0, start - extension_m),
                anchored_end_m=min(span_m, end + extension_m),
                governing_required_area_mm2=max(
                    item.shifted_required_longitudinal_area_mm2
                    for item in stations[start_index : end_index + 1]
                ),
                arrangement=arrangement,
                anchorage_length_mm=anchorage.design_anchorage_length_mm,
            )
        )

    link_zones: list[LinkSpacingZone] = []
    link_groups = _contiguous_groups(
        stations,
        lambda item: (
            item.selected_links.link_diameter_mm,
            item.selected_links.leg_count,
            item.selected_links.spacing_mm,
        ),
    )
    for start_index, end_index in link_groups:
        arrangement = stations[start_index].selected_links
        start, end = _zone_bounds(stations, start_index, end_index, span_m)
        link_zones.append(
            LinkSpacingZone(
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

    return ProjectTGirderEnvelopeDetailingResult(
        envelope=envelope,
        stations=stations,
        longitudinal_zones=tuple(longitudinal_zones),
        link_zones=tuple(link_zones),
        tension_shift_m=tension_shift_m,
        status=(
            "Simple-span positive-bending EC2 envelope detailing: native co-located ULS M/V, "
            "bilateral tension-force shift, one longitudinal bar diameter with curtailed total "
            "bar counts, anchorage-extended cutoff guidance, and one closed-link family with "
            "section-by-section spacing zones. Alternate anchorage geometries and drawing-level "
            "torsion-cage placement remain explicit later detailing tasks."
        ),
    )
