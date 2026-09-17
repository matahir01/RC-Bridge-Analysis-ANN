from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from rc_bridge.analysis.transformed_sections import (
    CrackedTSectionProperties,
    cracked_t_section_properties,
)


@dataclass(frozen=True)
class BS5400CrackWidthResult:
    crack_width_mm: float
    allowable_crack_width_mm: float
    utilization: float
    g_crack_mm: float
    passes: bool
    acr_mm: float
    mean_strain: float
    status: str


@dataclass(frozen=True)
class BS5400MeanStrainResult:
    epsilon_1: float
    epsilon_s: float
    raw_mean_strain: float
    mean_strain: float
    tension_stiffening_correction: float
    status: str


@dataclass(frozen=True)
class BS5400TSectionCrackResult:
    section: CrackedTSectionProperties
    strain: BS5400MeanStrainResult
    crack: BS5400CrackWidthResult
    modular_ratio: float
    service_moment_knm: float
    permanent_moment_knm: float
    live_moment_knm: float
    status: str


def controlling_surface_distance_mm(
    *,
    bar_spacing_mm: float,
    nominal_cover_to_bar_surface_mm: float,
    bar_diameter_mm: float,
) -> float:
    """Return surface-to-nearest-bar distance a_cr at the mid-spacing point.

    The geometry follows the usual BS 5400 crack-width construction: distance
    from the surface point midway between adjacent bars to the nearest bar
    surface. This is a geometric helper only; callers may supply a_cr directly
    when a different surface point controls.
    """
    if min(bar_spacing_mm, nominal_cover_to_bar_surface_mm, bar_diameter_mm) <= 0.0:
        raise ValueError("Bar spacing, cover and diameter must be positive.")

    centre_cover_mm = nominal_cover_to_bar_surface_mm + bar_diameter_mm / 2.0
    centre_distance_mm = sqrt((bar_spacing_mm / 2.0) ** 2 + centre_cover_mm**2)
    return centre_distance_mm - bar_diameter_mm / 2.0


def mean_strain_bs5400(
    *,
    epsilon_1: float,
    epsilon_s: float,
    tension_zone_width_mm: float,
    overall_depth_mm: float,
    crack_point_depth_mm: float,
    compression_depth_mm: float,
    steel_area_mm2: float,
    permanent_moment_knm: float,
    live_moment_knm: float,
) -> BS5400MeanStrainResult:
    """Evaluate BS 5400 Part 4 Equation 25 mean strain.

    Equation 25 applies a concrete tension-stiffening correction to the elastic
    strain at the surface point being checked. The resulting mean strain must
    not exceed epsilon_1. A negative mean strain indicates an uncracked section.

    The equation contains Mq/Mg. When Mg is zero the ratio is undefined; this
    helper conservatively uses epsilon_1 with no tension-stiffening reduction
    rather than inventing a numerical substitute.
    """
    if epsilon_1 < 0.0:
        raise ValueError("epsilon_1 cannot be negative.")
    if epsilon_s < 0.0:
        raise ValueError("epsilon_s cannot be negative.")
    if min(tension_zone_width_mm, overall_depth_mm, steel_area_mm2) <= 0.0:
        raise ValueError("Tension-zone width, overall depth and steel area must be positive.")
    if not 0.0 <= compression_depth_mm < overall_depth_mm:
        raise ValueError("compression_depth_mm must lie within the section.")
    if not compression_depth_mm <= crack_point_depth_mm <= overall_depth_mm:
        raise ValueError("crack_point_depth_mm must lie between the neutral axis and tension face.")
    if permanent_moment_knm < 0.0 or live_moment_knm < 0.0:
        raise ValueError("Service moments cannot be negative.")

    if epsilon_s == 0.0 or epsilon_1 == 0.0:
        return BS5400MeanStrainResult(
            epsilon_1=epsilon_1,
            epsilon_s=epsilon_s,
            raw_mean_strain=0.0,
            mean_strain=0.0,
            tension_stiffening_correction=0.0,
            status="zero tensile strain: section is uncracked under the supplied service effects",
        )

    if permanent_moment_knm == 0.0:
        return BS5400MeanStrainResult(
            epsilon_1=epsilon_1,
            epsilon_s=epsilon_s,
            raw_mean_strain=epsilon_1,
            mean_strain=epsilon_1,
            tension_stiffening_correction=0.0,
            status=(
                "BS 5400 Equation 25 Mq/Mg term is undefined for Mg=0; "
                "epsilon_1 is retained conservatively without tension-stiffening reduction"
            ),
        )

    geometry_term = (
        3.8
        * tension_zone_width_mm
        * overall_depth_mm
        * (crack_point_depth_mm - compression_depth_mm)
        / (
            epsilon_s
            * steel_area_mm2
            * (overall_depth_mm - compression_depth_mm)
        )
    )
    load_term = (1.0 - live_moment_knm / permanent_moment_knm) * 1e-9
    correction = geometry_term * load_term
    raw_mean_strain = epsilon_1 - correction
    mean_strain = min(raw_mean_strain, epsilon_1)

    return BS5400MeanStrainResult(
        epsilon_1=epsilon_1,
        epsilon_s=epsilon_s,
        raw_mean_strain=raw_mean_strain,
        mean_strain=mean_strain,
        tension_stiffening_correction=correction,
        status="BS 5400 Part 4 Equation 25 mean strain with epsilon_m capped at epsilon_1",
    )


