from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    lm1_characteristic_lane_load,
    lm1_remaining_area_udl_kn_m2,
    lm1_tandem_axle_spacing_m,
    notional_lane_layout,
)
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillagePointLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)


LM1_TRANSVERSE_WHEEL_SPACING_M = 2.0


@dataclass(frozen=True)
class LM1LongitudinalRegion:
    """One longitudinal interval on which a lane or remaining-area UDL is active."""

    x_start_m: float
    x_end_m: float

    def __post_init__(self) -> None:
        if self.x_end_m <= self.x_start_m:
            raise ValueError("LM1 longitudinal region must have positive length.")


@dataclass(frozen=True)
class LM1LaneVerificationPlacement:
    """Explicit transverse/longitudinal placement of one numbered LM1 lane."""

    lane_number: int
    y_start_m: float
    y_end_m: float
    udl_regions: tuple[LM1LongitudinalRegion, ...] = ()
    tandem_lead_x_m: float | None = None

    def __post_init__(self) -> None:
        if self.lane_number < 1:
            raise ValueError("LM1 lane_number must be positive.")
        if self.y_end_m <= self.y_start_m:
            raise ValueError("LM1 lane transverse bounds must have positive width.")

    @property
    def width_m(self) -> float:
        return self.y_end_m - self.y_start_m

    @property
    def centre_y_m(self) -> float:
        return 0.5 * (self.y_start_m + self.y_end_m)


@dataclass(frozen=True)
class LM1RemainingAreaVerificationPlacement:
    """Explicit transverse location of one part of the EN 1991-2 remaining area."""

    y_start_m: float
    y_end_m: float
    udl_regions: tuple[LM1LongitudinalRegion, ...] = ()

    def __post_init__(self) -> None:
        if self.y_end_m <= self.y_start_m:
            raise ValueError("Remaining-area transverse bounds must have positive width.")

    @property
    def width_m(self) -> float:
        return self.y_end_m - self.y_start_m


def _validate_regions(
    regions: tuple[LM1LongitudinalRegion, ...],
    *,
    total_length_m: float,
) -> None:
    for region in regions:
        if region.x_start_m < -1e-9 or region.x_end_m > total_length_m + 1e-9:
            raise ValueError("LM1 UDL region lies outside the bridge length.")


def _validate_transverse_coverage(
    project: ProjectInput,
    lane_placements: tuple[LM1LaneVerificationPlacement, ...],
    remaining_placements: tuple[LM1RemainingAreaVerificationPlacement, ...],
) -> None:
    layout = notional_lane_layout(float(project.geometry.carriageway_width_m))
    expected_lane_numbers = set(range(1, layout.lane_count + 1))
    supplied_lane_numbers = {placement.lane_number for placement in lane_placements}
    if len(supplied_lane_numbers) != len(lane_placements):
        raise ValueError("Each LM1 lane number may be placed only once in one verification snapshot.")
    if supplied_lane_numbers != expected_lane_numbers:
        raise ValueError(
            "LM1 verification snapshot must place every notional lane exactly once: "
            f"expected {sorted(expected_lane_numbers)}, got {sorted(supplied_lane_numbers)}."
        )

    for placement in lane_placements:
        if abs(placement.width_m - layout.lane_width_m) > 1e-9:
            raise ValueError(
                f"LM1 lane {placement.lane_number} width must be {layout.lane_width_m:.6g} m."
            )

    remaining_width = sum(placement.width_m for placement in remaining_placements)
    if abs(remaining_width - layout.remaining_width_m) > 1e-9:
        raise ValueError(
            "Explicit remaining-area strips must reproduce the EN 1991-2 remaining width."
        )

    strips = [
        (placement.y_start_m, placement.y_end_m)
        for placement in (*lane_placements, *remaining_placements)
    ]
    strips.sort(key=lambda item: item[0])
    left_edge = float(project.geometry.carriageway_left_edge_m)
    right_edge = float(project.geometry.carriageway_right_edge_m)
    if not strips:
        raise ValueError("LM1 transverse snapshot contains no loaded carriageway strips.")
    if abs(strips[0][0] - left_edge) > 1e-9 or abs(strips[-1][1] - right_edge) > 1e-9:
        raise ValueError("LM1 lane and remaining-area strips must span the complete carriageway width.")
    for previous, current in zip(strips, strips[1:]):
        if abs(previous[1] - current[0]) > 1e-9:
            raise ValueError("LM1 transverse strips must be contiguous without gaps or overlaps.")


