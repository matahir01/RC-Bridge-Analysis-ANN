from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import (
    DesignCode,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
)
from rc_bridge.research.acceptance_matrix import (
    V1AcceptanceMatrix,
    eurocode_simple_span_v1_acceptance_matrix,
)
from rc_bridge.research.verification import VerificationScope

MSC_ANN_TARGETS = (
    "g_flexure_knm",
    "g_shear_kn",
    "g_crack_mm",
    "g_deflection_mm",
)

MSC_ACTION_SCOPE = "permanent actions + EN 1991-2 LM1"
MSC_FLEXURE_SCOPE = (
    "positive bending with the governing compression block retained within the "
    "verified effective composite flange domain"
)


@dataclass(frozen=True)
class MScDeterministicGate:
    """Machine-readable deterministic gate for the current four-target MSc ANN."""

    project_blockers: tuple[str, ...]
    verification_missing: tuple[str, ...]
    targets: tuple[str, ...] = MSC_ANN_TARGETS

    @property
    def project_scope_ready(self) -> bool:
        return not self.project_blockers

    @property
    def verification_ready(self) -> bool:
        return not self.verification_missing

    @property
    def ready(self) -> bool:
        return self.project_scope_ready and self.verification_ready

    def require_ready(self) -> None:
        blockers = (*self.project_blockers, *self.verification_missing)
        if blockers:
            raise RuntimeError(
                "MSc deterministic research gate remains locked: "
                + "; ".join(blockers)
            )


def msc_project_scope_blockers(project: ProjectInput) -> tuple[str, ...]:
    """Return project-level blockers for the verified simple-span research domain."""

    blockers: list[str] = []
    geometry = project.geometry
    if project.design_code is not DesignCode.EUROCODE:
        blockers.append("design_code must be Eurocode")
    if geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        blockers.append("support_system must be simply supported")
    if len(geometry.span_lengths_m) != 1:
        blockers.append("the current MSc profile requires exactly one span")
    if geometry.section_type is not SectionType.RECTANGULAR:
        blockers.append(
            "the current MSc profile requires a rectangular precast girder"
        )
    if not isinstance(geometry.girder_profile, RectangularGirderProfile):
        blockers.append(
            "a complete rectangular precast girder profile is required"
        )
    if not geometry.deck_construction.in_situ_slab_composite_participation:
        blockers.append("the in-situ slab must participate in composite positive bending")
    if geometry.deck_construction.false_slab_composite_participation:
        blockers.append(
            "precast false-slab composite participation is outside the verified MSc baseline"
        )
    return tuple(blockers)


def evaluate_msc_deterministic_gate(
    project: ProjectInput,
    *,
    matrix: V1AcceptanceMatrix | None = None,
) -> MScDeterministicGate:
    """Combine project-scope checks with the independently accepted MSc manifest."""

    acceptance = matrix or eurocode_simple_span_v1_acceptance_matrix()
    verification = acceptance.msc_research_verification_manifest()
    missing = verification.missing_requirements_for(
        VerificationScope.MSC_SIMPLE_SPAN_ANN
    )
    return MScDeterministicGate(
        project_blockers=msc_project_scope_blockers(project),
        verification_missing=missing,
    )


def require_msc_project_scope(project: ProjectInput) -> None:
    blockers = msc_project_scope_blockers(project)
    if blockers:
        raise RuntimeError(
            "Project is outside the verified MSc simple-span scope: "
            + "; ".join(blockers)
        )
