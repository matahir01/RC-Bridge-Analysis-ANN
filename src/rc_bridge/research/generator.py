from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .dataset import TrainingRecord
from .sampling import VariableRange, latin_hypercube_samples
from .verification import DeterministicSolverVerification


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
    verification: DeterministicSolverVerification | None = None,
    solver_verified: bool | None = None,
) -> list[TrainingRecord]:
    """Evaluate deterministic samples and create ANN-ready records.

    Production export requires named deterministic verification milestones. The
    former ``solver_verified=True`` Boolean is retained only to produce a clear
    migration error; it can no longer unlock training data by itself.
    """
    if solver_verified is not None:
        raise RuntimeError(
            "The legacy solver_verified Boolean no longer unlocks ANN data. "
            "Supply a DeterministicSolverVerification with all required milestones."
        )
    if verification is None:
        raise RuntimeError(
            "Training data generation is locked until structured deterministic "
            "solver verification is supplied."
        )
    verification.require_ann_ready()

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
