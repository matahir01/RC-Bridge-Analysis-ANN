from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EffectiveFlangeWidthResult:
    web_width_m: float
    left_physical_outstand_m: float
    right_physical_outstand_m: float
    left_effective_outstand_m: float
    right_effective_outstand_m: float
    effective_flange_width_m: float
    physical_flange_width_m: float
    l0_m: float


def effective_outstand_width_ec2(outstand_m: float, l0_m: float) -> float:
    """First-generation EC2 effective flange outstand for a T/L beam.

    Implements EN 1992-1-1 5.3.2.1 form:
        b_eff,i = min(0.2*b_i + 0.1*l0, 0.2*l0, b_i)

    ``l0`` is the distance between points of zero bending moment and is kept
    explicit so continuous-span and support-region assumptions remain visible.
    """
    if outstand_m < 0:
        raise ValueError("Flange outstand cannot be negative.")
    if l0_m <= 0:
        raise ValueError("l0 must be positive.")
    return min(0.2 * outstand_m + 0.1 * l0_m, 0.2 * l0_m, outstand_m)


def effective_flange_width_ec2(
    web_width_m: float,
    left_outstand_m: float,
    right_outstand_m: float,
    l0_m: float,
) -> EffectiveFlangeWidthResult:
    """Calculate EC2 effective flange width from physical slab outstands."""
    if web_width_m <= 0:
        raise ValueError("Web width must be positive.")
    if left_outstand_m < 0 or right_outstand_m < 0:
        raise ValueError("Physical flange outstands cannot be negative.")

    left_eff = effective_outstand_width_ec2(left_outstand_m, l0_m)
    right_eff = effective_outstand_width_ec2(right_outstand_m, l0_m)
    physical = web_width_m + left_outstand_m + right_outstand_m
    effective = web_width_m + left_eff + right_eff

    return EffectiveFlangeWidthResult(
        web_width_m=web_width_m,
        left_physical_outstand_m=left_outstand_m,
        right_physical_outstand_m=right_outstand_m,
        left_effective_outstand_m=left_eff,
        right_effective_outstand_m=right_eff,
        effective_flange_width_m=min(effective, physical),
        physical_flange_width_m=physical,
        l0_m=l0_m,
    )
