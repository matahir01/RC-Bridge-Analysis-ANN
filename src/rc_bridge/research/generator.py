from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .dataset import TrainingRecord
from .sampling import VariableRange, latin_hypercube_samples
from .verification import (\n    DeterministicSolverVerification,\n    SolverProfile,\n    VerificationScope,\n)


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


COMMON_REQUIRED_TRAINING_VARIABLES = {
    "span_m",
    "girder_spacing_m",
    "girder_depth_m",
    "deck_thickness_m",
    "fyk_mpa",
    "steel_area_mm2",
}

PROFILE_REQUIRED_TRAINING_VARIABLES = {
    SolverProfile.EUROCODE_1G: {"fck_mpa"},
    SolverProfile.BS5400_BD37_01: {"fcu_mpa"},
}


def generate_training_records(
    samples: Iterable[dict[str, float]],
    solver: SolverFunction,
    *,
    solver_profile: SolverProfile | None = None,
    verification: DeterministicSolverVerification | None = None,
    solver_verified: bool | None = None,
) -> list[TrainingRecord]:
    """Evaluate deterministic samples and create provenance-safe ANN records.

    Export requires a named deterministic solver profile and a verification
    object for that exact profile. Eurocode rows require fck; BS 5400/BD 37/01
    rows require fcu. The former ``solver_verified=True`` Boolean can no longer
    unlock ground-truth generation.
    """
    if solver_verified is not None:
        raise RuntimeError(
            "The legacy solver_verified Boolean no longer unlocks ANN data. "
            "Supply a DeterministicSolverVerification with all required milestones."
        )
    if solver_profile is None:
        raise RuntimeError(
            "Training data generation is locked until an explicit deterministic "
            "solver_profile is supplied."
        )
    if verification is None:
        raise RuntimeError(
            "Training data generation is locked until structured deterministic "
            "solver verification is supplied."
        )
    verification.require_ready_for(\n        expected_profile=solver_profile,\n        scope=verification_scope,\n    )

    required = COMMON_REQUIRED_TRAINING_VARIABLES | PROFILE_REQUIRED_TRAINING_VARIABLES[
        solver_profile
    ]
    records: list[TrainingRecord] = []
    for sample in samples:
        missing = required.difference(sample)
        if missing:
            raise ValueError(f"Sample is missing required variables: {sorted(missing)}")

        out = solver(sample)
        records.append(
            TrainingRecord(
                solver_profile=solver_profile.value,
                span_m=sample["span_m"],
                girder_spacing_m=sample["girder_spacing_m"],
                girder_depth_m=sample["girder_depth_m"],
                deck_thickness_m=sample["deck_thickness_m"],
                fck_mpa=sample.get("fck_mpa"),
                fcu_mpa=sample.get("fcu_mpa"),
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
