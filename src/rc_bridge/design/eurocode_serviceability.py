from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UncrackedTSectionSLS:
    transformed_area_mm2: float
    neutral_axis_from_top_mm: float
    second_moment_mm4: float
    cracking_moment_knm: float


def uncracked_t_section_sls(
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    modular_ratio: float,
    fct_eff_mpa: float,
) -> UncrackedTSectionSLS:
    """Transformed uncracked T-section properties for EC2 serviceability.

    Concrete in tension is retained because this represents the uncracked
    state. Compression reinforcement is not yet included in this first kernel.
    """
    values = (
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        total_depth_m,
        steel_area_mm2,
        steel_depth_m,
        modular_ratio,
        fct_eff_mpa,
    )
    if any(value <= 0 for value in values):
        raise ValueError("Geometry, material and transformed-section inputs must be positive.")
    if flange_thickness_m >= total_depth_m:
        raise ValueError("Flange thickness must be less than total depth.")
    if steel_depth_m >= total_depth_m:
        raise ValueError("Steel depth must lie within the section.")
    if web_width_m > effective_flange_width_m:
        raise ValueError("Web width cannot exceed effective flange width.")

    beff = effective_flange_width_m * 1000.0
    hf = flange_thickness_m * 1000.0
    bw = web_width_m * 1000.0
    h = total_depth_m * 1000.0
    d = steel_depth_m * 1000.0
    ne_as = modular_ratio * steel_area_mm2

    concrete_area = bw * h + (beff - bw) * hf
    transformed_area = concrete_area + ne_as

    first_moment_top = (
        bw * h**2 / 2.0
        + (beff - bw) * hf**2 / 2.0
        + ne_as * d
    )
    x = first_moment_top / transformed_area

    second_moment_top = (
        bw * h**3 / 3.0
        + (beff - bw) * hf**3 / 3.0
        + ne_as * d**2
    )
    inertia = second_moment_top - transformed_area * x**2
    if inertia <= 0:
        raise ValueError("Calculated transformed second moment is non-positive.")

    tensile_fibre_distance = h - x
    mcr_nmm = fct_eff_mpa * inertia / tensile_fibre_distance

    return UncrackedTSectionSLS(
        transformed_area_mm2=transformed_area,
        neutral_axis_from_top_mm=x,
        second_moment_mm4=inertia,
        cracking_moment_knm=mcr_nmm / 1e6,
    )


def ec2_tension_stiffening_zeta(
    service_moment_knm: float,
    cracking_moment_knm: float,
    beta: float = 0.5,
) -> float:
    """EC2 7.4.3 interpolation coefficient using Mcr/M for flexure."""
    if service_moment_knm < 0 or cracking_moment_knm <= 0:
        raise ValueError("Moments must be non-negative and cracking moment positive.")
    if not 0.0 <= beta <= 1.0:
        raise ValueError("beta must lie between 0 and 1.")
    if service_moment_knm <= cracking_moment_knm:
        return 0.0

    zeta = 1.0 - beta * (cracking_moment_knm / service_moment_knm) ** 2
    return min(max(zeta, 0.0), 1.0)


def interpolate_service_deformation(
    uncracked_value: float,
    fully_cracked_value: float,
    zeta: float,
) -> float:
    """Interpolate a deformation parameter between EC2 states I and II."""
    if not 0.0 <= zeta <= 1.0:
        raise ValueError("zeta must lie between 0 and 1.")
    return zeta * fully_cracked_value + (1.0 - zeta) * uncracked_value