def surface_crack_width_bs5400(
    *,
    acr_mm: float,
    mean_strain: float,
    nominal_cover_mm: float,
    overall_depth_mm: float,
    compression_depth_mm: float,
    allowable_crack_width_mm: float,
) -> BS5400CrackWidthResult:
    """Evaluate the BS 5400 Part 4 surface flexural crack-width equation.

    For a non-zero compression zone:
        w = 3 a_cr epsilon_m /
            [1 + 2(a_cr - c_nom)/(h - d_c)]

    When d_c is zero, the alternative expression w = 3 a_cr epsilon_m is used.
    A non-positive mean strain denotes an uncracked section and returns zero
    crack width.
    """
    if acr_mm <= 0.0:
        raise ValueError("acr_mm must be positive.")
    if nominal_cover_mm < 0.0:
        raise ValueError("nominal_cover_mm cannot be negative.")
    if overall_depth_mm <= 0.0:
        raise ValueError("overall_depth_mm must be positive.")
    if compression_depth_mm < 0.0 or compression_depth_mm >= overall_depth_mm:
        raise ValueError(
            "compression_depth_mm must be non-negative and smaller than overall_depth_mm."
        )
    if allowable_crack_width_mm <= 0.0:
        raise ValueError("allowable_crack_width_mm must be positive.")

    if mean_strain <= 0.0:
        return BS5400CrackWidthResult(
            crack_width_mm=0.0,
            allowable_crack_width_mm=allowable_crack_width_mm,
            utilization=0.0,
            g_crack_mm=allowable_crack_width_mm,
            passes=True,
            acr_mm=acr_mm,
            mean_strain=mean_strain,
            status="BS 5400 mean strain is non-positive: section treated as uncracked",
        )

    if compression_depth_mm == 0.0:
        denominator = 1.0
        equation = "BS 5400 alternative surface crack equation for zero compression depth"
    else:
        denominator = 1.0 + 2.0 * (acr_mm - nominal_cover_mm) / (
            overall_depth_mm - compression_depth_mm
        )
        if denominator <= 0.0:
            raise ValueError("Crack-width geometry produces a non-positive denominator.")
        equation = "BS 5400 surface flexural crack-width equation"

    crack_width_mm = 3.0 * acr_mm * mean_strain / denominator
    utilization = crack_width_mm / allowable_crack_width_mm
    margin = allowable_crack_width_mm - crack_width_mm
    return BS5400CrackWidthResult(
        crack_width_mm=crack_width_mm,
        allowable_crack_width_mm=allowable_crack_width_mm,
        utilization=utilization,
        g_crack_mm=margin,
        passes=margin >= 0.0,
        acr_mm=acr_mm,
        mean_strain=mean_strain,
        status=equation,
    )


def crack_width_t_section_bs5400(
    *,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    permanent_moment_knm: float,
    live_moment_knm: float,
    es_mpa: float,
    ec_modified_mpa: float,
    crack_point_depth_mm: float,
    acr_mm: float,
    nominal_cover_mm: float,
    allowable_crack_width_mm: float,
    tension_zone_width_m: float | None = None,
) -> BS5400TSectionCrackResult:
    """Run cracked elastic T-section analysis and BS 5400 crack-width checks.

    ``ec_modified_mpa`` is intentionally explicit because BS 5400 service
    analysis distinguishes short- and long-term concrete stiffness. The caller
    must supply the project-appropriate modified modulus rather than the solver
    silently choosing a creep assumption.
    """
    if permanent_moment_knm < 0.0 or live_moment_knm < 0.0:
        raise ValueError("Service moments cannot be negative.")
    if es_mpa <= 0.0 or ec_modified_mpa <= 0.0:
        raise ValueError("Steel and modified concrete moduli must be positive.")

    service_moment_knm = permanent_moment_knm + live_moment_knm
    modular_ratio = es_mpa / ec_modified_mpa
    section = cracked_t_section_properties(
        effective_flange_width_m=effective_flange_width_m,
        flange_thickness_m=flange_thickness_m,
        web_width_m=web_width_m,
        total_depth_m=total_depth_m,
        steel_area_mm2=steel_area_mm2,
        steel_depth_m=steel_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment_knm,
    )

    x_mm = section.neutral_axis_from_top_mm
    d_mm = steel_depth_m * 1000.0
    h_mm = total_depth_m * 1000.0
    if not x_mm <= crack_point_depth_mm <= h_mm:
        raise ValueError("crack_point_depth_mm must lie in the tensile zone.")

    epsilon_s = section.steel_stress_mpa / es_mpa
    epsilon_1 = 0.0
    if epsilon_s > 0.0:
        epsilon_1 = epsilon_s * (crack_point_depth_mm - x_mm) / (d_mm - x_mm)

    bt_m = web_width_m if tension_zone_width_m is None else tension_zone_width_m
    if bt_m <= 0.0:
        raise ValueError("tension_zone_width_m must be positive.")

    strain = mean_strain_bs5400(
        epsilon_1=epsilon_1,
        epsilon_s=epsilon_s,
        tension_zone_width_mm=bt_m * 1000.0,
        overall_depth_mm=h_mm,
        crack_point_depth_mm=crack_point_depth_mm,
        compression_depth_mm=x_mm,
        steel_area_mm2=steel_area_mm2,
        permanent_moment_knm=permanent_moment_knm,
        live_moment_knm=live_moment_knm,
    )
    crack = surface_crack_width_bs5400(
        acr_mm=acr_mm,
        mean_strain=strain.mean_strain,
        nominal_cover_mm=nominal_cover_mm,
        overall_depth_mm=h_mm,
        compression_depth_mm=x_mm,
        allowable_crack_width_mm=allowable_crack_width_mm,
    )

    return BS5400TSectionCrackResult(
        section=section,
        strain=strain,
        crack=crack,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment_knm,
        permanent_moment_knm=permanent_moment_knm,
        live_moment_knm=live_moment_knm,
        status=(
            "BS 5400 cracked-elastic T-section serviceability path; modified concrete "
            "modulus and crack-point geometry are explicit project inputs"
        ),
    )
