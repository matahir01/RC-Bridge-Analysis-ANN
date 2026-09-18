from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from rc_bridge.design.eurocode_detailing import bar_area_mm2


@dataclass(frozen=True)
class TorsionCageLinkArrangement:
    link_diameter_mm: float
    leg_count: int
    spacing_mm: float
    provided_shear_asw_per_s_mm2_per_m: float
    provided_torsion_leg_asw_per_s_mm2_per_m: float
    satisfies_shear: bool
    satisfies_torsion: bool
    maximum_torsion_link_spacing_mm: float
    satisfies_longitudinal_spacing: bool
    satisfies_torsion_link_spacing: bool
    satisfies_transverse_leg_spacing: bool
    status: str


@dataclass(frozen=True)
class TorsionLongitudinalArrangement:
    bar_diameter_mm: float
    bar_count: int
    corner_bar_count: int
    additional_perimeter_bar_count: int
    provided_area_mm2: float
    required_area_mm2: float
    nominal_perimeter_spacing_mm: float
    maximum_perimeter_spacing_mm: float
    satisfies_perimeter_spacing: bool
    status: str


@dataclass(frozen=True)
class TorsionCageDetailingResult:
    required_shear_asw_per_s_mm2_per_m: float
    required_torsion_leg_asw_per_s_mm2_per_m: float
    required_torsion_longitudinal_area_mm2: float
    links: TorsionCageLinkArrangement
    longitudinal: TorsionLongitudinalArrangement | None
    torsion_cell_perimeter_m: float
    maximum_torsion_link_spacing_mm: float
    maximum_longitudinal_torsion_bar_spacing_mm: float
    status: str


