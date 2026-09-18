from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from rc_bridge.analysis.lane_distribution import (
    equal_lane_distribution,
    equal_remaining_area_distribution,
)
from rc_bridge.analysis.loads import (
    deck_self_weight_per_girder_kn_m,
    section_self_weight_kn_m,
)
from rc_bridge.analysis.simple_span import (
    DistributedLoadSegment,
    simple_span_distributed_load_response,
    simple_span_distributed_response_at_x,
)
from rc_bridge.codes.common import FactoredCombination, LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import (
    DesignCode,
    PermanentActionStage,
    PermanentLineActionCategory,
    ProjectInput,
    SupportSystem,
)
from rc_bridge.design.eurocode_deflection import SimpleSpanMomentDiagram
from rc_bridge.workflow.eurocode_bridge_traffic import (
    BridgeLM1TrafficResult,
    run_simple_span_lm1_bridge_traffic,
)
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeServiceabilityInput,
    EurocodeTGirderWorkflowResult,
    TGirderDesignInput,
    run_eurocode_t_girder_case,
)


@dataclass(frozen=True)
class UniformPermanentLoadInput:
    """Explicit additional characteristic permanent line loads on one girder."""

    girder_self_weight_kn_m: float = 0.0
    surfacing_and_finishes_kn_m: float = 0.0
    assigned_barrier_and_services_kn_m: float = 0.0
    other_kn_m: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.girder_self_weight_kn_m,
            self.surfacing_and_finishes_kn_m,
            self.assigned_barrier_and_services_kn_m,
            self.other_kn_m,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("Permanent line-load components cannot be negative.")

    @property
    def total_additional_kn_m(self) -> float:
        return (
            self.girder_self_weight_kn_m
            + self.surfacing_and_finishes_kn_m
            + self.assigned_barrier_and_services_kn_m
            + self.other_kn_m
        )


@dataclass(frozen=True)
class ProjectPermanentLoadSegment:
    """One auditable per-girder permanent line-load segment in global x."""

    source: str
    category: str
    stage: PermanentActionStage
    magnitude_kn_m: float
    x_start_m: float
    x_end_m: float

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.category.strip():
            raise ValueError("Permanent-load segment source and category are required.")
        if self.magnitude_kn_m < 0.0:
            raise ValueError("Permanent-load segment magnitude cannot be negative.")
        if self.x_start_m < 0.0 or self.x_end_m <= self.x_start_m:
            raise ValueError("Permanent-load segment bounds must define a positive length.")

    @property
    def total_load_kn(self) -> float:
        return self.magnitude_kn_m * (self.x_end_m - self.x_start_m)


@dataclass(frozen=True)
class ProjectGirderCombinationSet:
    girder_index: int
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    persistent_uls: FactoredCombination
    characteristic_sls: FactoredCombination
    frequent_sls: FactoredCombination
    quasi_permanent_sls: FactoredCombination
    traffic_distribution_method: str


class SLSCombinationChoice(str, Enum):
    CHARACTERISTIC = "characteristic"
    FREQUENT = "frequent"
    QUASI_PERMANENT = "quasi_permanent"


@dataclass(frozen=True)
class ProjectServiceabilitySelection:
    input: EurocodeServiceabilityInput
    crack_combination_name: str
    deflection_combination_name: str
    deflection_method: str = "equivalent full-span UDL from selected SLS maximum moment"


@dataclass(frozen=True)
class ProjectTGirderVerificationResult:
    combinations: ProjectGirderCombinationSet
    serviceability: ProjectServiceabilitySelection
    materials: EurocodeMaterialInput
    design: EurocodeTGirderWorkflowResult


