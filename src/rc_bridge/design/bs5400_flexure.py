from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BS5400RectangularFlexureResult:
    resistance_knm: float
    steel_controlled_resistance_knm: float
    concrete_limit_resistance_knm: float
    lever_arm_m: float
    utilization: float
    g_flexure_knm: float
    status: str


def rectangular_singly_reinforced_resistance_bs5400(
    *,
    width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fcu_mpa: float,
    fy_mpa: float,
    steel_design_factor: float = 0.87,
    lever_arm_coefficient: float = 1.10,
    lever_arm_limit_ratio: float = 0.95,
    concrete_moment_limit_coefficient: float = 0.15,
) -> BS5400RectangularFlexureResult:
    """Legacy BS 5400 Part 4 singly reinforced rectangular flexure check.

    This implements the common design equations used for comparison-mode bridge
    calculations. Coefficients remain explicit because BS 5400 is a legacy code
    and project/edition requirements must be verified before design use.
    """
    if min(width_m, effective_depth_m, steel_area_mm2, fcu_mpa, fy_mpa) <= 0.0:
        raise ValueError("Section dimensions, reinforcement and strengths must be positive.")
    if min(
        steel_design_factor,
        lever_arm_coefficient,
        lever_arm_limit_ratio,
        concrete_moment_limit_coefficient,
    ) <= 0.0:
        raise ValueError("BS 5400 flexure coefficients must be positive.")

    b_mm = width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    z_raw_mm = d_mm * (
        1.0 - lever_arm_coefficient * fy_mpa * steel_area_mm2 / (fcu_mpa * b_mm * d_mm)
    )
    if z_raw_mm <= 0.0:
        raise ValueError("Reinforcement is outside the scope of the singly reinforced model.")
    z_mm = min(z_raw_mm, lever_arm_limit_ratio * d_mm)

    steel_moment_knm = (
        steel_design_factor * fy_mpa * steel_area_mm2 * z_mm / 1_000_000.0
    )
    concrete_limit_knm = (
        concrete_moment_limit_coefficient * fcu_mpa * b_mm * d_mm**2 / 1_000_000.0
    )
    resistance_knm = min(steel_moment_knm, concrete_limit_knm)

    return BS5400RectangularFlexureResult(
        resistance_knm=resistance_knm,
        steel_controlled_resistance_knm=steel_moment_knm,
        concrete_limit_resistance_knm=concrete_limit_knm,
        lever_arm_m=z_mm / 1000.0,
        utilization=0.0,
        g_flexure_knm=resistance_knm,
        status=(
            "BS 5400 Part 4 legacy/comparison rectangular flexure kernel; "
            "edition/project coefficients and ductility/detailing checks must be verified"
        ),
    )


def check_rectangular_flexure_bs5400(
    *,
    med_knm: float,
    width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fcu_mpa: float,
    fy_mpa: float,
) -> BS5400RectangularFlexureResult:
    if med_knm < 0.0:
        raise ValueError("med_knm cannot be negative.")
    base = rectangular_singly_reinforced_resistance_bs5400(
        width_m=width_m,
        effective_depth_m=effective_depth_m,
        steel_area_mm2=steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fy_mpa=fy_mpa,
    )
    utilization = med_knm / base.resistance_knm if base.resistance_knm > 0.0 else float("inf")
    return BS5400RectangularFlexureResult(
        resistance_knm=base.resistance_knm,
        steel_controlled_resistance_knm=base.steel_controlled_resistance_knm,
        concrete_limit_resistance_knm=base.concrete_limit_resistance_knm,
        lever_arm_m=base.lever_arm_m,
        utilization=utilization,
        g_flexure_knm=base.resistance_knm - med_knm,
        status=base.status,
    )
