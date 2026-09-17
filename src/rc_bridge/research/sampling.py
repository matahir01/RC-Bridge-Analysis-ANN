from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc


@dataclass(frozen=True)
class VariableRange:
    name: str
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if self.upper <= self.lower:
            raise ValueError(f"Upper bound must exceed lower bound for {self.name}.")


def latin_hypercube_samples(
    variables: list[VariableRange],
    sample_count: int,
    seed: int | None = None,
) -> list[dict[str, float]]:
    if not variables:
        raise ValueError("At least one variable is required.")
    if sample_count <= 0:
        raise ValueError("Sample count must be positive.")

    sampler = qmc.LatinHypercube(d=len(variables), seed=seed)
    unit = sampler.random(n=sample_count)
    lower = np.array([v.lower for v in variables], dtype=float)
    upper = np.array([v.upper for v in variables], dtype=float)
    scaled = qmc.scale(unit, lower, upper)

    return [
        {variable.name: float(value) for variable, value in zip(variables, row)}
        for row in scaled
    ]
