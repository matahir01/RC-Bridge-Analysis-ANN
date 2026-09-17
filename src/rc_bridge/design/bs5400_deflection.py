from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from rc_bridge.analysis.elastic_deflection import simply_supported_midspan_deflection_mm
from rc_bridge.analysis.loads import PointLoad


@dataclass(frozen=True)
class BS5400DeflectionResult:
    permanent_long_term_deflection_mm: float
    live_short_term_deflection_mm: float
    total_deflection_mm: float
    allowable_deflection_mm: float | None
    utilization: float | None
    g_deflection_mm: float | None
    passes: bool | None
    status: str


def bs5400_simple_span_elastic_deflection(
    *,
    span_m: float,
    permanent_udl_kn_m: float,
    live_udl_kn_m: float,
    live_point_loads: Sequence[PointLoad],
    long_term_concrete_modulus_mpa: float,
    short_term_concrete_modulus_mpa: float,
    permanent_second_moment_mm4: float,
    live_second_moment_mm4: float,
    allowable_deflection_mm: float | None = None,
    integration_segments: int = 2000,
) -> BS5400DeflectionResult:
    """Calculate nominal-load elastic midspan deflection for a simple span.

    Permanent actions use the supplied long-term concrete stiffness while live
    actions use short-term stiffness. Section inertias are explicit because the
    appropriate cracked/uncracked stiffness depends on the project serviceability
    analysis. No universal bridge span/deflection limit is assumed.

    Shrinkage curvature, construction-stage sequencing and non-prismatic members
    remain outside this first elastic kernel.
    """
    if permanent_udl_kn_m < 0.0 or live_udl_kn_m < 0.0:
        raise ValueError("Permanent and live UDL values cannot be negative.")
    if min(
        long_term_concrete_modulus_mpa,
        short_term_concrete_modulus_mpa,
        permanent_second_moment_mm4,
        live_second_moment_mm4,
    ) <= 0.0:
        raise ValueError("Elastic moduli and section inertias must be positive.")
    if allowable_deflection_mm is not None and allowable_deflection_mm <= 0.0:
        raise ValueError("allowable_deflection_mm must be positive when supplied.")

    permanent = simply_supported_midspan_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=long_term_concrete_modulus_mpa,
        second_moment_mm4=permanent_second_moment_mm4,
        udl_kn_m=permanent_udl_kn_m,
        integration_segments=integration_segments,
    )
    live = simply_supported_midspan_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=short_term_concrete_modulus_mpa,
        second_moment_mm4=live_second_moment_mm4,
        udl_kn_m=live_udl_kn_m,
        point_loads=live_point_loads,
        integration_segments=integration_segments,
    )
    total = permanent + live

    utilization: float | None = None
    margin: float | None = None
    passes: bool | None = None
    if allowable_deflection_mm is not None:
        utilization = total / allowable_deflection_mm
        margin = allowable_deflection_mm - total
        passes = margin >= 0.0

    return BS5400DeflectionResult(
        permanent_long_term_deflection_mm=permanent,
        live_short_term_deflection_mm=live,
        total_deflection_mm=total,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=margin,
        passes=passes,
        status=(
            "BS 5400 nominal-load elastic simple-span deflection with explicit long-term "
            "permanent and short-term live stiffness; project clearance/profile criterion, "
            "shrinkage curvature and construction-stage effects remain explicit verification items"
        ),
    )
