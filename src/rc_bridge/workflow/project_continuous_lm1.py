from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.analysis.continuous_influence import (
    AdverseUDLEffect,
    InfluenceResponseKind,
    section_influence_line,
)
from rc_bridge.analysis.lane_distribution import (
    AggregatedGirderSectionEffect,
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
    aggregate_lm1_continuous_section_effects,
)
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    SignedSectionCombinationSet,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.codes.eurocode.en1991_2 import (
    LM1AdjustmentFactors,
    NotionalLaneLayout,
    notional_lane_layout,
)
from rc_bridge.codes.eurocode.lm1_effects import (
    LM1ContinuousSectionEffect,
    lm1_lane_effect_from_influence,
    lm1_remaining_area_effect_from_influence,
)
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem


@dataclass(frozen=True)
class ProjectContinuousLM1SectionInput:
    ei_kn_m2_by_span: tuple[float, ...]
    response_span_index: int
    response_position_m: float
    response_kind: InfluenceResponseKind
    lane_distributions: tuple[LaneGirderDistribution, ...]
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None
    factors: LM1AdjustmentFactors | None = None
    influence_positions: int = 801
    movement_steps: int = 1201

    def __post_init__(self) -> None:
        if not self.ei_kn_m2_by_span:
            raise ValueError("At least one span EI is required.")
        if any(value <= 0.0 for value in self.ei_kn_m2_by_span):
            raise ValueError("All span EI values must be positive.")
        if self.response_span_index < 0:
            raise ValueError("response_span_index cannot be negative.")
        if self.response_position_m < 0.0:
            raise ValueError("response_position_m cannot be negative.")
        if self.response_kind not in ("moment", "shear"):
            raise ValueError("response_kind must be 'moment' or 'shear'.")
        if not self.lane_distributions:
            raise ValueError("Validated/imported lane distributions are required.")
        if self.influence_positions < 2:
            raise ValueError("At least two influence-line positions are required.")
        if self.movement_steps < 2:
            raise ValueError("At least two tandem movement steps are required.")


@dataclass(frozen=True)
class ProjectContinuousLM1SectionResult:
    lane_layout: NotionalLaneLayout
    lane_effects: tuple[LM1ContinuousSectionEffect, ...]
    remaining_area_effect: AdverseUDLEffect | None
    girder_effects: tuple[AggregatedGirderSectionEffect, ...]
    traffic_distribution_method: str
    status: str

    def effect_for_girder(self, girder_index: int) -> AggregatedGirderSectionEffect:
        for effect in self.girder_effects:
            if effect.girder_index == girder_index:
                return effect
        raise IndexError(f"Girder {girder_index} is not present in the LM1 section result.")


