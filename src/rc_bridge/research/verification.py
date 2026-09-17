from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverProfile(str, Enum):
    """Deterministic code/loading profile that produced ANN ground truth."""

    EUROCODE_1G = "eurocode_1g_en1990_en1991_2_en1992_2"
    EUROCODE_CONTINUOUS = "eurocode_continuous_en1990_en1991_2_en1992_2"
    BS5400_BD37_01 = "bs5400_part4_bd37_01"


@dataclass(frozen=True)
class DeterministicSolverVerification:
    """Named verification milestones required before ANN ground-truth export.

    Verification is tied to one solver profile. A verified simple-span Eurocode
    path cannot certify the continuous Eurocode solver, and neither can certify
    BS 5400 records. Torsion remains conditional because some sampled/design cases
    may legitimately have no torsional requirement.
    """

    solver_profile: SolverProfile
    traffic_loading: bool = False
    load_combinations: bool = False
    flexure: bool = False
    shear: bool = False
    cracking: bool = False
    deflection: bool = False
    fatigue: bool = False
    detailing: bool = False
    transverse_distribution: bool = False
    independent_benchmark: bool = False
    torsion_required: bool = False
    torsion: bool = False

    def missing_requirements(self) -> tuple[str, ...]:
        requirements = {
            "traffic_loading": self.traffic_loading,
            "load_combinations": self.load_combinations,
            "flexure": self.flexure,
            "shear": self.shear,
            "cracking": self.cracking,
            "deflection": self.deflection,
            "fatigue": self.fatigue,
            "detailing": self.detailing,
            "transverse_distribution": self.transverse_distribution,
            "independent_benchmark": self.independent_benchmark,
        }
        if self.torsion_required:
            requirements["torsion"] = self.torsion
        return tuple(name for name, complete in requirements.items() if not complete)

    @property
    def ann_ready(self) -> bool:
        return not self.missing_requirements()

    def require_ann_ready(self, *, expected_profile: SolverProfile) -> None:
        if self.solver_profile != expected_profile:
            raise RuntimeError(
                "ANN training data generation remains locked. Verification profile "
                f"{self.solver_profile.value!r} does not match requested solver profile "
                f"{expected_profile.value!r}."
            )
        missing = self.missing_requirements()
        if missing:
            raise RuntimeError(
                "ANN training data generation remains locked. Missing deterministic "
                f"verification milestones: {', '.join(missing)}."
            )
