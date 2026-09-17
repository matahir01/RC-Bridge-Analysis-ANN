from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.bs5400_shear import check_shear_bs5400


@dataclass(frozen=True)
class BS5400ProvidedShearResistanceResult:
    provided_asv_per_s_mm2_per_m: float
    minimum_asv_per_s_mm2_per_m: float
    link_limited_resistance_kn: float
    maximum_resistance_kn: float
    governing_resistance_kn: float
    utilization: float
    g_shear_kn: float
    status: str


def provided_vertical_link_resistance_bs5400(
    *,
    ved_kn: float,
    provided_asv_per_s_mm2_per_m: float,
    web_width_m: float,
    effective_depth_m: float,
    longitudinal_steel_area_mm2: float,
    fcu_mpa: float,
    fyv_mpa: float,
) -> BS5400ProvidedShearResistanceResult:
    """Return BS 5400 beam shear resistance for actual supplied vertical links.

    The Part 4 vertical-link design equation is inverted to recover the shear
    stress supported by the supplied A_sv/s_v. Beam minimum links are enforced;
    the resulting resistance is capped by the maximum web shear resistance.
    """
    if ved_kn < 0.0:
        raise ValueError("ved_kn cannot be negative.")
    if provided_asv_per_s_mm2_per_m <= 0.0:
        raise ValueError("Provided A_sv/s_v must be positive.")

    base = check_shear_bs5400(
        ved_kn=ved_kn,
        web_width_m=web_width_m,
        effective_depth_m=effective_depth_m,
        longitudinal_steel_area_mm2=longitudinal_steel_area_mm2,
        fcu_mpa=fcu_mpa,
        fyv_mpa=fyv_mpa,
    )
    if provided_asv_per_s_mm2_per_m + 1e-9 < base.minimum_asv_per_s_mm2_per_m:
        raise ValueError(
            "Provided BS 5400 vertical links are below the minimum beam-link requirement."
        )

    bw_mm = web_width_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    asv_per_s_mm2_per_mm = provided_asv_per_s_mm2_per_m / 1000.0

    link_capacity_stress_mpa = (
        asv_per_s_mm2_per_mm * 0.87 * base.effective_fyv_mpa / bw_mm
        - 0.40
        + base.concrete_design_shear_stress_mpa
    )
    link_capacity_stress_mpa = max(
        link_capacity_stress_mpa,
        base.concrete_design_shear_stress_mpa,
    )
    link_limited_resistance_kn = link_capacity_stress_mpa * bw_mm * d_mm / 1000.0
    governing_resistance_kn = min(
        link_limited_resistance_kn,
        base.maximum_resistance_kn,
    )
    utilization = (
        ved_kn / governing_resistance_kn if governing_resistance_kn > 0.0 else float("inf")
    )

    return BS5400ProvidedShearResistanceResult(
        provided_asv_per_s_mm2_per_m=provided_asv_per_s_mm2_per_m,
        minimum_asv_per_s_mm2_per_m=base.minimum_asv_per_s_mm2_per_m,
        link_limited_resistance_kn=link_limited_resistance_kn,
        maximum_resistance_kn=base.maximum_resistance_kn,
        governing_resistance_kn=governing_resistance_kn,
        utilization=utilization,
        g_shear_kn=governing_resistance_kn - ved_kn,
        status=(
            "BS 5400 Part 4 supplied vertical-link resistance; minimum beam links "
            "enforced and resistance capped by maximum web shear resistance"
        ),
    )
