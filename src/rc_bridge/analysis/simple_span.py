from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimpleSpanResult:
    reaction_left_kn: float
    reaction_right_kn: float
    max_moment_knm: float
    max_shear_kn: float


def udl_simple_span(span_m: float, udl_kn_m: float) -> SimpleSpanResult:
    """Closed-form simply supported beam response to a full-span UDL."""
    if span_m <= 0:
        raise ValueError("span_m must be greater than zero")
    if udl_kn_m < 0:
        raise ValueError("udl_kn_m cannot be negative")

    reaction = udl_kn_m * span_m / 2.0
    return SimpleSpanResult(
        reaction_left_kn=reaction,
        reaction_right_kn=reaction,
        max_moment_knm=udl_kn_m * span_m**2 / 8.0,
        max_shear_kn=reaction,
    )
