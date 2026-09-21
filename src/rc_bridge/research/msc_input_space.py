from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from rc_bridge.core.models import ProjectInput


class ResearchVariableRole(str, Enum):
    """Role of a variable in the MSc ANN/reliability/RBDO workflow."""

    RANDOM = "random"
    DESIGN = "design"


class DistributionFamily(str, Enum):
    """Probability family used only for stochastic reliability variables."""

    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    EXTREME_VALUE = "extreme_value"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class EvidenceStatus(str, Enum):
    """How far the numerical probabilistic definition has been justified."""

    EVIDENCE_BACKED_PROVISIONAL = "evidence_backed_provisional"
    FAMILY_ONLY = "family_only"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ResearchVariableDefinition:
    """One machine-readable MSc input-space definition.

    Design variables need search bounds before LHS/RBDO generation.
    Random variables need a probability model for reliability analysis.
    A value may be evidence-backed but still provisional until the thesis
    methodology explicitly freezes it.
    """

    name: str
    symbol: str
    role: ResearchVariableRole
    baseline: float | None
    distribution: DistributionFamily
    evidence_status: EvidenceStatus
    lower_bound: float | None = None
    upper_bound: float | None = None
    mean: float | None = None
    standard_deviation: float | None = None
    coefficient_of_variation: float | None = None
    evidence_note: str = ""

    def __post_init__(self) -> None:
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.upper_bound <= self.lower_bound
        ):
            raise ValueError(f"Invalid bounds for {self.name}.")
        for value in (
            self.baseline,
            self.lower_bound,
            self.upper_bound,
            self.mean,
            self.standard_deviation,
            self.coefficient_of_variation,
        ):
            if value is not None and not isfinite(float(value)):
                raise ValueError(f"Non-finite MSc input-space value for {self.name}.")
        if self.standard_deviation is not None and self.standard_deviation <= 0.0:
            raise ValueError(f"Standard deviation must be positive for {self.name}.")
        if (
            self.coefficient_of_variation is not None
            and self.coefficient_of_variation <= 0.0
        ):
            raise ValueError(f"Coefficient of variation must be positive for {self.name}.")
        if (
            self.role is ResearchVariableRole.DESIGN
            and self.distribution is not DistributionFamily.NOT_APPLICABLE
        ):
            raise ValueError(
                f"Design variable {self.name} must not be assigned a reliability distribution."
            )

    @property
    def sampling_bounds_ready(self) -> bool:
        return self.lower_bound is not None and self.upper_bound is not None

    @property
    def reliability_model_ready(self) -> bool:
        if self.role is ResearchVariableRole.DESIGN:
            return True
        if self.distribution in (
            DistributionFamily.UNRESOLVED,
            DistributionFamily.NOT_APPLICABLE,
        ):
            return False
        return (
            self.mean is not None
            and (
                self.standard_deviation is not None
                or self.coefficient_of_variation is not None
            )
        )


MSC_DEFLECTION_LIMIT_SPAN_RATIO = 250.0


@dataclass(frozen=True)
class MScScopeLock:
    """Fixed research context around which the ANN/RBDO input space is defined."""

    analysis_span_m: float = 15.0
    physical_precast_girder_length_m: float = 14.95
    deck_width_m: float = 11.0
    carriageway_width_m: float = 7.0
    girder_count: int = 7
    girder_spacing_m: float = 1.70
    baseline_precast_width_m: float = 0.40
    baseline_precast_depth_m: float = 0.95
    precast_false_slab_depth_m: float = 0.075
    in_situ_slab_depth_m: float = 0.175
    baseline_fck_mpa: float = 35.0
    baseline_fyk_mpa: float = 500.0
    deflection_limit_span_ratio: float = MSC_DEFLECTION_LIMIT_SPAN_RATIO

    @property
    def baseline_deflection_limit_mm(self) -> float:
        return self.analysis_span_m * 1000.0 / self.deflection_limit_span_ratio


MSC_SCOPE_LOCK = MScScopeLock()


