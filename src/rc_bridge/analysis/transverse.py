from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionResult:
    girder_index: int
    fraction: float
    method: str


def equal_distribution(girder_count: int) -> list[DistributionResult]:
    """Simple equal-share baseline for verification only.

    This is intentionally not presented as a final bridge-design method. It is
    retained as a transparent baseline against which refined transverse models
    and imported grillage results can be compared.
    """
    if girder_count <= 0:
        raise ValueError("Girder count must be positive.")
    share = 1.0 / girder_count
    return [
        DistributionResult(i + 1, share, "equal_share_baseline")
        for i in range(girder_count)
    ]


def normalize_distribution(factors: list[float], method: str = "user_or_grillage") -> list[DistributionResult]:
    """Normalize externally determined transverse distribution factors.

    This is the integration point for grillage-analysis exports. Factors may be
    force shares, reaction shares, or other consistently defined positive
    influence values; the caller remains responsible for the physical meaning.
    """
    if not factors:
        raise ValueError("At least one distribution factor is required.")
    if any(value < 0 for value in factors):
        raise ValueError("Distribution factors cannot be negative.")
    total = sum(factors)
    if total <= 0:
        raise ValueError("Distribution factors must have a positive sum.")
    return [
        DistributionResult(i + 1, value / total, method)
        for i, value in enumerate(factors)
    ]


def apply_distribution(total_effect: float, distribution: list[DistributionResult]) -> list[float]:
    if total_effect < 0:
        raise ValueError("Total effect must be non-negative for this helper.")
    if not distribution:
        raise ValueError("Distribution results are required.")
    fraction_sum = sum(item.fraction for item in distribution)
    if abs(fraction_sum - 1.0) > 1e-9:
        raise ValueError("Distribution fractions must sum to 1.0.")
    return [total_effect * item.fraction for item in distribution]
