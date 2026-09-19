from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem


class CapabilityState(str, Enum):
    READY = "ready"
    REQUIRES_ANALYSIS = "requires_analysis"
    VERIFICATION_REQUIRED = "verification_required"
    RESEARCH_LOCKED = "research_locked"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ApplicationCapability:
    name: str
    state: CapabilityState
    detail: str


@dataclass(frozen=True)
class ApplicationDashboard:
    capabilities: tuple[ApplicationCapability, ...]

    @property
    def ready_count(self) -> int:
        return sum(item.state is CapabilityState.READY for item in self.capabilities)

    @property
    def locked_count(self) -> int:
        locked = {
            CapabilityState.REQUIRES_ANALYSIS,
            CapabilityState.VERIFICATION_REQUIRED,
            CapabilityState.RESEARCH_LOCKED,
        }
        return sum(item.state in locked for item in self.capabilities)


def build_application_dashboard(
    project: ProjectInput,
    *,
    has_native_lm1_analysis: bool,
) -> ApplicationDashboard:
    """Describe what the current project can do without weakening verification gates."""

    eurocode = project.design_code is DesignCode.EUROCODE
    continuous = project.geometry.support_system is SupportSystem.CONTINUOUS
    has_profile = project.geometry.girder_profile is not None

    capabilities: list[ApplicationCapability] = [
        ApplicationCapability(
            name="Project definition and persistence",
            state=CapabilityState.READY,
            detail=(
                "Versioned/checksummed project data, application design basis, "
                "rectangular/T/I physical profiles, editable spans and girder layout."
            ),
        ),
        ApplicationCapability(
            name="Physical section and grillage properties",
            state=CapabilityState.READY if has_profile else CapabilityState.REQUIRES_ANALYSIS,
            detail=(
                "Longitudinal/transverse properties are derived from the physical "
                "bridge model; a complete girder profile is required for native analysis."
            ),
        ),
    ]

    if eurocode:
        capabilities.append(
            ApplicationCapability(
                name="Native EN 1991-2 LM1 full-width traffic analysis",
                state=(
                    CapabilityState.READY
                    if has_native_lm1_analysis
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Native grillage M/V/T and traffic-deflection search is available "
                    "for the editable full bridge geometry."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name=(
                    "Continuous-span Eurocode production workflow"
                    if continuous
                    else "Simple-span Eurocode physical-section design workflow"
                ),
                state=CapabilityState.VERIFICATION_REQUIRED,
                detail=(
                    "Flexure, shear, cracking, deflection, fatigue and detailing engines "
                    "are implemented, but final production acceptance remains gated by "
                    "independent MIDAS/STAAD evidence."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="FLM3 fatigue and reinforcement detailing",
                state=CapabilityState.VERIFICATION_REQUIRED,
                detail=(
                    "Dedicated FLM3 girder fatigue and drawing-level reinforcement zoning "
                    "are implemented; clause/project verification and independent acceptance "
                    "remain outstanding."
                ),
            )
        )
    else:
        capabilities.extend(
            (
                ApplicationCapability(
                    name="BS 5400 / BD 37 traffic and girder verification",
                    state=CapabilityState.VERIFICATION_REQUIRED,
                    detail=(
                        "The isolated legacy BS 5400 path supports ULS/SLS/fatigue-scope "
                        "verification, but transverse-distribution and final independent "
                        "acceptance are not certified for production use."
                    ),
                ),
                ApplicationCapability(
                    name="Eurocode LM1 / FLM3 workflows",
                    state=CapabilityState.NOT_APPLICABLE,
                    detail="The current project design code is BS 5400.",
                ),
            )
        )

    capabilities.extend(
        (
            ApplicationCapability(
                name="MIDAS Civil / STAAD.Pro governing-case export",
                state=(
                    CapabilityState.READY
                    if has_native_lm1_analysis
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Exact application-generated governing cases can be exported as .mct "
                    "and .std packages with manifests and result-request templates."
                ),
            ),
            ApplicationCapability(
                name="Independent verification acceptance",
                state=CapabilityState.VERIFICATION_REQUIRED,
                detail=(
                    "Run the application-generated files in installed MIDAS/STAAD, import "
                    "genuine returned results and confirm axes, signs, model equivalence "
                    "and justified tolerances."
                ),
            ),
            ApplicationCapability(
                name="ANN / reliability / RBDO research generation",
                state=CapabilityState.RESEARCH_LOCKED,
                detail=(
                    "Research ground-truth export stays locked until the exact solver "
                    "profile satisfies every deterministic verification milestone."
                ),
            ),
        )
    )
    return ApplicationDashboard(capabilities=tuple(capabilities))
