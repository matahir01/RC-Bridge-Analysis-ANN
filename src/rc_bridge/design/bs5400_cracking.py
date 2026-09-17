from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class BS5400CrackWidthResult:
    crack_width_mm: float
    allowable_crack_width_mm: float
    utilization: float
    g_crack_mm: float
    passes: bool
    acr_mm: float
    mean_strain: float
    status: str


def controlling_surface_distance_mm(
    *,
    bar_spacing_mm: float,
    nominal_cover_to_bar_surface_mm: float,
    bar_diameter_mm: float,
) -> float:
    """Return surface-to-nearest-bar distance a_cr at the mid-spacing point.

    The geometry follows the usual BS 5400 crack-width construction: distance
    from the surface point midway between adjacent bars to the nearest bar
    surface. This is a geometric helper only; callers may supply a_cr directly
    when a different surface point controls.
    """
    if min(bar_spacing_mm, nominal_cover_to_bar_surface_mm, bar_diameter_mm) <= 0.0:
        raise ValueError("Bar spacing, cover and diameter must be positive.")

    centre_cover_mm = nominal_cover_to_bar_surface_mm + bar_diameter_mm / 2.0
    centre_distance_mm = sqrt((bar_spacing_mm / 2.0) ** 2 + centre_cover_mm**2)
    return centre_distance_mm - bar_diameter_mm / 2.0


def surface_crack_width_bs5400(
    *,
    acr_mm: float,
    mean_strain: float,
    nominal_cover_mm: float,
    overall_depth_mm: float,
    compression_depth_mm: float,
    allowable_crack_width_mm: float,
) -> BS5400CrackWidthResult:
    """Evaluate the BS 5400 Part 4 surface flexural crack-width equation.

    For a non-zero compression zone:
        w = 3 a_cr epsilon_m /
            [1 + 2(a_cr - c_nom)/(h - d_c)]

    When d_c is zero, the alternative expression w = 3 a_cr epsilon_m is used.
    ``mean_strain`` must already include the applicable tension-stiffening
    treatment; this kernel deliberately does not infer it from a load case.
    """
    if acr_mm <= 0.0:
        raise ValueError("acr_mm must be positive.")
    if mean_strain < 0.0:
        raise ValueError("mean_strain cannot be negative.")
    if nominal_cover_mm < 0.0:
        raise ValueError("nominal_cover_mm cannot be negative.")
    if overall_depth_mm <= 0.0:
        raise ValueError("overall_depth_mm must be positive.")
    if compression_depth_mm < 0.0 or compression_depth_mm >= overall_depth_mm:
        raise ValueError(
            "compression_depth_mm must be non-negative and smaller than overall_depth_mm."
        )
    if allowable_crack_width_mm <= 0.0:
        raise ValueError("allowable_crack_width_mm must be positive.")

    if compression_depth_mm == 0.0:
        denominator = 1.0
        equation = "BS 5400 alternative surface crack equation for zero compression depth"
    else:
        denominator = 1.0 + 2.0 * (acr_mm - nominal_cover_mm) / (
            overall_depth_mm - compression_depth_mm
        )
        if denominator <= 0.0:
            raise ValueError("Crack-width geometry produces a non-positive denominator.")
        equation = "BS 5400 surface flexural crack-width equation"

    crack_width_mm = 3.0 * acr_mm * mean_strain / denominator
    utilization = crack_width_mm / allowable_crack_width_mm
    margin = allowable_crack_width_mm - crack_width_mm
    return BS5400CrackWidthResult(
        crack_width_mm=crack_width_mm,
        allowable_crack_width_mm=allowable_crack_width_mm,
        utilization=utilization,
        g_crack_mm=margin,
        passes=margin >= 0.0,
        acr_mm=acr_mm,
        mean_strain=mean_strain,
        status=(
            f"{equation}; mean strain must come from a verified BS 5400 serviceability "
            "section analysis before this result is used for design"
        ),
    )
