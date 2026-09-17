from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlangedFlexureResult:
    resistance_knm: float
    neutral_axis_m: float
    compression_block_depth_m: float
    compression_centroid_from_top_m: float
    lever_arm_m: float
    steel_force_kn: float
    compression_zone: str
    status: str


def t_section_singly_reinforced_resistance(
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    lambda_block: float = 0.8,
) -> FlangedFlexureResult:
    """Simplified EC2-style positive-bending resistance for a flanged RC section.

    The top flange is assumed to be in compression and the tension steel below.
    The rectangular stress block is split between flange and web when its depth
    exceeds the flange thickness. Ductility/strain-limit checks remain a
    separate verification step and are therefore reported in ``status``.
    """
    values = (
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        effective_depth_m,
        steel_area_mm2,
        fck_mpa,
        fyk_mpa,
        gamma_c,
        gamma_s,
        alpha_cc,
        lambda_block,
    )
    if any(value <= 0 for value in values):
        raise ValueError("Geometry, reinforcement, strengths and factors must be positive.")
    if web_width_m > effective_flange_width_m:
        raise ValueError("Web width cannot exceed effective flange width.")
    if flange_thickness_m >= effective_depth_m:
        raise ValueError("Flange thickness must be less than effective depth.")

    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    fyd_mpa = fyk_mpa / gamma_s
    steel_force_n = steel_area_mm2 * fyd_mpa

    beff_mm = effective_flange_width_m * 1000.0
    hf_mm = flange_thickness_m * 1000.0
    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0

    flange_capacity_n = fcd_mpa * beff_mm * hf_mm

    if steel_force_n <= flange_capacity_n:
        a_mm = steel_force_n / (fcd_mpa * beff_mm)
        centroid_mm = a_mm / 2.0
        zone = "flange_only"
    else:
        web_force_n = steel_force_n - flange_capacity_n
        web_block_depth_mm = web_force_n / (fcd_mpa * bw_mm)
        a_mm = hf_mm + web_block_depth_mm
        flange_area = beff_mm * hf_mm
        web_area = bw_mm * web_block_depth_mm
        centroid_mm = (
            flange_area * (hf_mm / 2.0)
            + web_area * (hf_mm + web_block_depth_mm / 2.0)
        ) / (flange_area + web_area)
        zone = "flange_and_web"

    x_mm = a_mm / lambda_block
    z_mm = d_mm - centroid_mm
    if z_mm <= 0:
        raise ValueError("Invalid section: calculated lever arm is non-positive.")

    mrd_nmm = steel_force_n * z_mm
    return FlangedFlexureResult(
        resistance_knm=mrd_nmm / 1e6,
        neutral_axis_m=x_mm / 1000.0,
        compression_block_depth_m=a_mm / 1000.0,
        compression_centroid_from_top_m=centroid_mm / 1000.0,
        lever_arm_m=z_mm / 1000.0,
        steel_force_kn=steel_force_n / 1000.0,
        compression_zone=zone,
        status=(
            "simplified EC2 positive-bending flanged resistance; "
            "ductility, strain limits and detailed bridge clauses require verification"
        ),
    )
