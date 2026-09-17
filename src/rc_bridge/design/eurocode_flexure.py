from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlexureResult:
    resistance_knm: float
    neutral_axis_m: float
    lever_arm_m: float
    steel_force_kn: float
    status: str


def rectangular_singly_reinforced_resistance(
    width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
) -> FlexureResult:
    """Preliminary EC2-style singly reinforced rectangular-section resistance.

    Uses a simplified rectangular concrete compression block and is intended
    for solver development and benchmark verification. Flanged sections,
    ductility limits, redistribution and National Annex choices are handled by
    later dedicated design modules.
    """
    if min(width_m, effective_depth_m, steel_area_mm2, fck_mpa, fyk_mpa) <= 0:
        raise ValueError("Geometry, reinforcement and strengths must be positive.")
    if gamma_c <= 0 or gamma_s <= 0 or alpha_cc <= 0:
        raise ValueError("Material factors must be positive.")

    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    fyd_mpa = fyk_mpa / gamma_s
    steel_force_n = steel_area_mm2 * fyd_mpa

    # Simplified EC2 rectangular block for normal-strength concrete:
    # C = eta * fcd * b * lambda*x, with eta=1.0 and lambda=0.8.
    width_mm = width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    lambda_block = 0.8
    eta = 1.0
    x_mm = steel_force_n / (eta * fcd_mpa * width_mm * lambda_block)
    compression_centroid_mm = 0.5 * lambda_block * x_mm
    z_mm = d_mm - compression_centroid_mm

    if z_mm <= 0:
        raise ValueError("Invalid section: calculated lever arm is non-positive.")

    mrd_nmm = steel_force_n * z_mm
    status = "preliminary; requires clause-by-clause verification"
    return FlexureResult(
        resistance_knm=mrd_nmm / 1e6,
        neutral_axis_m=x_mm / 1000.0,
        lever_arm_m=z_mm / 1000.0,
        steel_force_kn=steel_force_n / 1000.0,
        status=status,
    )
