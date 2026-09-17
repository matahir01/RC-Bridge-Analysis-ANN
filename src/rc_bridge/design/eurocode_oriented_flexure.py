from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompressionFace = Literal["top", "bottom"]


@dataclass(frozen=True)
class OrientedFlangedFlexureResult:
    resistance_knm: float
    neutral_axis_from_compression_face_m: float
    compression_block_depth_m: float
    compression_centroid_from_compression_face_m: float
    lever_arm_m: float
    steel_force_kn: float
    compression_zone: str
    compression_face: CompressionFace
    status: str


def oriented_flanged_singly_reinforced_resistance(
    compression_flange_width_m: float,
    compression_flange_thickness_m: float,
    web_width_m: float,
    effective_depth_from_compression_face_m: float,
    steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    *,
    compression_face: CompressionFace,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    lambda_block: float = 0.8,
) -> OrientedFlangedFlexureResult:
    """Return singly reinforced resistance for a flanged compression face.

    The same rectangular stress-block mechanics apply whether compression is at
    the top or bottom of the member. Geometry is therefore supplied relative to
    the actual compression face. For a hogging continuous girder this means the
    deck slab must not be supplied as the compression flange; the lower precast
    girder geometry governs instead.
    """
    values = (
        compression_flange_width_m,
        compression_flange_thickness_m,
        web_width_m,
        effective_depth_from_compression_face_m,
        steel_area_mm2,
        fck_mpa,
        fyk_mpa,
        gamma_c,
        gamma_s,
        alpha_cc,
        lambda_block,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("Geometry, reinforcement, strengths and factors must be positive.")
    if compression_face not in ("top", "bottom"):
        raise ValueError("compression_face must be 'top' or 'bottom'.")
    if web_width_m > compression_flange_width_m:
        raise ValueError("Web width cannot exceed the compression-flange width.")
    if compression_flange_thickness_m >= effective_depth_from_compression_face_m:
        raise ValueError("Compression-flange thickness must be less than effective depth.")

    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    fyd_mpa = fyk_mpa / gamma_s
    steel_force_n = steel_area_mm2 * fyd_mpa

    flange_width_mm = compression_flange_width_m * 1000.0
    flange_thickness_mm = compression_flange_thickness_m * 1000.0
    web_width_mm = web_width_m * 1000.0
    effective_depth_mm = effective_depth_from_compression_face_m * 1000.0

    flange_force_capacity_n = fcd_mpa * flange_width_mm * flange_thickness_mm
    if steel_force_n <= flange_force_capacity_n:
        block_depth_mm = steel_force_n / (fcd_mpa * flange_width_mm)
        centroid_mm = block_depth_mm / 2.0
        compression_zone = "flange_only"
    else:
        web_force_n = steel_force_n - flange_force_capacity_n
        web_block_depth_mm = web_force_n / (fcd_mpa * web_width_mm)
        block_depth_mm = flange_thickness_mm + web_block_depth_mm
        flange_area_mm2 = flange_width_mm * flange_thickness_mm
        web_area_mm2 = web_width_mm * web_block_depth_mm
        centroid_mm = (
            flange_area_mm2 * flange_thickness_mm / 2.0
            + web_area_mm2 * (flange_thickness_mm + web_block_depth_mm / 2.0)
        ) / (flange_area_mm2 + web_area_mm2)
        compression_zone = "flange_and_web"

    neutral_axis_mm = block_depth_mm / lambda_block
    lever_arm_mm = effective_depth_mm - centroid_mm
    if lever_arm_mm <= 0.0:
        raise ValueError("Invalid section: calculated lever arm is non-positive.")

    resistance_nmm = steel_force_n * lever_arm_mm
    return OrientedFlangedFlexureResult(
        resistance_knm=resistance_nmm / 1e6,
        neutral_axis_from_compression_face_m=neutral_axis_mm / 1000.0,
        compression_block_depth_m=block_depth_mm / 1000.0,
        compression_centroid_from_compression_face_m=centroid_mm / 1000.0,
        lever_arm_m=lever_arm_mm / 1000.0,
        steel_force_kn=steel_force_n / 1000.0,
        compression_zone=compression_zone,
        compression_face=compression_face,
        status=(
            "simplified EC2 oriented flanged resistance; geometry is measured from the "
            "actual compression face and ductility/strain limits require separate verification"
        ),
    )