def project_eurocode_material_input(
    project: ProjectInput,
    *,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
) -> EurocodeMaterialInput:
    """Build the girder-workflow material input from project properties.

    Ecm and the default fct,eff are derived from first-generation EC2 concrete
    properties. Supply ``fct_eff_mpa`` explicitly for early-age cracking or any
    other stage where the effective tensile strength differs from 28-day fctm.
    A project elastic-modulus override takes precedence over the EC2 estimate.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Eurocode material derivation requires a Eurocode project.")
    if fct_eff_mpa is not None and fct_eff_mpa <= 0.0:
        raise ValueError("fct_eff_mpa must be positive when supplied.")
    if es_mpa <= 0.0:
        raise ValueError("es_mpa must be positive.")

    fck_mpa = float(project.materials.fck_mpa)
    properties = concrete_properties_ec2(fck_mpa)
    ecm_mpa = (
        float(project.materials.elastic_modulus_mpa)
        if project.materials.elastic_modulus_mpa is not None
        else properties.ecm_mpa
    )
    return EurocodeMaterialInput(
        fck_mpa=fck_mpa,
        fyk_mpa=float(project.materials.fyk_mpa),
        ecm_mpa=ecm_mpa,
        fct_eff_mpa=fct_eff_mpa or properties.fctm_mpa,
        es_mpa=es_mpa,
    )


def girder_deck_tributary_width_m(project: ProjectInput, *, girder_index: int) -> float:
    """Return physical deck tributary width for any longitudinal girder line.

    Internal girders receive the spacing between adjacent midlines. Exterior
    girders receive half the adjacent spacing plus the physical deck overhang.
    This lets the permanent-load path cover edge girders without pretending
    their deck tributary width equals an internal spacing.
    """
    geometry = project.geometry
    girder_count = int(geometry.girder_count)
    if not 1 <= girder_index <= girder_count:
        raise IndexError("girder_index is outside the project girder layout.")

    left_boundary, right_boundary = girder_deck_tributary_bounds_m(
        project,
        girder_index=girder_index,
    )
    tributary_width = right_boundary - left_boundary
    if tributary_width <= 0.0:
        raise ValueError("Computed girder deck tributary width must be positive.")
    return tributary_width


def girder_deck_tributary_bounds_m(
    project: ProjectInput,
    *,
    girder_index: int,
) -> tuple[float, float]:
    """Return physical left/right transverse tributary boundaries for one girder."""
    geometry = project.geometry
    girder_count = int(geometry.girder_count)
    if not 1 <= girder_index <= girder_count:
        raise IndexError("girder_index is outside the project girder layout.")
    width = float(geometry.deck_width_m)
    spacing = float(geometry.girder_spacing_m)
    first_y = -width / 2.0 + float(geometry.nominal_edge_overhang_m)
    coordinates = tuple(first_y + index * spacing for index in range(girder_count))
    y = coordinates[girder_index - 1]
    left = -width / 2.0 if girder_index == 1 else 0.5 * (coordinates[girder_index - 2] + y)
    right = width / 2.0 if girder_index == girder_count else 0.5 * (y + coordinates[girder_index])
    return left, right


def _girder_line_action_share(
    project: ProjectInput,
    *,
    girder_index: int,
    y_m: float,
) -> float:
    """Return the statical share of one positioned longitudinal line action."""
    girder_count = int(project.geometry.girder_count)
    if not 1 <= girder_index <= girder_count:
        raise IndexError("girder_index is outside the project girder layout.")
    width = float(project.geometry.deck_width_m)
    spacing = float(project.geometry.girder_spacing_m)
    first_y = -width / 2.0 + float(project.geometry.nominal_edge_overhang_m)
    coordinates = tuple(first_y + index * spacing for index in range(girder_count))
    shares = [0.0] * girder_count
    if y_m <= coordinates[0]:
        shares[0] = 1.0
    elif y_m >= coordinates[-1]:
        shares[-1] = 1.0
    else:
        left_index = next(
            index
            for index in range(girder_count - 1)
            if coordinates[index] <= y_m <= coordinates[index + 1]
        )
        fraction_right = (y_m - coordinates[left_index]) / spacing
        shares[left_index] = 1.0 - fraction_right
        shares[left_index + 1] = fraction_right
    return shares[girder_index - 1]


def girder_superimposed_permanent_segments(
    project: ProjectInput,
    *,
    girder_index: int,
) -> tuple[ProjectPermanentLoadSegment, ...]:
    """Return positioned physical superimposed actions allocated to one girder.

    Area layers are assigned by exact overlap with the girder tributary band.
    Longitudinal line actions between girder lines are shared by linear statics;
    actions on deck overhangs are assigned to the adjacent exterior girder. The
    latter captures vertical load allocation only—local overhang bending remains
    a transverse-deck design action. Longitudinal bounds and construction stage
    are retained rather than collapsed into an equivalent full-span UDL.
    """
    girder_count = int(project.geometry.girder_count)
    if not 1 <= girder_index <= girder_count:
        raise IndexError("girder_index is outside the project girder layout.")
    left, right = girder_deck_tributary_bounds_m(project, girder_index=girder_index)
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    segments: list[ProjectPermanentLoadSegment] = []
    for layer in project.permanent_actions.surfacing_layers:
        overlap = max(0.0, min(right, layer.y_end_m) - max(left, layer.y_start_m))
        magnitude = overlap * layer.pressure_kn_m2
        if magnitude <= 0.0:
            continue
        segments.append(
            ProjectPermanentLoadSegment(
                source=layer.name,
                category="surfacing",
                stage=layer.stage,
                magnitude_kn_m=magnitude,
                x_start_m=float(layer.x_start_m),
                x_end_m=(total_length if layer.x_end_m is None else float(layer.x_end_m)),
            )
        )
    for action in project.permanent_actions.line_actions:
        share = _girder_line_action_share(
            project,
            girder_index=girder_index,
            y_m=float(action.y_m),
        )
        magnitude = float(action.magnitude_kn_m) * share
        if magnitude <= 0.0:
            continue
        segments.append(
            ProjectPermanentLoadSegment(
                source=action.name,
                category=action.category.value,
                stage=action.stage,
                magnitude_kn_m=magnitude,
                x_start_m=float(action.x_start_m),
                x_end_m=(
                    total_length if action.x_end_m is None else float(action.x_end_m)
                ),
            )
        )
    return tuple(segments)


def girder_superimposed_permanent_loads_kn_m(
    project: ProjectInput,
    *,
    girder_index: int,
) -> tuple[float, float, float]:
    """Return full-bridge equivalent line loads for the legacy summary API.

    Longitudinally partial actions are divided by total bridge length. Analysis
    uses :func:`girder_superimposed_permanent_segments` and does not replace
    those actions with this equivalent value.
    """
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    by_category = {
        "surfacing": 0.0,
        PermanentLineActionCategory.BARRIER.value: 0.0,
        PermanentLineActionCategory.SERVICES.value: 0.0,
        PermanentLineActionCategory.OTHER.value: 0.0,
    }
    for segment in girder_superimposed_permanent_segments(
        project,
        girder_index=girder_index,
    ):
        by_category[segment.category] += segment.total_load_kn / total_length
    barriers_and_services = (
        by_category[PermanentLineActionCategory.BARRIER.value]
        + by_category[PermanentLineActionCategory.SERVICES.value]
    )
    return (
        by_category["surfacing"],
        barriers_and_services,
        by_category[PermanentLineActionCategory.OTHER.value],
    )


def girder_false_slab_self_weight_kn_m(
    project: ProjectInput,
    *,
    girder_index: int,
) -> float:
    """Precast false-slab self-weight on one girder tributary strip."""
    return deck_self_weight_per_girder_kn_m(
        deck_thickness_m=float(
            project.geometry.deck_construction.precast_false_slab_depth_m
        ),
        girder_spacing_m=girder_deck_tributary_width_m(
            project,
            girder_index=girder_index,
        ),
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def girder_in_situ_deck_self_weight_kn_m(
    project: ProjectInput,
    *,
    girder_index: int,
) -> float:
    """Wet in-situ slab self-weight on one girder tributary strip."""
    return deck_self_weight_per_girder_kn_m(
        deck_thickness_m=float(project.geometry.deck_construction.in_situ_slab_depth_m),
        girder_spacing_m=girder_deck_tributary_width_m(
            project,
            girder_index=girder_index,
        ),
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def girder_deck_self_weight_kn_m(project: ProjectInput, *, girder_index: int) -> float:
    """Total physical deck self-weight carried by one girder tributary strip."""
    return girder_false_slab_self_weight_kn_m(
        project,
        girder_index=girder_index,
    ) + girder_in_situ_deck_self_weight_kn_m(
        project,
        girder_index=girder_index,
    )


def internal_girder_deck_self_weight_kn_m(project: ProjectInput) -> float:
    """Physical deck self-weight on the standard internal tributary width."""
    girder_count = int(project.geometry.girder_count)
    if girder_count < 3:
        raise ValueError("An internal girder requires at least three girder lines.")
    return girder_deck_self_weight_kn_m(project, girder_index=2)


def physical_girder_self_weight_kn_m(project: ProjectInput) -> float | None:
    """Return physical precast girder self-weight when a complete profile is defined."""
    area_m2 = project.geometry.girder_profile_area_m2
    if area_m2 is None:
        return None
    return section_self_weight_kn_m(
        area_m2=area_m2,
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def girder_permanent_load_segments(
    project: ProjectInput,
    *,
    girder_index: int,
    additional: UniformPermanentLoadInput | None = None,
    included_stages: Sequence[PermanentActionStage] | None = None,
) -> tuple[ProjectPermanentLoadSegment, ...]:
    """Build the auditable global-x permanent load pattern for one girder.

    Physical girder, precast false-slab and wet in-situ slab weights retain
    their actual stiffness states. The false slab is loaded before any optional
    verified false-slab composite participation is activated for the wet pour.
    Positioned surfacing/line actions retain their longitudinal extents and
    stages. Legacy explicit overrides are full-length actions and are rejected
    whenever they would duplicate an automated physical category.
    """
    girder_count = int(project.geometry.girder_count)
    if not 1 <= girder_index <= girder_count:
        raise IndexError("girder_index is outside the project girder layout.")
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    extra = additional or UniformPermanentLoadInput()
    profile_self_weight_kn_m = physical_girder_self_weight_kn_m(project)
    if (
        profile_self_weight_kn_m is not None
        and extra.girder_self_weight_kn_m > 0.0
        and abs(extra.girder_self_weight_kn_m - profile_self_weight_kn_m) > 1.0e-9
    ):
        raise ValueError(
            "Explicit girder_self_weight_kn_m conflicts with the value derived "
            "from the physical girder profile."
        )

    automated = girder_superimposed_permanent_segments(
        project,
        girder_index=girder_index,
    )
    automated_categories = {segment.category for segment in automated}
    if "surfacing" in automated_categories and extra.surfacing_and_finishes_kn_m > 0.0:
        raise ValueError("Explicit surfacing load would double count physical surfacing layers.")
    if (
        automated_categories
        & {
            PermanentLineActionCategory.BARRIER.value,
            PermanentLineActionCategory.SERVICES.value,
        }
        and extra.assigned_barrier_and_services_kn_m > 0.0
    ):
        raise ValueError(
            "Explicit barrier/services load would double count positioned line actions."
        )
    if (
        PermanentLineActionCategory.OTHER.value in automated_categories
        and extra.other_kn_m > 0.0
    ):
        raise ValueError("Explicit other permanent load would double count physical line actions.")

    segments: list[ProjectPermanentLoadSegment] = []
    girder_self_weight_kn_m = (
        profile_self_weight_kn_m
        if profile_self_weight_kn_m is not None
        else extra.girder_self_weight_kn_m
    )
    if girder_self_weight_kn_m > 0.0:
        segments.append(
            ProjectPermanentLoadSegment(
                source=(
                    "physical girder profile self-weight"
                    if profile_self_weight_kn_m is not None
                    else "explicit girder self-weight"
                ),
                category="girder_self_weight",
                stage=PermanentActionStage.PRECAST_GIRDER,
                magnitude_kn_m=girder_self_weight_kn_m,
                x_start_m=0.0,
                x_end_m=total_length,
            )
        )
    # The precast false slab is installed while the girder-only stiffness is
    # active. Its own weight therefore remains in the PRECAST_GIRDER increment.
    # If verified composite false-slab participation is later activated for the
    # wet pour, only the wet in-situ slab benefits from that increased stiffness.
    false_slab_weight = girder_false_slab_self_weight_kn_m(
        project,
        girder_index=girder_index,
    )
    if false_slab_weight > 0.0:
        segments.append(
            ProjectPermanentLoadSegment(
                source="physical precast false slab self-weight",
                category="deck_self_weight",
                stage=PermanentActionStage.PRECAST_GIRDER,
                magnitude_kn_m=false_slab_weight,
                x_start_m=0.0,
                x_end_m=total_length,
            )
        )
    in_situ_weight = girder_in_situ_deck_self_weight_kn_m(
        project,
        girder_index=girder_index,
    )
    if in_situ_weight > 0.0:
        segments.append(
            ProjectPermanentLoadSegment(
                source="physical wet in-situ deck self-weight",
                category="deck_self_weight",
                stage=PermanentActionStage.DECK_CONSTRUCTION,
                magnitude_kn_m=in_situ_weight,
                x_start_m=0.0,
                x_end_m=total_length,
            )
        )
    segments.extend(automated)
    for source, category, magnitude in (
        (
            "explicit surfacing and finishes",
            "surfacing",
            extra.surfacing_and_finishes_kn_m,
        ),
        (
            "explicit assigned barriers and services",
            "barriers_and_services",
            extra.assigned_barrier_and_services_kn_m,
        ),
        ("explicit other permanent action", "other", extra.other_kn_m),
    ):
        if magnitude > 0.0:
            segments.append(
                ProjectPermanentLoadSegment(
                    source=source,
                    category=category,
                    stage=PermanentActionStage.SUPERIMPOSED,
                    magnitude_kn_m=magnitude,
                    x_start_m=0.0,
                    x_end_m=total_length,
                )
            )

    if included_stages is None:
        return tuple(segments)
    stages = {PermanentActionStage(value) for value in included_stages}
    return tuple(segment for segment in segments if segment.stage in stages)


def girder_span_permanent_load_segments(
    project: ProjectInput,
    *,
    girder_index: int,
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
    included_stages: Sequence[PermanentActionStage] | None = None,
) -> tuple[DistributedLoadSegment, ...]:
    """Clip global permanent segments to one span and return local coordinates."""
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")
    span_start = sum(
        float(value) for value in project.geometry.span_lengths_m[:span_index]
    )
    span_length = float(project.geometry.span_lengths_m[span_index])
    span_end = span_start + span_length
    local: list[DistributedLoadSegment] = []
    for segment in girder_permanent_load_segments(
        project,
        girder_index=girder_index,
        additional=additional,
        included_stages=included_stages,
    ):
        start = max(segment.x_start_m, span_start)
        end = min(segment.x_end_m, span_end)
        if end <= start:
            continue
        local.append(
            DistributedLoadSegment(
                magnitude_kn_m=segment.magnitude_kn_m,
                start_m=start - span_start,
                end_m=end - span_start,
                label=f"{segment.category}: {segment.source}",
                stage=segment.stage.value,
            )
        )
    return tuple(local)


def girder_permanent_moments_knm_at(
    project: ProjectInput,
    *,
    girder_index: int,
    stations_m: Sequence[float],
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
    included_stages: Sequence[PermanentActionStage] | None = None,
) -> tuple[float, ...]:
    """Return the exact simple-span permanent moment field at local stations."""
    span_m = float(project.geometry.span_lengths_m[span_index])
    loads = girder_span_permanent_load_segments(
        project,
        girder_index=girder_index,
        span_index=span_index,
        additional=additional,
        included_stages=included_stages,
    )
    return tuple(
        simple_span_distributed_response_at_x(span_m, loads, float(x_m))[0]
        for x_m in stations_m
    )


def girder_characteristic_permanent_effects(
    project: ProjectInput,
    *,
    girder_index: int,
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
    included_stages: Sequence[PermanentActionStage] | None = None,
) -> LoadEffects:
    """Return simple-span characteristic permanent effects for any girder.

    Deck self-weight uses the physical deck tributary width of the selected
    girder. Longitudinal action extents are analysed directly using exact
    segmented-load reactions and zero-shear moment extrema. Construction stages
    can be selected explicitly; omission means all permanent stages.
    """
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This permanent-load adapter currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    result = simple_span_distributed_load_response(
        span_m,
        girder_span_permanent_load_segments(
            project,
            girder_index=girder_index,
            span_index=span_index,
            additional=additional,
            included_stages=included_stages,
        ),
    )
    return LoadEffects(
        moment_knm=result.max_moment_knm,
        shear_kn=result.max_abs_shear_kn,
    )


def internal_girder_characteristic_permanent_effects(
    project: ProjectInput,
    *,
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
    included_stages: Sequence[PermanentActionStage] | None = None,
) -> LoadEffects:
    """Return simple-span characteristic G effects for a representative internal girder."""
    girder_count = int(project.geometry.girder_count)
    if girder_count < 3:
        raise ValueError("An internal girder requires at least three girder lines.")
    return girder_characteristic_permanent_effects(
        project,
        girder_index=2,
        span_index=span_index,
        additional=additional,
        included_stages=included_stages,
    )


def run_project_lm1_equal_share_verification(
    project: ProjectInput,
    *,
    span_index: int = 0,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> BridgeLM1TrafficResult:
    """Run the current simple-span LM1 benchmark with equal transverse shares.

    This is intentionally labelled verification-only. It checks longitudinal
    LM1 mechanics, bridge geometry plumbing, and conservation of total traffic
    effects. It is not the production transverse-distribution solution; that
    must use validated analytical factors or imported grillage results.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("This verification workflow currently supports Eurocode projects only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This verification workflow currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    carriageway_width_m = float(project.geometry.carriageway_width_m)
    girder_count = int(project.geometry.girder_count)
    layout = notional_lane_layout(carriageway_width_m)

    lane_distributions = [
        equal_lane_distribution(lane_number, girder_count)
        for lane_number in range(1, layout.lane_count + 1)
    ]
    remaining_distribution = (
        equal_remaining_area_distribution(girder_count)
        if layout.remaining_width_m > 0.0
        else None
    )

    return run_simple_span_lm1_bridge_traffic(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        lane_distributions=lane_distributions,
        remaining_area_distribution=remaining_distribution,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )


def project_internal_girder_combinations_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    sls_factors: ServiceabilityPsiFactors,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> ProjectGirderCombinationSet:
    """Assemble Gk/Qk and Eurocode ULS/SLS effects for an internal girder.

    The traffic branch intentionally uses the equal-share verification model.
    Production design must replace it with validated analytical or imported
    grillage distribution before the solver is marked verified for ANN use.
    """
    girder_count = int(project.geometry.girder_count)
    if not 2 <= girder_index <= girder_count - 1:
        raise ValueError(
            "This helper is for internal girders only; edge-girder permanent-load "
            "tributary widths must be modelled separately."
        )

    permanent = internal_girder_characteristic_permanent_effects(
        project,
        span_index=span_index,
        additional=additional_permanent,
    )
    traffic_result = run_project_lm1_equal_share_verification(
        project,
        span_index=span_index,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    traffic_item = traffic_result.girder_effects[girder_index - 1]
    traffic = LoadEffects(
        moment_knm=traffic_item.moment_knm,
        shear_kn=traffic_item.shear_kn,
    )

    return ProjectGirderCombinationSet(
        girder_index=girder_index,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        persistent_uls=persistent_uls(permanent, traffic, uls_factors),
        characteristic_sls=characteristic_sls(permanent, traffic),
        frequent_sls=frequent_sls(permanent, traffic, sls_factors),
        quasi_permanent_sls=quasi_permanent_sls(permanent, traffic, sls_factors),
        traffic_distribution_method=traffic_item.method,
    )


def _select_sls_combination(
    combinations: ProjectGirderCombinationSet,
    choice: SLSCombinationChoice,
) -> FactoredCombination:
    if choice == SLSCombinationChoice.CHARACTERISTIC:
        return combinations.characteristic_sls
    if choice == SLSCombinationChoice.FREQUENT:
        return combinations.frequent_sls
    if choice == SLSCombinationChoice.QUASI_PERMANENT:
        return combinations.quasi_permanent_sls
    raise ValueError(f"Unsupported SLS combination choice: {choice}")


def project_serviceability_from_combinations(
    combinations: ProjectGirderCombinationSet,
    *,
    span_m: float,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
    deflection_moment_diagram: SimpleSpanMomentDiagram | None = None,
    deflection_service_moment_knm: float | None = None,
) -> ProjectServiceabilitySelection:
    """Build SLS inputs from explicitly selected EN 1990 combinations.

    A supplied co-located moment field drives signed curvature integration. If
    no field is available, the compatibility route back-calculates a full-span
    line load as w_eq = 8M/L^2 and labels that approximation explicitly.
    """
    if span_m <= 0.0:
        raise ValueError("span_m must be positive.")
    if crack_limit_mm <= 0.0 or allowable_deflection_mm <= 0.0:
        raise ValueError("SLS limits must be positive.")

    crack_case = _select_sls_combination(combinations, crack_combination)
    deflection_case = _select_sls_combination(combinations, deflection_combination)
    equivalent_udl_kn_m = 8.0 * deflection_case.effects.moment_knm / span_m**2

    return ProjectServiceabilitySelection(
        input=EurocodeServiceabilityInput(
            service_moment_knm=crack_case.effects.moment_knm,
            equivalent_full_span_udl_kn_m=equivalent_udl_kn_m,
            crack_limit_mm=crack_limit_mm,
            allowable_deflection_mm=allowable_deflection_mm,
            creep_coefficient=creep_coefficient,
            deflection_beta=deflection_beta,
            crack_kt=crack_kt,
            deflection_moment_diagram=deflection_moment_diagram,
            deflection_service_moment_knm=deflection_service_moment_knm,
        ),
        crack_combination_name=crack_case.name,
        deflection_combination_name=deflection_case.name,
        deflection_method=(
            "signed M/EI curvature integration of co-located permanent and traffic response"
            if deflection_moment_diagram is not None
            else "equivalent full-span UDL from selected SLS maximum moment"
        ),
    )


def run_project_internal_t_girder_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    section: TGirderDesignInput,
    sls_factors: ServiceabilityPsiFactors,
    crack_combination: SLSCombinationChoice,
    deflection_combination: SLSCombinationChoice,
    crack_limit_mm: float,
    allowable_deflection_mm: float,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
    creep_coefficient: float = 0.0,
    deflection_beta: float = 0.5,
    crack_kt: float = 0.4,
    cot_theta: float = 2.0,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> ProjectTGirderVerificationResult:
    """Run the current project-to-design path for an internal T-girder.

    This remains a verification workflow because traffic is still distributed
    equally between girders. It is suitable for plumbing and hand-check
    validation, not for production bridge design or ANN data generation until
    transverse distribution is replaced and independently verified.
    """
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    expected_total_depth_m = (
        float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    )
    if abs(section.total_depth_m - expected_total_depth_m) > 1e-9:
        raise ValueError(
            "T-girder total depth must match project girder depth plus physical deck depth."
        )

    combinations = project_internal_girder_combinations_verification(
        project,
        girder_index=girder_index,
        sls_factors=sls_factors,
        span_index=span_index,
        additional_permanent=additional_permanent,
        uls_factors=uls_factors,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
    materials = project_eurocode_material_input(
        project,
        fct_eff_mpa=fct_eff_mpa,
        es_mpa=es_mpa,
    )
    serviceability = project_serviceability_from_combinations(
        combinations,
        span_m=span_m,
        crack_combination=crack_combination,
        deflection_combination=deflection_combination,
        crack_limit_mm=crack_limit_mm,
        allowable_deflection_mm=allowable_deflection_mm,
        creep_coefficient=creep_coefficient,
        deflection_beta=deflection_beta,
        crack_kt=crack_kt,
    )
    design = run_eurocode_t_girder_case(
        girder_index=girder_index,
        span_m=span_m,
        permanent_effects=combinations.permanent_characteristic,
        traffic_effects=combinations.traffic_characteristic,
        section=section,
        materials=materials,
        serviceability=serviceability.input,
        uls_factors=uls_factors,
        cot_theta=cot_theta,
    )

    return ProjectTGirderVerificationResult(
        combinations=combinations,
        serviceability=serviceability,
        materials=materials,
        design=design,
    )