MSC_CORE_VARIABLES: tuple[ResearchVariableDefinition, ...] = (
    ResearchVariableDefinition(
        name="fck_mpa",
        symbol="f_ck",
        role=ResearchVariableRole.RANDOM,
        baseline=35.0,
        distribution=DistributionFamily.LOGNORMAL,
        evidence_status=EvidenceStatus.EVIDENCE_BACKED_PROVISIONAL,
        coefficient_of_variation=0.17,
        evidence_note=(
            "JCSS RC reliability example uses lognormal concrete compression strength "
            "with COV 0.17. Distribution family is also consistent with JRC reliability "
            "guidance for material properties. Mean mapping for the C35/45 baseline is "
            "not frozen yet."
        ),
    ),
    ResearchVariableDefinition(
        name="fyk_mpa",
        symbol="f_y",
        role=ResearchVariableRole.RANDOM,
        baseline=500.0,
        distribution=DistributionFamily.NORMAL,
        evidence_status=EvidenceStatus.EVIDENCE_BACKED_PROVISIONAL,
        mean=560.0,
        standard_deviation=30.0,
        evidence_note=(
            "JCSS reinforcing-steel model permits a normal yield-strength model; for "
            "high-standard production it gives sigma about 30 MPa and mean S_nom+2sigma, "
            "which gives about 560 MPa for nominal 500 MPa steel."
        ),
    ),
    ResearchVariableDefinition(
        name="girder_width_m",
        symbol="b",
        role=ResearchVariableRole.DESIGN,
        baseline=0.40,
        distribution=DistributionFamily.NOT_APPLICABLE,
        evidence_status=EvidenceStatus.UNRESOLVED,
        evidence_note=(
            "RBDO design variable. Bounds must be justified from feasible bridge-girder "
            "geometry and the verified positive-bending composite-flange domain."
        ),
    ),
    ResearchVariableDefinition(
        name="girder_depth_m",
        symbol="h",
        role=ResearchVariableRole.DESIGN,
        baseline=0.95,
        distribution=DistributionFamily.NOT_APPLICABLE,
        evidence_status=EvidenceStatus.UNRESOLVED,
        evidence_note=(
            "RBDO design variable. Bounds must preserve feasible construction, effective "
            "depth and the verified simple-span layered-section domain."
        ),
    ),
    ResearchVariableDefinition(
        name="longitudinal_steel_area_mm2",
        symbol="A_s",
        role=ResearchVariableRole.DESIGN,
        baseline=None,
        distribution=DistributionFamily.NOT_APPLICABLE,
        evidence_status=EvidenceStatus.UNRESOLVED,
        evidence_note=(
            "RBDO design variable. Baseline and bounds should be taken from the deterministic "
            "girder design and feasible discrete bar arrangements, not invented independently."
        ),
    ),
    ResearchVariableDefinition(
        name="permanent_action_multiplier",
        symbol="lambda_G",
        role=ResearchVariableRole.RANDOM,
        baseline=1.0,
        distribution=DistributionFamily.NORMAL,
        evidence_status=EvidenceStatus.FAMILY_ONLY,
        evidence_note=(
            "JRC reliability guidance supports Gaussian permanent-action effects. JCSS gives "
            "ordinary-concrete unit-weight COV about 0.04, but that does not by itself define "
            "the uncertainty of the complete bridge permanent-action model, so mean/COV remain "
            "unfrozen."
        ),
    ),
    ResearchVariableDefinition(
        name="traffic_action_multiplier",
        symbol="lambda_Q",
        role=ResearchVariableRole.RANDOM,
        baseline=1.0,
        distribution=DistributionFamily.EXTREME_VALUE,
        evidence_status=EvidenceStatus.FAMILY_ONLY,
        evidence_note=(
            "JRC reliability guidance recommends an extreme-value family when a variable "
            "represents a maximum over a reference period. Bridge-specific LM1 traffic "
            "probabilistic parameters remain to be justified before reliability sampling."
        ),
    ),
)


def msc_variable(name: str) -> ResearchVariableDefinition:
    match = next((item for item in MSC_CORE_VARIABLES if item.name == name), None)
    if match is None:
        raise KeyError(f"Unknown MSc core variable: {name}")
    return match


def unresolved_sampling_items() -> tuple[str, ...]:
    """Return variables that still block pilot LHS input-space freezing."""

    unresolved: list[str] = []
    for item in MSC_CORE_VARIABLES:
        if not item.sampling_bounds_ready:
            unresolved.append(f"{item.name}: sampling bounds")
        if not item.reliability_model_ready:
            unresolved.append(f"{item.name}: reliability parameters")
    return tuple(unresolved)


def require_input_space_frozen() -> None:
    """Prevent accidental large-dataset generation before methodology freeze."""

    blockers = unresolved_sampling_items()
    if blockers:
        raise RuntimeError(
            "MSc input space is not frozen for pilot/full dataset generation: "
            + "; ".join(blockers)
        )


def deflection_limit_mm(span_m: float) -> float:
    if span_m <= 0.0:
        raise ValueError("Span must be positive.")
    return span_m * 1000.0 / MSC_DEFLECTION_LIMIT_SPAN_RATIO


def scope_lock_project_blockers(project: ProjectInput) -> tuple[str, ...]:
    """Check only fixed research-context quantities, not RBDO design variables."""

    geometry = project.geometry
    blockers: list[str] = []
    if tuple(float(value) for value in geometry.span_lengths_m) != (
        MSC_SCOPE_LOCK.analysis_span_m,
    ):
        blockers.append("analysis span must remain 15.0 m")
    if abs(float(geometry.deck_width_m) - MSC_SCOPE_LOCK.deck_width_m) > 1.0e-9:
        blockers.append("deck width must remain 11.0 m")
    if (
        abs(float(geometry.carriageway_width_m) - MSC_SCOPE_LOCK.carriageway_width_m)
        > 1.0e-9
    ):
        blockers.append("carriageway width must remain 7.0 m")
    if int(geometry.girder_count) != MSC_SCOPE_LOCK.girder_count:
        blockers.append("girder count must remain seven")
    if abs(float(geometry.girder_spacing_m) - MSC_SCOPE_LOCK.girder_spacing_m) > 1.0e-9:
        blockers.append("girder spacing must remain 1.70 m")
    if (
        geometry.precast_girder_length_m is None
        or abs(
            float(geometry.precast_girder_length_m)
            - MSC_SCOPE_LOCK.physical_precast_girder_length_m
        )
        > 1.0e-9
    ):
        blockers.append("physical precast girder length must remain 14.95 m")
    deck = geometry.deck_construction
    if (
        abs(
            float(deck.precast_false_slab_depth_m)
            - MSC_SCOPE_LOCK.precast_false_slab_depth_m
        )
        > 1.0e-9
    ):
        blockers.append("precast false slab depth must remain 75 mm")
    if (
        abs(float(deck.in_situ_slab_depth_m) - MSC_SCOPE_LOCK.in_situ_slab_depth_m)
        > 1.0e-9
    ):
        blockers.append("in-situ deck depth must remain 175 mm")
    return tuple(blockers)
