from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeterministicSolverVerification:
    """Named verification milestones required before ANN ground-truth export.

    A single Boolean is intentionally insufficient: each deterministic solver
    capability must be explicitly verified so the training-data provenance is
    auditable. Torsion is conditional because some sampled/design cases may
    legitimately have no torsional design requirement.
    """

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

    def require_ann_ready(self) -> None:
        missing = self.missing_requirements()
        if missing:
            raise RuntimeError(
                "ANN training data generation remains locked. Missing deterministic "
                f"verification milestones: {', '.join(missing)}."
            )