def build_lm1_grillage_load_case(
    project: ProjectInput,
    *,
    lane_placements: tuple[LM1LaneVerificationPlacement, ...],
    remaining_area_placements: tuple[LM1RemainingAreaVerificationPlacement, ...] = (),
    factors: LM1AdjustmentFactors | None = None,
    name: str = "EN 1991-2 LM1 verification snapshot",
) -> GrillageVerificationLoadCase:
    """Create an explicit LM1 static snapshot for a beam-grillage verification model.

    The transverse position and lane numbering are supplied explicitly so the
    exporter does not assume which physical strip is the unfavourable lane 1.
    Each tandem axle is split into two equal wheel loads spaced 2.0 m
    transversely. UDL regions are supplied independently for every strip so
    continuous-span adverse loading can be reproduced without a full-span
    shortcut.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("LM1 grillage verification requires a Eurocode project.")

    _validate_transverse_coverage(project, lane_placements, remaining_area_placements)
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    adjustment = factors or LM1AdjustmentFactors()

    point_loads: list[GrillagePointLoad] = []
    area_loads: list[GrillageAreaLoad] = []
    axle_spacing = lm1_tandem_axle_spacing_m()

    for placement in lane_placements:
        _validate_regions(placement.udl_regions, total_length_m=total_length)
        lane = lm1_characteristic_lane_load(placement.lane_number, adjustment)
        for region in placement.udl_regions:
            area_loads.append(
                GrillageAreaLoad(
                    x_start_m=region.x_start_m,
                    x_end_m=region.x_end_m,
                    y_start_m=placement.y_start_m,
                    y_end_m=placement.y_end_m,
                    pressure_kn_m2=lane.udl_kn_m2,
                    label=f"LM1 lane {placement.lane_number} UDL",
                )
            )

        if placement.tandem_lead_x_m is None or lane.axle_load_kn <= 0.0:
            continue
        wheel_y = (
            placement.centre_y_m - LM1_TRANSVERSE_WHEEL_SPACING_M / 2.0,
            placement.centre_y_m + LM1_TRANSVERSE_WHEEL_SPACING_M / 2.0,
        )
        if wheel_y[0] < placement.y_start_m - 1e-9 or wheel_y[1] > placement.y_end_m + 1e-9:
            raise ValueError("LM1 tandem wheel centres do not fit inside the supplied lane strip.")
        wheel_load = lane.axle_load_kn / 2.0
        active_axles = 0
        for axle_index, axle_x in enumerate(
            (placement.tandem_lead_x_m, placement.tandem_lead_x_m + axle_spacing),
            start=1,
        ):
            if axle_x < -1e-9 or axle_x > total_length + 1e-9:
                continue
            active_axles += 1
            for wheel_index, y_m in enumerate(wheel_y, start=1):
                point_loads.append(
                    GrillagePointLoad(
                        x_m=axle_x,
                        y_m=y_m,
                        magnitude_kn=wheel_load,
                        label=(
                            f"LM1 lane {placement.lane_number} axle {axle_index} "
                            f"wheel {wheel_index}"
                        ),
                    )
                )
        if active_axles == 0:
            raise ValueError("LM1 tandem placement leaves both axles outside the bridge.")

    remaining_pressure = lm1_remaining_area_udl_kn_m2(adjustment)
    for index, placement in enumerate(remaining_area_placements, start=1):
        _validate_regions(placement.udl_regions, total_length_m=total_length)
        for region in placement.udl_regions:
            area_loads.append(
                GrillageAreaLoad(
                    x_start_m=region.x_start_m,
                    x_end_m=region.x_end_m,
                    y_start_m=placement.y_start_m,
                    y_end_m=placement.y_end_m,
                    pressure_kn_m2=remaining_pressure,
                    label=f"LM1 remaining area {index} UDL",
                )
            )

    return GrillageVerificationLoadCase(
        name=name,
        point_loads=tuple(point_loads),
        area_loads=tuple(area_loads),
    )


def build_project_lm1_grillage_verification_model(
    project: ProjectInput,
    *,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...],
    transverse_section: GrillageSectionProperties,
    transverse_stations_m: tuple[float, ...],
    lane_placements: tuple[LM1LaneVerificationPlacement, ...],
    remaining_area_placements: tuple[LM1RemainingAreaVerificationPlacement, ...] = (),
    factors: LM1AdjustmentFactors | None = None,
    name: str = "EN 1991-2 LM1 verification snapshot",
) -> VerificationModel:
    load_case = build_lm1_grillage_load_case(
        project,
        lane_placements=lane_placements,
        remaining_area_placements=remaining_area_placements,
        factors=factors,
        name=name,
    )
    model = build_project_grillage_verification_model(
        project,
        longitudinal_sections_by_span=longitudinal_sections_by_span,
        transverse_section=transverse_section,
        transverse_stations_m=transverse_stations_m,
        load_case=load_case,
    )
    metadata = dict(model.metadata)
    metadata.update(
        {
            "traffic_model": "EN 1991-2 LM1 first-generation implementation",
            "lane_placement": "explicit transverse strips; lane numbering supplied by caller",
            "tandem_geometry": "two axles at 1.2 m; each axle split into two wheels 2.0 m apart",
            "udl_placement": "explicit longitudinal regions per lane/remaining-area strip",
            "local_wheel_contact": "wheel-centre point loads; local deck contact patch not represented",
        }
    )
    return VerificationModel(
        name=model.name,
        nodes=model.nodes,
        materials=model.materials,
        sections=model.sections,
        beams=model.beams,
        supports=model.supports,
        load_cases=model.load_cases,
        metadata=metadata,
    )
