from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.design.eurocode_fatigue import (
    ConcreteCompressionFatigueResult,
    ReinforcementFatigueResult,
    concrete_compression_fatigue_check,
    reinforcement_fatigue_check,
)


@dataclass(frozen=True)
class ReinforcementFatigueInput:
    reference_stress_range_mpa: float
    lambda_s: float
    characteristic_fatigue_strength_mpa: float
    gamma_s_fat: float = 1.15
    phi_fat: float = 1.0


@dataclass(frozen=True)
class ConcreteFatigueInput:
    sigma_c_max_mpa: float
    sigma_c_min_mpa: float
    gamma_c: float = 1.50
    alpha_cc: float = 1.0
    k1: float = 0.85
    beta_cc_t0: float = 1.0


@dataclass(frozen=True)
class ProjectFatigueInput:
    source_description: str
    reinforcement: ReinforcementFatigueInput
    concrete: ConcreteFatigueInput | None = None

    def __post_init__(self) -> None:
        if not self.source_description.strip():
            raise ValueError("source_description is required for fatigue traceability.")


@dataclass(frozen=True)
class ProjectFatigueResult:
    source_description: str
    reinforcement: ReinforcementFatigueResult
    concrete: ConcreteCompressionFatigueResult | None
    status: str

    @property
    def passes(self) -> bool:
        return self.reinforcement.passes and (
            self.concrete is None or self.concrete.passes
        )


def run_project_eurocode_fatigue(
    project: ProjectInput,
    *,
    fatigue: ProjectFatigueInput,
) -> ProjectFatigueResult:
    """Run traceable first-generation EC2 bridge fatigue checks.

    The reinforcement reference stress range must come from a dedicated fatigue
    analysis/load model. This workflow deliberately does not reuse the LM1
    characteristic traffic envelope as a fatigue action.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("This fatigue workflow currently supports Eurocode projects only.")

    steel = fatigue.reinforcement
    reinforcement = reinforcement_fatigue_check(
        reference_stress_range_mpa=steel.reference_stress_range_mpa,
        lambda_s=steel.lambda_s,
        phi_fat=steel.phi_fat,
        characteristic_fatigue_strength_mpa=steel.characteristic_fatigue_strength_mpa,
        gamma_s_fat=steel.gamma_s_fat,
    )

    concrete_result = None
    if fatigue.concrete is not None:
        concrete = fatigue.concrete
        concrete_result = concrete_compression_fatigue_check(
            sigma_c_max_mpa=concrete.sigma_c_max_mpa,
            sigma_c_min_mpa=concrete.sigma_c_min_mpa,
            fck_mpa=float(project.materials.fck_mpa),
            gamma_c=concrete.gamma_c,
            alpha_cc=concrete.alpha_cc,
            k1=concrete.k1,
            beta_cc_t0=concrete.beta_cc_t0,
        )

    return ProjectFatigueResult(
        source_description=fatigue.source_description,
        reinforcement=reinforcement,
        concrete=concrete_result,
        status=(
            "Fatigue checked from an explicit fatigue-analysis stress source; "
            "LM1 characteristic traffic effects are not substituted for fatigue loading"
        ),
    )
