from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.design.eurocode_fatigue import (
    ConcreteCompressionFatigueResult,
    ReinforcementFatigueResult,
    concrete_compression_fatigue_check,
    reinforcement_fatigue_check,
)
from rc_bridge.workflow.project_fatigue import ConcreteFatigueInput


class LocalDeckFatigueSourceKind(str, Enum):
    DEDICATED_PLATE_ANALYSIS = "dedicated_plate_analysis"
    VERIFIED_EXTERNAL_LOCAL_MODEL = "verified_external_local_model"


@dataclass(frozen=True)
class LocalDeckReinforcementFatigueInput:
    detail_name: str
    reference_stress_range_mpa: float
    lambda_s: float
    characteristic_fatigue_strength_mpa: float
    gamma_s_fat: float = 1.15
    phi_fat: float = 1.0

    def __post_init__(self) -> None:
        if not self.detail_name.strip():
            raise ValueError("Local-deck fatigue detail_name cannot be empty.")
        if self.reference_stress_range_mpa < 0.0:
            raise ValueError("Local-deck reinforcement stress range cannot be negative.")
        if min(
            self.lambda_s,
            self.characteristic_fatigue_strength_mpa,
            self.gamma_s_fat,
            self.phi_fat,
        ) <= 0.0:
            raise ValueError("Local-deck reinforcement fatigue factors must be positive.")


@dataclass(frozen=True)
class ProjectLocalDeckFatigueInput:
    source_kind: LocalDeckFatigueSourceKind
    source_description: str
    reinforcement_details: tuple[LocalDeckReinforcementFatigueInput, ...]
    concrete: ConcreteFatigueInput | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", LocalDeckFatigueSourceKind(self.source_kind))
        if not self.source_description.strip():
            raise ValueError("Local-deck fatigue source_description is required.")
        if not self.reinforcement_details:
            raise ValueError(
                "Local-deck fatigue requires at least one reinforcement stress-range detail."
            )
        names = [item.detail_name for item in self.reinforcement_details]
        if len(set(names)) != len(names):
            raise ValueError("Local-deck fatigue detail names must be unique.")


@dataclass(frozen=True)
class LocalDeckReinforcementFatigueResult:
    detail_name: str
    fatigue: ReinforcementFatigueResult


@dataclass(frozen=True)
class ProjectLocalDeckFatigueResult:
    source_kind: LocalDeckFatigueSourceKind
    source_description: str
    reinforcement_details: tuple[LocalDeckReinforcementFatigueResult, ...]
    concrete: ConcreteCompressionFatigueResult | None
    status: str

    @property
    def passes(self) -> bool:
        return all(item.fatigue.passes for item in self.reinforcement_details) and (
            self.concrete is None or self.concrete.passes
        )


def run_project_local_deck_fatigue(
    project: ProjectInput,
    *,
    fatigue: ProjectLocalDeckFatigueInput,
) -> ProjectLocalDeckFatigueResult:
    """Check local deck fatigue from a dedicated local structural stress source.

    The global beam/grillage model is deliberately not used to manufacture local
    slab reinforcement stresses. Inputs must come from a dedicated plate/slab
    analysis or a separately verified external local model using a fatigue load
    model. This keeps local wheel effects traceable without pretending that a
    longitudinal grillage member force is a local deck-plate stress.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Local-deck fatigue currently supports Eurocode projects only.")

    reinforcement = tuple(
        LocalDeckReinforcementFatigueResult(
            detail_name=item.detail_name,
            fatigue=reinforcement_fatigue_check(
                reference_stress_range_mpa=item.reference_stress_range_mpa,
                lambda_s=item.lambda_s,
                characteristic_fatigue_strength_mpa=(
                    item.characteristic_fatigue_strength_mpa
                ),
                gamma_s_fat=item.gamma_s_fat,
                phi_fat=item.phi_fat,
            ),
        )
        for item in fatigue.reinforcement_details
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

    return ProjectLocalDeckFatigueResult(
        source_kind=fatigue.source_kind,
        source_description=fatigue.source_description,
        reinforcement_details=reinforcement,
        concrete=concrete_result,
        status=(
            "Local deck fatigue checked from a dedicated plate/slab or verified external "
            "local-model stress source. Native global grillage effects are not silently "
            "relabelled as local deck reinforcement stresses."
        ),
    )
