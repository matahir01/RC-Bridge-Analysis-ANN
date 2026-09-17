from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.design.eurocode_oriented_demand import check_flexure_oriented_flanged


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
    compression_model: str = "rectangular"
    compression_flange_width_m: float | None = None
    compression_flange_thickness_m: float | None = None
    web_width_m: float | None = None

    @property
    def required_steel_area_mm2(self) -> float:
        return self.required_top_steel_area_mm2

    @property
    def provided_steel_area_mm2(self) -> float:
        return self.provided_top_steel_area_mm2

    @property
    def resistance_knm(self) -> float:
        return self.resistance_magnitude_knm

    @property
    def g_flexure_knm(self) -> float:
        return self.g_hogging_knm


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
    The deck is on the tension face at an internal support, so its positive-bending
    compression flange is not credited. ``compression_width_m`` therefore describes
    the verified lower compression zone, commonly a T-girder stem/web.
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
        compression_model="rectangular",
        web_width_m=compression_width_m,
    )


def check_negative_bending_flanged_support(
    *,
    design_moment_knm: float,
    bottom_flange_width_m: float,
    bottom_flange_thickness_m: float,
    web_width_m: float,
    effective_depth_from_bottom_m: float,
    provided_top_steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
) -> NegativeBendingFlexureResult:
    """Check hogging resistance when the physical girder has a lower compression flange.

    This branch is intended for I-type precast girders. All compression geometry is
    measured from the bottom face; the deck remains on the tension side and is not
    credited as a compression flange.
    """
    if design_moment_knm > 0.0:
        raise ValueError("Negative-bending support check requires a non-positive moment.")
    demand = abs(design_moment_knm)
    flexure = check_flexure_oriented_flanged(
        med_knm=demand,
        compression_flange_width_m=bottom_flange_width_m,
        compression_flange_thickness_m=bottom_flange_thickness_m,
        web_width_m=web_width_m,
        effective_depth_from_compression_face_m=effective_depth_from_bottom_m,
        provided_steel_area_mm2=provided_top_steel_area_mm2,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        compression_face="bottom",
    )
    return NegativeBendingFlexureResult(
        design_moment_knm=design_moment_knm,
        design_moment_magnitude_knm=demand,
        required_top_steel_area_mm2=flexure.required_steel_area_mm2,
        provided_top_steel_area_mm2=provided_top_steel_area_mm2,
        resistance_magnitude_knm=flexure.resistance_knm,
        signed_resistance_knm=-flexure.resistance_knm,
        utilization=flexure.utilization,
        g_hogging_knm=flexure.g_flexure_knm,
        compression_width_m=web_width_m,
        effective_depth_m=effective_depth_from_bottom_m,
        passes=flexure.g_flexure_knm >= 0.0,
        status=(
            "EC2 negative-bending support check with explicit bottom compression flange; "
            "deck tension concrete is excluded from compression resistance"
        ),
        compression_model="bottom_flanged",
        compression_flange_width_m=bottom_flange_width_m,
        compression_flange_thickness_m=bottom_flange_thickness_m,
        web_width_m=web_width_m,
    )
