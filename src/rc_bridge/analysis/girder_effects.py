from __future__ import annotations

from dataclasses import dataclass

from .transverse import DistributionResult


@dataclass(frozen=True)
class GirderEffect:
    girder_index: int
    moment_knm: float
    shear_kn: float
    distribution_fraction: float
    method: str


def distribute_effects_to_girders(
    total_moment_knm: float,
    total_shear_kn: float,
    distribution: list[DistributionResult],
) -> list[GirderEffect]:
    if total_moment_knm < 0 or total_shear_kn < 0:
        raise ValueError("Moment and shear magnitudes must be non-negative.")
    if not distribution:
        raise ValueError("Distribution results are required.")

    fraction_sum = sum(item.fraction for item in distribution)
    if abs(fraction_sum - 1.0) > 1e-9:
        raise ValueError("Distribution fractions must sum to 1.0.")

    return [
        GirderEffect(
            girder_index=item.girder_index,
            moment_knm=total_moment_knm * item.fraction,
            shear_kn=total_shear_kn * item.fraction,
            distribution_fraction=item.fraction,
            method=item.method,
        )
        for item in distribution
    ]
