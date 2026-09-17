from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


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
