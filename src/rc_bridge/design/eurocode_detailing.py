from __future__ import annotations

from dataclasses import dataclass
from math import ceil, pi, sqrt


@dataclass(frozen=True)
class LongitudinalDetailingResult:
    minimum_tension_steel_mm2: float
    maximum_longitudinal_steel_mm2: float
    provided_steel_mm2: float
    satisfies_minimum: bool
    satisfies_maximum: bool
    governing_minimum_ratio: float
    status: str


@dataclass(frozen=True)
class ShearDetailingResult:
    minimum_rho_w: float
    minimum_asw_per_s_mm2_per_mm: float
    minimum_asw_per_s_mm2_per_m: float
    design_required_asw_per_s_mm2_per_m: float
    governing_required_asw_per_s_mm2_per_m: float
    maximum_longitudinal_link_spacing_mm: float
    maximum_transverse_leg_spacing_mm: float
    status: str


@dataclass(frozen=True)
class BeamDetailingResult:
    longitudinal: LongitudinalDetailingResult
    shear: ShearDetailingResult


@dataclass(frozen=True)
class LongitudinalBarArrangement:
    bar_diameter_mm: float
    bar_count: int
    layer_count: int
    bars_per_layer: tuple[int, ...]
    provided_area_mm2: float
    clear_horizontal_spacing_mm: float
    clear_vertical_spacing_mm: float
    fits_web: bool
    status: str


@dataclass(frozen=True)
class LinkArrangement:
    link_diameter_mm: float
    leg_count: int
    spacing_mm: float
    provided_asw_per_s_mm2_per_m: float
    satisfies_required_area: bool
    satisfies_longitudinal_spacing: bool
    satisfies_transverse_leg_spacing: bool
    status: str


@dataclass(frozen=True)
class AnchorageLapResult:
    fbd_mpa: float
    required_anchorage_length_mm: float
    minimum_anchorage_length_mm: float
    design_anchorage_length_mm: float
    design_lap_length_mm: float
    status: str


@dataclass(frozen=True)
class CoverDurabilityResult:
    bond_minimum_cover_mm: float
    durability_minimum_cover_mm: float
    allowance_for_deviation_mm: float
    nominal_cover_mm: float
    provided_cover_mm: float
    satisfies_nominal_cover: bool
    status: str


def bar_area_mm2(diameter_mm: float) -> float:
    if diameter_mm <= 0.0:
        raise ValueError("Bar diameter must be positive.")
    return pi * diameter_mm**2 / 4.0


