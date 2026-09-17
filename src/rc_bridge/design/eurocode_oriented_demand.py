from __future__ import annotations

from rc_bridge.design.eurocode_demand import FlexuralDemandResult
from rc_bridge.design.eurocode_oriented_flexure import (
    CompressionFace,
    oriented_flanged_singly_reinforced_resistance,
)
from rc_bridge.research.limit_states import flexural_limit_state


def required_tension_steel_oriented_flanged(
    med_knm: float,
    compression_flange_width_m: float,
    compression_flange_thickness_m: float,
    web_width_m: float,
    effective_depth_from_compression_face_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    *,
    compression_face: CompressionFace,
    tolerance_knm: float = 0.01,
) -> float:
    """Solve required tension steel for an explicitly oriented flanged section."""
    if med_knm < 0.0:
        raise ValueError("Design moment magnitude cannot be negative.")
    if med_knm == 0.0:
        return 0.0

    lower = 1.0
    upper = 1000.0
    for _ in range(30):
        resistance = oriented_flanged_singly_reinforced_resistance(
            compression_flange_width_m,
            compression_flange_thickness_m,
            web_width_m,
            effective_depth_from_compression_face_m,
            upper,
            fck_mpa,
            fyk_mpa,
            compression_face=compression_face,
        )
        if resistance.resistance_knm >= med_knm:
            break
        upper *= 2.0
    else:
        raise ValueError(
            "Unable to bracket required steel area; oriented flanged section may be outside model scope."
        )

    for _ in range(80):
        mid = 0.5 * (lower + upper)
        resistance = oriented_flanged_singly_reinforced_resistance(
            compression_flange_width_m,
            compression_flange_thickness_m,
            web_width_m,
            effective_depth_from_compression_face_m,
            mid,
            fck_mpa,
            fyk_mpa,
            compression_face=compression_face,
        )
        if abs(resistance.resistance_knm - med_knm) <= tolerance_knm:
            return mid
        if resistance.resistance_knm < med_knm:
            lower = mid
        else:
            upper = mid
    return upper


def check_flexure_oriented_flanged(
    med_knm: float,
    compression_flange_width_m: float,
    compression_flange_thickness_m: float,
    web_width_m: float,
    effective_depth_from_compression_face_m: float,
    provided_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    *,
    compression_face: CompressionFace,
) -> FlexuralDemandResult:
    """Check provided steel for top- or bottom-compression flanged bending."""
    required = required_tension_steel_oriented_flanged(
        med_knm,
        compression_flange_width_m,
        compression_flange_thickness_m,
        web_width_m,
        effective_depth_from_compression_face_m,
        fck_mpa,
        fyk_mpa,
        compression_face=compression_face,
    )
    resistance = oriented_flanged_singly_reinforced_resistance(
        compression_flange_width_m,
        compression_flange_thickness_m,
        web_width_m,
        effective_depth_from_compression_face_m,
        provided_steel_area_mm2,
        fck_mpa,
        fyk_mpa,
        compression_face=compression_face,
    )
    utilization = (
        med_knm / resistance.resistance_knm
        if resistance.resistance_knm > 0.0
        else float("inf")
    )
    return FlexuralDemandResult(
        required_steel_area_mm2=required,
        provided_steel_area_mm2=provided_steel_area_mm2,
        resistance_knm=resistance.resistance_knm,
        utilization=utilization,
        g_flexure_knm=flexural_limit_state(resistance.resistance_knm, med_knm),
        status=resistance.status,
    )
