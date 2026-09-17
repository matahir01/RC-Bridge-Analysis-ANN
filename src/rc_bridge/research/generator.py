from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .dataset import TrainingRecord
from .sampling import VariableRange, latin_hypercube_samples


@dataclass(frozen=True)
class SolverOutputs:
    permanent_moment_knm: float
    traffic_moment_knm: float
    design_moment_knm: float
    resistance_moment_knm: float

    @property
    def g_flexure_knm(self) -> float:
        return self.resistance_moment_knm - self.design_moment_knm


SolverFunction = Callable[[dict[str, float]], SolverOutputs]


REQUIRED_TRAINING_VARIABLES = {
    "span_m",
    "girder_spacing_m",
    "girder_depth_m",
    "deck_thickness_m",
    "fck_mpa",
    "fyk_mpa",
    "steel_area_mm2",
}


def generate_training_records(
    samples: Iterable[dict[str, float]],
    solver: SolverFunction,
    *,
    solver_verified: bool = False,
) -> list[TrainingRecord]:
    """Evaluate deterministic samples and create ANN-ready records.

    ``solver_verified`` is deliberately mandatory for production data. This
    prevents a partially implemented or unverified calculation path from being
    silently used as ANN ground truth.
    """
    if not solver_verified:
        raise RuntimeError(
            "Training data generation is locked until the deterministic solver "
            "path is marked verified."
        )

    records: list[TrainingRecord] = []
    for sample in samples:
        missing = REQUIRED_TRAINING_VARIABLES.difference(sample)
        if missing:
            raise ValueError(f"Sample is missing required variables: {sorted(missing)}")

        out = solver(sample)
        records.append(
            TrainingRecord(
                span_m=sample["span_m"],
                girder_spacing_m=sample["girder_spacing_m"],
                girder_depth_m=sample["girder_depth_m"],
                deck_thickness_m=sample["deck_thickness_m"],
                fck_mpa=sample["fck_mpa"],
                fyk_mpa=sample["fyk_mpa"],
                steel_area_mm2=sample["steel_area_mm2"],
                permanent_moment_knm=out.permanent_moment_knm,
                traffic_moment_knm=out.traffic_moment_knm,
                design_moment_knm=out.design_moment_knm,
                resistance_moment_knm=out.resistance_moment_knm,
                g_flexure_knm=out.g_flexure_knm,
            )
        )
    return records


def lhs_training_samples(
    variables: list[VariableRange],
    sample_count: int,
    seed: int | None = None,
) -> list[dict[str, float]]:
    """Convenience wrapper for reproducible Latin Hypercube training samples."""
    return latin_hypercube_samples(variables, sample_count, seed)
