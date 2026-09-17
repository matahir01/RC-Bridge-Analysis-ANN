from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance


@dataclass(frozen=True)
class NegativeBendingFlexureResult:
    design_moment_knm: float
    design_moment_magnitude_knm: float
    required_top_steel_area_mm2: float
    provided_top_steel_area_mm2: float
    resistance_magnitude_knm: float
    signed_resistance_knm: float
    utilization: float
    g_hogging_knm: float
    compression_width_m: float
    effective_depth_m: float
    passes: bool
    status: str


def check_negative_bending_rectangular_support(
    *,
    design_moment_knm: float,
    compression_width_m: float,
    effective_depth_m: float,
    provided_top_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
) -> NegativeBendingFlexureResult:
    """Check a continuous-girder support region under negative bending.

    The supplied moment must use the project sign convention (negative = hogging).
    The section is intentionally treated as rectangular in compression. For a
    conventional deck-on-girder T-section the deck is on the tension face at an
    internal support, so its positive-bending compression flange is not credited.
    ``compression_width_m`` must therefore describe the verified compression zone
    on the opposite face (typically the girder web/stem unless a bottom flange is
    explicitly modelled and justified).
    """
    if design_moment_knm > 0.0:
        raise ValueError("Negative-bending support check requires a non-positive moment.")
    if min(
        compression_width_m,
        effective_depth_m,
        provided_top_steel_area_mm2,
        fck_mpa,
        fyk_mpa,
    ) <= 0.0:
        raise ValueError("Geometry, reinforcement and strengths must be positive.")

    demand = abs(design_moment_knm)
    required = required_tension_steel_rectangular(
        demand,
        compression_width_m,
        effective_depth_m,
        fck_mpa,
        fyk_mpa,
    )
    resistance = rectangular_singly_reinforced_resistance(
        compression_width_m,
        effective_depth_m,
        provided_top_steel_area_mm2,
        fck_mpa,
        fyk_mpa,
    )
    resistance_magnitude = resistance.resistance_knm
    utilization = demand / resistance_magnitude if resistance_magnitude > 0.0 else float("inf")
    margin = resistance_magnitude - demand

    return NegativeBendingFlexureResult(
        design_moment_knm=design_moment_knm,
        design_moment_magnitude_knm=demand,
        required_top_steel_area_mm2=required,
        provided_top_steel_area_mm2=provided_top_steel_area_mm2,
        resistance_magnitude_knm=resistance_magnitude,
        signed_resistance_knm=-resistance_magnitude,
        utilization=utilization,
        g_hogging_knm=margin,
        compression_width_m=compression_width_m,
        effective_depth_m=effective_depth_m,
        passes=margin >= 0.0,
        status=(
            "EC2 simplified rectangular negative-bending support check; deck tension flange "
            "is excluded from compression resistance and ductility/detailing checks remain explicit"
        ),
    )
