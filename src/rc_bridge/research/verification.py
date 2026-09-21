from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SolverProfile(str, Enum):
    """Deterministic code/loading profile that produced ANN ground truth."""

    EUROCODE_1G = "eurocode_1g_en1990_en1991_2_en1992_2"
    EUROCODE_CONTINUOUS = "eurocode_continuous_en1990_en1991_2_en1992_2"
    BS5400_BD37_01 = "bs5400_part4_bd37_01"


class VerificationScope(str, Enum):
    """Named verification scope used when unlocking deterministic outputs.

    FULL_APPLICATION_V1 retains the original conservative all-feature gate.
    MSC_SIMPLE_SPAN_ANN is deliberately narrower and covers only the
    deterministic limit states exported by the current MSc four-target ANN
    dataset: flexure, shear, cracking and deflection under the accepted
    permanent+LM1 simple-span Eurocode profile.
    """

    FULL_APPLICATION_V1 = "full_application_v1"
    MSC_SIMPLE_SPAN_ANN = "msc_simple_span_ann"


FULL_APPLICATION_REQUIREMENTS = (
    "traffic_loading",
    "load_combinations",
    "flexure",
    "shear",
    "cracking",
    "deflection",
    "fatigue",
    "detailing",
    "transverse_distribution",
    "independent_benchmark",
)

MSC_SIMPLE_SPAN_ANN_REQUIREMENTS = (
    "traffic_loading",
    "load_combinations",
    "flexure",
    "shear",
    "cracking",
    "deflection",
    "transverse_distribution",
    "independent_benchmark",
)


def requirements_for_scope(scope: VerificationScope) -> tuple[str, ...]:
    if scope is VerificationScope.FULL_APPLICATION_V1:
        return FULL_APPLICATION_REQUIREMENTS
    if scope is VerificationScope.MSC_SIMPLE_SPAN_ANN:
        return MSC_SIMPLE_SPAN_ANN_REQUIREMENTS
    raise ValueError(f"Unsupported verification scope: {scope!r}")


@dataclass(frozen=True)
class DeterministicSolverVerification:
    """Named verification milestones for one deterministic solver profile.

    Verification is tied to one solver profile. A verified simple-span Eurocode
    path cannot certify the continuous Eurocode solver, and neither can certify
    BS 5400 records. Torsion remains conditional because some sampled/design
    cases may legitimately have no torsional requirement.

    The legacy ann_ready property intentionally retains the conservative
    full-application gate. Research dataset generation may request the narrower
    explicitly named MSc scope; callers must opt into that scope rather than
    receiving an implicit relaxation.
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

    def _status_by_name(self) -> dict[str, bool]:
        return {
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
            "torsion": self.torsion,
        }

    def missing_requirements_for(
        self,
        scope: VerificationScope,
    ) -> tuple[str, ...]:
        status = self._status_by_name()
        required = list(requirements_for_scope(scope))
        if scope is VerificationScope.FULL_APPLICATION_V1 and self.torsion_required:
            required.append("torsion")
        return tuple(name for name in required if not status[name])

    def missing_requirements(self) -> tuple[str, ...]:
        """Backward-compatible full-application requirement list."""
        return self.missing_requirements_for(VerificationScope.FULL_APPLICATION_V1)

    @property
    def ann_ready(self) -> bool:
        """Conservative legacy readiness: all full-application gates pass."""
        return not self.missing_requirements()

    def ready_for(self, scope: VerificationScope) -> bool:
        return not self.missing_requirements_for(scope)

    def require_ready_for(
        self,
        *,
        expected_profile: SolverProfile,
        scope: VerificationScope,
    ) -> None:
        if self.solver_profile != expected_profile:
            raise RuntimeError(
                "ANN training data generation remains locked. Verification profile "
                f"{self.solver_profile.value!r} does not match requested solver profile "
                f"{expected_profile.value!r}."
            )
        missing = self.missing_requirements_for(scope)
        if missing:
            raise RuntimeError(
                "ANN training data generation remains locked for verification scope "
                f"{scope.value!r}. Missing deterministic verification milestones: "
                f"{', '.join(missing)}."
            )

    def require_ann_ready(self, *, expected_profile: SolverProfile) -> None:
        """Retain the original all-feature ANN lock for existing callers."""
        self.require_ready_for(
            expected_profile=expected_profile,
            scope=VerificationScope.FULL_APPLICATION_V1,
        )