def run_project_continuous_lm1_section(
    project: ProjectInput,
    input_data: ProjectContinuousLM1SectionInput,
) -> ProjectContinuousLM1SectionResult:
    """Evaluate characteristic LM1 effects at one continuous-bridge section.

    Longitudinal tandem and adverse UDL effects are generated from one numerical
    influence line. Supplied transverse lane/remaining-area fractions then map
    those effects to physical girders. This workflow intentionally refuses to
    invent equal-share factors or section stiffness.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Continuous LM1 workflow requires a Eurocode project.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous LM1 workflow requires a CONTINUOUS project.")

    span_lengths = tuple(float(value) for value in project.geometry.span_lengths_m)
    if len(span_lengths) < 2:
        raise ValueError("Continuous LM1 workflow requires at least two spans.")
    if len(input_data.ei_kn_m2_by_span) != len(span_lengths):
        raise ValueError("EI vector must match the project span count.")
    if not 0 <= input_data.response_span_index < len(span_lengths):
        raise IndexError("response_span_index is outside the project span list.")
    if input_data.response_position_m > span_lengths[input_data.response_span_index]:
        raise ValueError("response_position_m lies outside the target span.")

    layout = notional_lane_layout(float(project.geometry.carriageway_width_m))
    expected_lanes = set(range(1, layout.lane_count + 1))
    supplied_lanes = {item.lane_number for item in input_data.lane_distributions}
    if supplied_lanes != expected_lanes:
        raise ValueError(
            "Lane distributions must cover every LM1 notional lane exactly once: "
            f"expected {sorted(expected_lanes)}, got {sorted(supplied_lanes)}."
        )

    girder_count = int(project.geometry.girder_count)
    if any(item.girder_count != girder_count for item in input_data.lane_distributions):
        raise ValueError("Lane distribution girder count does not match the project.")
    if layout.remaining_width_m > 0.0 and input_data.remaining_area_distribution is None:
        raise ValueError(
            "A remaining-area distribution is required because the carriageway has residual width."
        )
    if (
        input_data.remaining_area_distribution is not None
        and input_data.remaining_area_distribution.girder_count != girder_count
    ):
        raise ValueError("Remaining-area distribution girder count does not match the project.")

    spans = tuple(
        BeamSpan(length_m=length, ei_kn_m2=input_data.ei_kn_m2_by_span[index])
        for index, length in enumerate(span_lengths)
    )
    influence = section_influence_line(
        spans,
        response_span_index=input_data.response_span_index,
        response_position_m=input_data.response_position_m,
        response_kind=input_data.response_kind,
        load_positions=input_data.influence_positions,
    )

    by_lane = {item.lane_number: item for item in input_data.lane_distributions}
    lane_effects = tuple(
        lm1_lane_effect_from_influence(
            influence,
            lane_number=lane_number,
            lane_width_m=layout.lane_width_m,
            factors=input_data.factors,
            movement_steps=input_data.movement_steps,
        )
        for lane_number in sorted(by_lane)
    )

    remaining_effect = None
    if layout.remaining_width_m > 0.0:
        remaining_effect = lm1_remaining_area_effect_from_influence(
            influence,
            remaining_width_m=layout.remaining_width_m,
            factors=input_data.factors,
        )

    girder_effects = tuple(
        aggregate_lm1_continuous_section_effects(
            list(lane_effects),
            list(input_data.lane_distributions),
            remaining_area_effect=remaining_effect,
            remaining_area_distribution=input_data.remaining_area_distribution,
        )
    )
    method = girder_effects[0].method
    return ProjectContinuousLM1SectionResult(
        lane_layout=layout,
        lane_effects=lane_effects,
        remaining_area_effect=remaining_effect,
        girder_effects=girder_effects,
        traffic_distribution_method=method,
        status=(
            "Continuous EN 1991-2 LM1 characteristic section effects generated from one "
            "longitudinal influence line and mapped using supplied transverse distributions"
        ),
    )


def continuous_lm1_girder_combinations(
    result: ProjectContinuousLM1SectionResult,
    *,
    girder_index: int,
    permanent_characteristic_effect: float,
    sls_factors: ServiceabilityPsiFactors,
    uls_factors: EurocodeFactors | None = None,
) -> SignedSectionCombinationSet:
    """Build signed ULS/SLS branches for one girder at the analysed section.

    ``permanent_characteristic_effect`` must be the signed longitudinal effect at
    the same section and for the same response kind as ``result``. Keeping it
    explicit prevents this traffic workflow from inventing a composite/cracked EI
    or silently mixing effects from different longitudinal locations.
    """
    traffic = result.effect_for_girder(girder_index)
    envelope = SignedSectionEnvelope(
        maximum_positive_effect=traffic.maximum_positive_effect,
        minimum_negative_effect=traffic.minimum_negative_effect,
        response_kind=traffic.response_kind,
    )
    return signed_section_combinations(
        permanent_characteristic_effect=permanent_characteristic_effect,
        traffic_characteristic=envelope,
        sls_factors=sls_factors,
        uls_factors=uls_factors,
    )
