from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BS5400TSectionFlexureResult:
    resistance_knm: float
    neutral_axis_depth_m: float
    lever_arm_m: float
    compression_zone: str
    utilization: float
    g_flexure_knm: float
    status: str


def t_section_singly_reinforced_resistance_bs5400(
    *,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fcu_mpa: float,
    fy_mpa: float,
    concrete_block_stress_factor: float = 0.40,
    steel_design_factor: float = 0.87,
    maximum_neutral_axis_ratio: float = 0.50,
    maximum_lever_arm_ratio: float = 0.95,
) -> BS5400TSectionFlexureResult:
    """Legacy BS 5400 positive-bending singly reinforced T-section resistance.

    The rectangular concrete compression block is solved explicitly. If the
    compression block lies within the flange, the section behaves as a wide
    rectangular section. If it enters the web, flange and web compression forces
    are resolved separately. Cases with x/d above the configured singly
    reinforced limit are rejected rather than extrapolated.
    """
    values = (
        effective_flange_width_m,
        flange_thickness_m,
        web_width_m,
        effective_depth_m,
        steel_area_mm2,
        fcu_mpa,
        fy_mpa,
        concrete_block_stress_factor,
        steel_design_factor,
        maximum_neutral_axis_ratio,
        maximum_lever_arm_ratio,
    )
    if any(value <= 0.0 for value in values):
        raise ValueError("T-section dimensions, reinforcement, strengths and factors must be positive.")
    if web_width_m > effective_flange_width_m:
        raise ValueError("web_width_m cannot exceed effective_flange_width_m.")
    if flange_thickness_m >= effective_depth_m:
        raise ValueError("flange_thickness_m must be less than effective_depth_m.")

    beff_mm = effective_flange_width_m * 1000.0
    hf_mm = flange_thickness_m * 1000.0
    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0

    tension_n = steel_design_factor * fy_mpa * steel_area_mm2
    block_stress_mpa = concrete_block_stress_factor * fcu_mpa
    flange_capacity_n = block_stress_mpa * beff_mm * hf_mm

    if tension_n <= flange_capacity_n:
        x_mm = tension_n / (block_stress_mpa * beff_mm)
        compression_zone = "flange"
        compression_centroid_mm = x_mm / 2.0
    else:
        web_force_n = tension_n - flange_capacity_n
        web_block_depth_mm = web_force_n / (block_stress_mpa * bw_mm)
        x_mm = hf_mm + web_block_depth_mm
        compression_zone = "flange_and_web"

        flange_force_n = flange_capacity_n
        web_centroid_mm = hf_mm + web_block_depth_mm / 2.0
        compression_centroid_mm = (
            flange_force_n * (hf_mm / 2.0) + web_force_n * web_centroid_mm
        ) / tension_n

    if x_mm > maximum_neutral_axis_ratio * d_mm:
        raise ValueError(
            "Neutral axis exceeds the configured singly reinforced BS 5400 limit; "
            "compression reinforcement or another section model is required."
        )

    lever_arm_mm = d_mm - compression_centroid_mm
    lever_arm_mm = min(lever_arm_mm, maximum_lever_arm_ratio * d_mm)
    resistance_knm = tension_n * lever_arm_mm / 1_000_000.0

    return BS5400TSectionFlexureResult(
        resistance_knm=resistance_knm,
        neutral_axis_depth_m=x_mm / 1000.0,
        lever_arm_m=lever_arm_mm / 1000.0,
        compression_zone=compression_zone,
        utilization=0.0,
        g_flexure_knm=resistance_knm,
        status=(
            "BS 5400 Part 4 legacy/comparison positive-bending T-section kernel; "
            "effective flange width, edition coefficients and detailing must be independently verified"
        ),
    )


def check_t_section_flexure_bs5400(
    *,
    med_knm: float,
    effective_flange_width_m: float,
    flange_thickness_m: float,
    web_width_m: float,
    effective_depth_m: float,
    steel_area_mm2: float,
    fcu_mpa: float,
    fy_mpa: float,
) -> BS5400TSectionFlexureResult:
    if med_knm < 0.0:
        raise ValueError("med_knm cannot be negative.")
    base = t_section_singly_reinforced_resistance_bs5400(
        effective_flange_width_m=effective_flange_width_m,
        flange_thickness_m=flange_thickness_m,
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        steel_area_mm2=steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fy_mpa=fy_mpa,
    )
    utilization = med_knm / base.resistance_knm if base.resistance_knm > 0.0 else float("inf")
    return BS5400TSectionFlexureResult(
        resistance_knm=base.resistance_knm,
        neutral_axis_depth_m=base.neutral_axis_depth_m,
        lever_arm_m=base.lever_arm_m,
        compression_zone=base.compression_zone,
        utilization=utilization,
        g_flexure_knm=base.resistance_knm - med_knm,
        status=base.status,
    )