def select_longitudinal_bar_arrangement(
    *,
    required_area_mm2: float,
    web_width_mm: float,
    cover_mm: float,
    link_diameter_mm: float,
    available_diameters_mm: tuple[float, ...] = (16.0, 20.0, 25.0, 32.0, 40.0),
    maximum_layers: int = 3,
    aggregate_size_mm: float = 20.0,
    preferred_vertical_clear_spacing_mm: float = 25.0,
) -> LongitudinalBarArrangement:
    """Select the least-area practical longitudinal bar arrangement that fits.

    Clear spacing follows the EC2 constructability minimum represented here as
    max(bar diameter, 20 mm, aggregate size + 5 mm). Bundled bars and couplers
    are outside this selector and require an explicit project detail.
    """
    if min(required_area_mm2, web_width_mm, cover_mm, link_diameter_mm) <= 0.0:
        raise ValueError("Bar-selection demand and geometry must be positive.")
    if maximum_layers < 1:
        raise ValueError("maximum_layers must be at least one.")
    if not available_diameters_mm or any(value <= 0.0 for value in available_diameters_mm):
        raise ValueError("Available bar diameters must be positive.")

    candidates: list[LongitudinalBarArrangement] = []
    clear_width = web_width_mm - 2.0 * (cover_mm + link_diameter_mm)
    for diameter in sorted(set(available_diameters_mm)):
        area = bar_area_mm2(diameter)
        count = max(2, ceil(required_area_mm2 / area))
        minimum_clear = max(20.0, diameter, aggregate_size_mm + 5.0)
        maximum_per_layer = int((clear_width + minimum_clear) // (diameter + minimum_clear))
        if maximum_per_layer < 2:
            continue
        layers = ceil(count / maximum_per_layer)
        if layers > maximum_layers:
            continue
        distribution = [count // layers] * layers
        for index in range(count % layers):
            distribution[index] += 1
        if min(distribution) < 2:
            continue
        governing_count = max(distribution)
        horizontal_clear = (
            (clear_width - governing_count * diameter) / (governing_count - 1)
            if governing_count > 1
            else clear_width - diameter
        )
        vertical_clear = max(preferred_vertical_clear_spacing_mm, minimum_clear)
        fits = horizontal_clear + 1.0e-9 >= minimum_clear
        if not fits:
            continue
        candidates.append(
            LongitudinalBarArrangement(
                bar_diameter_mm=diameter,
                bar_count=count,
                layer_count=layers,
                bars_per_layer=tuple(distribution),
                provided_area_mm2=count * area,
                clear_horizontal_spacing_mm=horizontal_clear,
                clear_vertical_spacing_mm=vertical_clear,
                fits_web=True,
                status=(
                    "Selected from discrete bars without bundling; verify flange/web transitions, "
                    "vibrator access and local cover on drawings"
                ),
            )
        )
    if not candidates:
        raise ValueError(
            "No unbundled longitudinal bar arrangement fits the web, cover and layer limits."
        )
    return min(
        candidates,
        key=lambda item: (item.provided_area_mm2, item.layer_count, item.bar_count),
    )


def select_vertical_link_arrangement(
    *,
    required_asw_per_s_mm2_per_m: float,
    web_width_mm: float,
    maximum_longitudinal_spacing_mm: float,
    maximum_transverse_leg_spacing_mm: float,
    cover_mm: float,
    available_diameters_mm: tuple[float, ...] = (8.0, 10.0, 12.0, 16.0),
    available_legs: tuple[int, ...] = (2, 4, 6),
    available_spacings_mm: tuple[float, ...] = (300.0, 250.0, 225.0, 200.0, 175.0, 150.0, 125.0, 100.0),
) -> LinkArrangement:
    """Select a discrete closed-link diameter, leg count and spacing."""
    if min(
        required_asw_per_s_mm2_per_m,
        web_width_mm,
        maximum_longitudinal_spacing_mm,
        maximum_transverse_leg_spacing_mm,
        cover_mm,
    ) <= 0.0:
        raise ValueError("Link-selection demand and geometry must be positive.")
    candidates: list[LinkArrangement] = []
    for diameter in sorted(set(available_diameters_mm)):
        for legs in sorted(set(available_legs)):
            if legs < 2 or legs % 2:
                continue
            transverse_spacing = (
                (web_width_mm - 2.0 * (cover_mm + diameter)) / (legs - 1)
            )
            if transverse_spacing > maximum_transverse_leg_spacing_mm + 1.0e-9:
                continue
            asw = legs * bar_area_mm2(diameter)
            for spacing in sorted(set(available_spacings_mm), reverse=True):
                provided = asw / spacing * 1000.0
                if spacing > maximum_longitudinal_spacing_mm + 1.0e-9:
                    continue
                if provided + 1.0e-9 < required_asw_per_s_mm2_per_m:
                    continue
                candidates.append(
                    LinkArrangement(
                        link_diameter_mm=diameter,
                        leg_count=legs,
                        spacing_mm=spacing,
                        provided_asw_per_s_mm2_per_m=provided,
                        satisfies_required_area=True,
                        satisfies_longitudinal_spacing=True,
                        satisfies_transverse_leg_spacing=True,
                        status=(
                            "Discrete closed vertical-link selection; use closer support zones "
                            "where the section-by-section shear demand requires them"
                        ),
                    )
                )
    if not candidates:
        raise ValueError("No available vertical-link arrangement satisfies demand and spacing.")
    return min(
        candidates,
        key=lambda item: (
            item.provided_asw_per_s_mm2_per_m,
            item.link_diameter_mm,
            item.leg_count,
        ),
    )


def anchorage_and_lap_lengths_mm(
    *,
    bar_diameter_mm: float,
    fyk_mpa: float,
    fctd_mpa: float,
    gamma_s: float = 1.15,
    eta1: float = 1.0,
    eta2: float = 1.0,
    anchorage_alpha_product: float = 1.0,
    lap_alpha_product: float = 1.0,
) -> AnchorageLapResult:
    """Return EC2 design anchorage and lap lengths for tension reinforcement."""
    if min(bar_diameter_mm, fyk_mpa, fctd_mpa, gamma_s) <= 0.0:
        raise ValueError("Anchorage inputs must be positive.")
    if min(eta1, eta2, anchorage_alpha_product, lap_alpha_product) <= 0.0:
        raise ValueError("Bond and anchorage coefficients must be positive.")
    fyd = fyk_mpa / gamma_s
    fbd = 2.25 * eta1 * eta2 * fctd_mpa
    lb_rqd = bar_diameter_mm * fyd / (4.0 * fbd)
    minimum_anchorage = max(0.3 * lb_rqd, 10.0 * bar_diameter_mm, 100.0)
    design_anchorage = max(anchorage_alpha_product * lb_rqd, minimum_anchorage)
    minimum_lap = max(
        0.3 * lap_alpha_product * lb_rqd,
        15.0 * bar_diameter_mm,
        200.0,
    )
    design_lap = max(lap_alpha_product * lb_rqd, minimum_lap)
    return AnchorageLapResult(
        fbd_mpa=fbd,
        required_anchorage_length_mm=lb_rqd,
        minimum_anchorage_length_mm=minimum_anchorage,
        design_anchorage_length_mm=design_anchorage,
        design_lap_length_mm=design_lap,
        status=(
            "Straight tension-bar EC2 bond model; revise alpha factors for hooks, welded bars, "
            "confinement, cover, transverse pressure and percentage lapped"
        ),
    )


def nominal_cover_check(
    *,
    bar_diameter_mm: float,
    durability_minimum_cover_mm: float,
    allowance_for_deviation_mm: float,
    provided_cover_mm: float,
) -> CoverDurabilityResult:
    if min(
        bar_diameter_mm,
        durability_minimum_cover_mm,
        provided_cover_mm,
    ) <= 0.0 or allowance_for_deviation_mm < 0.0:
        raise ValueError("Cover inputs are invalid.")
    bond_minimum = bar_diameter_mm
    nominal = max(bond_minimum, durability_minimum_cover_mm) + allowance_for_deviation_mm
    return CoverDurabilityResult(
        bond_minimum_cover_mm=bond_minimum,
        durability_minimum_cover_mm=durability_minimum_cover_mm,
        allowance_for_deviation_mm=allowance_for_deviation_mm,
        nominal_cover_mm=nominal,
        provided_cover_mm=provided_cover_mm,
        satisfies_nominal_cover=provided_cover_mm + 1.0e-9 >= nominal,
        status=(
            "Nominal cover from bond/durability plus deviation; fire, abrasion and project "
            "execution requirements must be checked separately"
        ),
    )


def minimum_tension_reinforcement_mm2(
    *,
    fctm_mpa: float,
    fyk_mpa: float,
    tension_zone_width_m: float,
    effective_depth_m: float,
    coefficient: float = 0.26,
    absolute_minimum_ratio: float = 0.0013,
) -> tuple[float, float]:
    """Return EC2 beam minimum tension reinforcement and governing ratio.

    Implements max(0.26 fctm/fyk * b_t d, 0.0013 b_t d) with configurable
    recommended coefficients.
    """
    if min(fctm_mpa, fyk_mpa, tension_zone_width_m, effective_depth_m) <= 0.0:
        raise ValueError("Material properties and dimensions must be positive.")
    if coefficient <= 0.0 or absolute_minimum_ratio <= 0.0:
        raise ValueError("Minimum reinforcement coefficients must be positive.")

    bt_mm = tension_zone_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    ratio_strength = coefficient * fctm_mpa / fyk_mpa
    governing_ratio = max(ratio_strength, absolute_minimum_ratio)
    return governing_ratio * bt_mm * d_mm, governing_ratio


def maximum_longitudinal_reinforcement_mm2(
    *,
    concrete_area_m2: float,
    maximum_ratio: float = 0.04,
) -> float:
    """Return recommended EC2 maximum longitudinal reinforcement area."""
    if concrete_area_m2 <= 0.0 or maximum_ratio <= 0.0:
        raise ValueError("Concrete area and maximum_ratio must be positive.")
    return maximum_ratio * concrete_area_m2 * 1_000_000.0


def minimum_vertical_shear_reinforcement(
    *,
    fck_mpa: float,
    fyk_mpa: float,
    web_width_m: float,
    coefficient: float = 0.08,
) -> tuple[float, float, float]:
    """Return EC2 minimum vertical shear reinforcement ratio and A_sw/s.

    For vertical links, rho_w,min = 0.08 sqrt(fck) / fyk and
    A_sw/s = rho_w,min * b_w.
    """
    if min(fck_mpa, fyk_mpa, web_width_m) <= 0.0:
        raise ValueError("Material properties and web width must be positive.")
    if coefficient <= 0.0:
        raise ValueError("Shear reinforcement coefficient must be positive.")

    rho_w_min = coefficient * sqrt(fck_mpa) / fyk_mpa
    bw_mm = web_width_m * 1000.0
    asw_per_s_mm2_per_mm = rho_w_min * bw_mm
    return rho_w_min, asw_per_s_mm2_per_mm, asw_per_s_mm2_per_mm * 1000.0


def maximum_vertical_link_spacings_mm(
    *,
    effective_depth_m: float,
    longitudinal_spacing_factor: float = 0.75,
    transverse_spacing_factor: float = 0.75,
    transverse_spacing_cap_mm: float = 600.0,
) -> tuple[float, float]:
    """Return recommended maximum vertical-link spacings for beams."""
    if effective_depth_m <= 0.0:
        raise ValueError("effective_depth_m must be positive.")
    if min(
        longitudinal_spacing_factor,
        transverse_spacing_factor,
        transverse_spacing_cap_mm,
    ) <= 0.0:
        raise ValueError("Link-spacing parameters must be positive.")

    d_mm = effective_depth_m * 1000.0
    longitudinal = longitudinal_spacing_factor * d_mm
    transverse = min(transverse_spacing_factor * d_mm, transverse_spacing_cap_mm)
    return longitudinal, transverse


def beam_detailing_requirements(
    *,
    fctm_mpa: float,
    fck_mpa: float,
    fyk_mpa: float,
    tension_zone_width_m: float,
    web_width_m: float,
    effective_depth_m: float,
    concrete_area_m2: float,
    provided_longitudinal_steel_mm2: float,
    design_required_asw_per_s_mm2_per_m: float = 0.0,
) -> BeamDetailingResult:
    """Assemble current EC2 beam reinforcement/detailing requirements."""
    if provided_longitudinal_steel_mm2 <= 0.0:
        raise ValueError("provided_longitudinal_steel_mm2 must be positive.")
    if design_required_asw_per_s_mm2_per_m < 0.0:
        raise ValueError("design_required_asw_per_s_mm2_per_m cannot be negative.")

    as_min, min_ratio = minimum_tension_reinforcement_mm2(
        fctm_mpa=fctm_mpa,
        fyk_mpa=fyk_mpa,
        tension_zone_width_m=tension_zone_width_m,
        effective_depth_m=effective_depth_m,
    )
    as_max = maximum_longitudinal_reinforcement_mm2(concrete_area_m2=concrete_area_m2)
    rho_w, asw_s_mm, asw_s_m = minimum_vertical_shear_reinforcement(
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        web_width_m=web_width_m,
    )
    s_long, s_trans = maximum_vertical_link_spacings_mm(
        effective_depth_m=effective_depth_m
    )

    return BeamDetailingResult(
        longitudinal=LongitudinalDetailingResult(
            minimum_tension_steel_mm2=as_min,
            maximum_longitudinal_steel_mm2=as_max,
            provided_steel_mm2=provided_longitudinal_steel_mm2,
            satisfies_minimum=provided_longitudinal_steel_mm2 >= as_min,
            satisfies_maximum=provided_longitudinal_steel_mm2 <= as_max,
            governing_minimum_ratio=min_ratio,
            status=(
                "EC2 beam longitudinal reinforcement limits; lap zones, anchorage, "
                "curtailment and National Annex rules remain separate"
            ),
        ),
        shear=ShearDetailingResult(
            minimum_rho_w=rho_w,
            minimum_asw_per_s_mm2_per_mm=asw_s_mm,
            minimum_asw_per_s_mm2_per_m=asw_s_m,
            design_required_asw_per_s_mm2_per_m=design_required_asw_per_s_mm2_per_m,
            governing_required_asw_per_s_mm2_per_m=max(
                asw_s_m, design_required_asw_per_s_mm2_per_m
            ),
            maximum_longitudinal_link_spacing_mm=s_long,
            maximum_transverse_leg_spacing_mm=s_trans,
            status=(
                "EC2 vertical-link minimum reinforcement and spacing limits; selected "
                "bar diameter, number of legs and anchorage still require detailing"
            ),
        ),
    )