def select_torsion_cage_detailing(
    *,
    required_shear_asw_per_s_mm2_per_m: float,
    required_torsion_leg_asw_per_s_mm2_per_m: float,
    required_torsion_longitudinal_area_mm2: float,
    torsion_cell_perimeter_m: float,
    web_width_mm: float,
    cover_mm: float,
    maximum_longitudinal_spacing_mm: float,
    maximum_transverse_leg_spacing_mm: float,
    maximum_torsion_link_spacing_mm: float,
    maximum_longitudinal_torsion_bar_spacing_mm: float = 350.0,
    available_link_diameters_mm: tuple[float, ...] = (8.0, 10.0, 12.0, 16.0),
    available_link_legs: tuple[int, ...] = (2, 4, 6),
    available_link_spacings_mm: tuple[float, ...] = (
        300.0,
        250.0,
        225.0,
        200.0,
        175.0,
        150.0,
        125.0,
        100.0,
    ),
    available_longitudinal_diameters_mm: tuple[float, ...] = (
        12.0,
        16.0,
        20.0,
        25.0,
        32.0,
    ),
    minimum_corner_bar_count: int = 4,
) -> TorsionCageDetailingResult:
    """Select a closed-link/perimeter-bar torsion cage from explicit demands.

    The torsion transverse demand is treated as the required area of one leg of
    the closed torsion link per spacing, while shear uses the sum of effective
    vertical legs. This avoids silently adding quantities with different link
    semantics. Longitudinal torsion steel is distributed around the verified
    torsion-cell perimeter with at least one bar at each of four corners and an
    explicit maximum perimeter spacing. Torsion-link spacing is checked against
    a separate explicit torsion limit rather than reusing shear spacing alone.
    """
    if min(
        torsion_cell_perimeter_m,
        web_width_mm,
        cover_mm,
        maximum_longitudinal_spacing_mm,
        maximum_transverse_leg_spacing_mm,
        maximum_torsion_link_spacing_mm,
        maximum_longitudinal_torsion_bar_spacing_mm,
    ) <= 0.0:
        raise ValueError("Torsion-cage geometry and spacing limits must be positive.")
    if min(
        required_shear_asw_per_s_mm2_per_m,
        required_torsion_leg_asw_per_s_mm2_per_m,
        required_torsion_longitudinal_area_mm2,
    ) < 0.0:
        raise ValueError("Torsion-cage reinforcement demands cannot be negative.")
    if minimum_corner_bar_count < 4:
        raise ValueError("A closed torsion cage requires at least four corner bars.")

    link_candidates: list[TorsionCageLinkArrangement] = []
    for diameter in sorted(set(available_link_diameters_mm)):
        if diameter <= 0.0:
            raise ValueError("Available link diameters must be positive.")
        area = bar_area_mm2(diameter)
        for legs in sorted(set(available_link_legs)):
            if legs < 2 or legs % 2:
                continue
            transverse_spacing = (
                web_width_mm - 2.0 * (cover_mm + diameter)
            ) / (legs - 1)
            if transverse_spacing > maximum_transverse_leg_spacing_mm + 1.0e-9:
                continue
            for spacing in sorted(set(available_link_spacings_mm), reverse=True):
                if spacing <= 0.0:
                    raise ValueError("Available link spacings must be positive.")
                if spacing > maximum_longitudinal_spacing_mm + 1.0e-9:
                    continue
                if spacing > maximum_torsion_link_spacing_mm + 1.0e-9:
                    continue
                torsion_provided = area / spacing * 1000.0
                shear_provided = legs * area / spacing * 1000.0
                if shear_provided + 1.0e-9 < required_shear_asw_per_s_mm2_per_m:
                    continue
                if (
                    torsion_provided + 1.0e-9
                    < required_torsion_leg_asw_per_s_mm2_per_m
                ):
                    continue
                link_candidates.append(
                    TorsionCageLinkArrangement(
                        link_diameter_mm=diameter,
                        leg_count=legs,
                        spacing_mm=spacing,
                        provided_shear_asw_per_s_mm2_per_m=shear_provided,
                        provided_torsion_leg_asw_per_s_mm2_per_m=torsion_provided,
                        satisfies_shear=True,
                        satisfies_torsion=True,
                        maximum_torsion_link_spacing_mm=maximum_torsion_link_spacing_mm,
                        satisfies_longitudinal_spacing=True,
                        satisfies_torsion_link_spacing=True,
                        satisfies_transverse_leg_spacing=True,
                        status=(
                            "Closed-link family selected with shear checked using all effective "
                            "vertical legs, torsion checked using one closed-link leg area, and "
                            "the explicit torsion-link spacing cap enforced."
                        ),
                    )
                )
    if not link_candidates:
        raise ValueError(
            "No available closed-link family satisfies the simultaneous shear/torsion "
            "reinforcement and spacing demands."
        )
    links = min(
        link_candidates,
        key=lambda item: (
            item.provided_shear_asw_per_s_mm2_per_m,
            item.provided_torsion_leg_asw_per_s_mm2_per_m,
            item.link_diameter_mm,
            item.leg_count,
        ),
    )

    longitudinal: TorsionLongitudinalArrangement | None = None
    if required_torsion_longitudinal_area_mm2 > 0.0:
        candidates: list[TorsionLongitudinalArrangement] = []
        perimeter_mm = torsion_cell_perimeter_m * 1000.0
        for diameter in sorted(set(available_longitudinal_diameters_mm)):
            if diameter <= 0.0:
                raise ValueError("Available torsion longitudinal diameters must be positive.")
            area = bar_area_mm2(diameter)
            count = max(
                minimum_corner_bar_count,
                ceil(required_torsion_longitudinal_area_mm2 / area),
                ceil(perimeter_mm / maximum_longitudinal_torsion_bar_spacing_mm),
            )
            candidates.append(
                TorsionLongitudinalArrangement(
                    bar_diameter_mm=diameter,
                    bar_count=count,
                    corner_bar_count=minimum_corner_bar_count,
                    additional_perimeter_bar_count=count - minimum_corner_bar_count,
                    provided_area_mm2=count * area,
                    required_area_mm2=required_torsion_longitudinal_area_mm2,
                    nominal_perimeter_spacing_mm=perimeter_mm / count,
                    maximum_perimeter_spacing_mm=(
                        maximum_longitudinal_torsion_bar_spacing_mm
                    ),
                    satisfies_perimeter_spacing=(
                        perimeter_mm / count
                        <= maximum_longitudinal_torsion_bar_spacing_mm + 1.0e-9
                    ),
                    status=(
                        "One longitudinal torsion bar is assigned to each cage corner; "
                        "remaining bars are to be distributed around the verified torsion-cell "
                        "perimeter within the specified maximum spacing. Exact coordinates "
                        "require the final section drawing."
                    ),
                )
            )
        longitudinal = min(
            candidates,
            key=lambda item: (
                item.provided_area_mm2,
                item.bar_diameter_mm,
                item.bar_count,
            ),
        )

    return TorsionCageDetailingResult(
        required_shear_asw_per_s_mm2_per_m=required_shear_asw_per_s_mm2_per_m,
        required_torsion_leg_asw_per_s_mm2_per_m=(
            required_torsion_leg_asw_per_s_mm2_per_m
        ),
        required_torsion_longitudinal_area_mm2=(
            required_torsion_longitudinal_area_mm2
        ),
        links=links,
        longitudinal=longitudinal,
        torsion_cell_perimeter_m=torsion_cell_perimeter_m,
        maximum_torsion_link_spacing_mm=maximum_torsion_link_spacing_mm,
        maximum_longitudinal_torsion_bar_spacing_mm=(
            maximum_longitudinal_torsion_bar_spacing_mm
        ),
        status=(
            "Drawing-level torsion cage family selected from the externally benchmark-gated "
            "co-located V-T demand. Corner/perimeter bar coordinates, bends, laps and local "
            "end-block congestion remain drawing-review items."
        ),
    )
