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
    has_extended_actions: bool = False,
    has_integrated_design: bool = False,
    has_local_deck_design: bool = False,
    has_fatigue: bool = False,
    design_blocker_count: int = 0,
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
                name="Permanent actions and EN 1990 combination interpretation",
                state=(
                    CapabilityState.READY
                    if has_native_lm1_analysis
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Physical girder/deck self-weight, editable surfacing/barrier/services "
                    "actions and simple-span Gk + native-LM1 Qk ULS/SLS interpretation are "
                    "available. Braking, thermal, pedestrian, LM2, safety-barrier impact, "
                    "construction-stage and static wind actions are exposed separately."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="Additional actions + wind",
                state=(
                    CapabilityState.READY
                    if has_extended_actions
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Braking/acceleration, thermal kinematics/restraint benchmark, "
                    "pedestrian footway loading, LM2 axle scanning, safety-barrier "
                    "accidental action, construction-stage separation and static wind "
                    "resultants are implemented. Longitudinal/transverse actions feed "
                    "explicit bearing/restraint checks instead of being faked as vertical loads."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="Native local deck/slab design",
                state=(
                    CapabilityState.READY
                    if has_local_deck_design
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Continuous transverse slab-strip analysis spans over the actual girder "
                    "lines and edge cantilevers under permanent actions, dispersed LM2 wheel "
                    "patches and the barrier-impact vertical wheel, with EC2 top/bottom "
                    "transverse reinforcement selection."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="Desktop FLM3 fatigue",
                state=(
                    CapabilityState.READY
                    if has_fatigue
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Native full-width FLM3 traffic is connected to the selected girder "
                    "reinforcement, concrete compression and vertical links. Project fatigue "
                    "detail-category inputs remain explicit rather than hidden constants."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="Integrated action-to-design coverage",
                state=(
                    CapabilityState.READY
                    if has_integrated_design and design_blocker_count == 0
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Compatible traffic groups feed girder ULS/SLS design; construction "
                    "stages can govern selected bars/links; braking/thermal/wind feed the "
                    "bearing/restraint path; local deck LM2/barrier-wheel flexure is checked "
                    "by the native slab solver and barrier impact remains a separate accidental "
                    "restraint check. "
                    + (
                        "No unresolved model/input blockers remain in the current design run."
                        if has_integrated_design and design_blocker_count == 0
                        else (
                            f"{design_blocker_count} explicit design blocker(s) remain."
                            if has_integrated_design
                            else "Run LM1, Additional actions 1-6 and integrated design."
                        )
                    )
                ),
            )
        )
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
                    "genuine independent-solver evidence for the exact project/profile."
                ),
            )
        )
        capabilities.append(
            ApplicationCapability(
                name="FLM3 fatigue and reinforcement detailing",
                state=(
                    CapabilityState.VERIFICATION_REQUIRED
                    if has_fatigue
                    else CapabilityState.REQUIRES_ANALYSIS
                ),
                detail=(
                    "Dedicated FLM3 girder fatigue is now a desktop workflow and drawing-level "
                    "reinforcement zoning remains implemented; independent acceptance remains "
                    "outstanding."
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
                    "Run the application-generated files in an installed independent solver, "
                    "import genuine returned results and confirm axes, signs, model equivalence "
                    "and justified tolerances. Deterministic v1 uses the STAAD acceptance path; "
                    "MIDAS cross-verification is deferred to V2."
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
