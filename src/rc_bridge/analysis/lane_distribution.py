from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.continuous_influence import AdverseUDLEffect
from rc_bridge.codes.eurocode.lm1_effects import (
    LM1ContinuousSectionEffect,
    LM1Envelope,
    LM1RemainingAreaEnvelope,
)


def _validate_fractions(
    moment_fractions: tuple[float, ...],
    shear_fractions: tuple[float, ...],
) -> None:
    if not moment_fractions or not shear_fractions:
        raise ValueError("Moment and shear distributions cannot be empty.")
    if len(moment_fractions) != len(shear_fractions):
        raise ValueError("Moment and shear distributions must have equal girder counts.")
    if any(value < 0 for value in moment_fractions + shear_fractions):
        raise ValueError("Distribution fractions cannot be negative.")
    if abs(sum(moment_fractions) - 1.0) > 1e-9:
        raise ValueError("Moment distribution fractions must sum to 1.0.")
    if abs(sum(shear_fractions) - 1.0) > 1e-9:
        raise ValueError("Shear distribution fractions must sum to 1.0.")


@dataclass(frozen=True)
class LaneGirderDistribution:
    """Lane-specific transverse fractions for girder moment and shear effects.

    The factors are intentionally external to the longitudinal LM1 solver so
    they may come from a grillage model, a validated analytical distribution
    method, or an explicitly labelled verification baseline.
    """

    lane_number: int
    moment_fractions: tuple[float, ...]
    shear_fractions: tuple[float, ...]
    method: str = "imported_or_validated_distribution"

    def __post_init__(self) -> None:
        if self.lane_number <= 0:
            raise ValueError("lane_number must be positive.")
        _validate_fractions(self.moment_fractions, self.shear_fractions)

    @property
    def girder_count(self) -> int:
        return len(self.moment_fractions)


@dataclass(frozen=True)
class RemainingAreaGirderDistribution:
    """Transverse fractions for the LM1 carriageway area outside notional lanes."""

    moment_fractions: tuple[float, ...]
    shear_fractions: tuple[float, ...]
    method: str = "imported_or_validated_remaining_area_distribution"

    def __post_init__(self) -> None:
        _validate_fractions(self.moment_fractions, self.shear_fractions)

    @property
    def girder_count(self) -> int:
        return len(self.moment_fractions)


@dataclass(frozen=True)
class AggregatedGirderTrafficEffect:
    girder_index: int
    moment_knm: float
    shear_kn: float
    method: str


@dataclass(frozen=True)
class AggregatedGirderSectionEffect:
    girder_index: int
    response_kind: str
    response_span_index: int
    response_position_m: float
    maximum_positive_effect: float
    minimum_negative_effect: float
    method: str


def equal_lane_distribution(
    lane_number: int,
    girder_count: int,
) -> LaneGirderDistribution:
    """Equal-share distribution for mechanics verification only."""
    if girder_count <= 0:
        raise ValueError("girder_count must be positive.")
    fraction = 1.0 / girder_count
    values = tuple(fraction for _ in range(girder_count))
    return LaneGirderDistribution(
        lane_number=lane_number,
        moment_fractions=values,
        shear_fractions=values,
        method="equal_share_verification_only",
    )


def equal_remaining_area_distribution(girder_count: int) -> RemainingAreaGirderDistribution:
    """Equal-share remaining-area distribution for mechanics verification only."""
    if girder_count <= 0:
        raise ValueError("girder_count must be positive.")
    fraction = 1.0 / girder_count
    values = tuple(fraction for _ in range(girder_count))
    return RemainingAreaGirderDistribution(
        moment_fractions=values,
        shear_fractions=values,
        method="equal_share_remaining_area_verification_only",
    )


def aggregate_lm1_lane_envelopes(
    envelopes: list[LM1Envelope],
    distributions: list[LaneGirderDistribution],
    remaining_area_envelope: LM1RemainingAreaEnvelope | None = None,
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None,
) -> list[AggregatedGirderTrafficEffect]:
    """Map lane-wise LM1 envelopes and remaining-area UDL to individual girders.

    Lane envelopes are independently optimized positive-moment and absolute-
    shear envelopes. This is conservative envelope aggregation, not a substitute
    for simultaneous grillage moving-load optimization. Production use should
    supply validated grillage/distribution factors and retain their method IDs.
    """
    if not envelopes:
        raise ValueError("At least one LM1 lane envelope is required.")
    if not distributions:
        raise ValueError("Lane distribution factors are required.")
    if (remaining_area_envelope is None) != (remaining_area_distribution is None):
        raise ValueError(
            "Remaining-area envelope and distribution must either both be supplied or both omitted."
        )

    by_lane = {item.lane_number: item for item in distributions}
    if len(by_lane) != len(distributions):
        raise ValueError("Duplicate lane distribution definitions are not allowed.")

    first = distributions[0]
    girder_count = first.girder_count
    if any(item.girder_count != girder_count for item in distributions):
        raise ValueError("All lane distributions must use the same girder count.")
    if (
        remaining_area_distribution is not None
        and remaining_area_distribution.girder_count != girder_count
    ):
        raise ValueError("Remaining-area distribution must use the same girder count as lane distributions.")

    moments = [0.0] * girder_count
    shears = [0.0] * girder_count
    methods: set[str] = set()

    for envelope in envelopes:
        distribution = by_lane.get(envelope.lane_number)
        if distribution is None:
            raise ValueError(f"Missing distribution for LM1 lane {envelope.lane_number}.")
        methods.add(distribution.method)
        for index in range(girder_count):
            moments[index] += envelope.max_moment_knm * distribution.moment_fractions[index]
            shears[index] += envelope.max_abs_shear_kn * distribution.shear_fractions[index]

    if remaining_area_envelope is not None and remaining_area_distribution is not None:
        methods.add(remaining_area_distribution.method)
        for index in range(girder_count):
            moments[index] += (
                remaining_area_envelope.max_moment_knm
                * remaining_area_distribution.moment_fractions[index]
            )
            shears[index] += (
                remaining_area_envelope.max_abs_shear_kn
                * remaining_area_distribution.shear_fractions[index]
            )

    method_label = "+".join(sorted(methods))
    return [
        AggregatedGirderTrafficEffect(
            girder_index=index + 1,
            moment_knm=moments[index],
            shear_kn=shears[index],
            method=method_label,
        )
        for index in range(girder_count)
    ]


def aggregate_lm1_continuous_section_effects(
    effects: list[LM1ContinuousSectionEffect],
    distributions: list[LaneGirderDistribution],
    *,
    remaining_area_effect: AdverseUDLEffect | None = None,
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None,
) -> list[AggregatedGirderSectionEffect]:
    """Distribute continuous-span LM1 section envelopes to physical girders.

    All supplied lane effects must refer to the same longitudinal response
    section and response kind. Moment effects use ``moment_fractions`` while
    shear effects use ``shear_fractions``. Positive and negative envelopes are
    retained separately so support hogging/uplift-sensitive cases are not lost.
    """
    if not effects:
        raise ValueError("At least one continuous LM1 lane effect is required.")
    if not distributions:
        raise ValueError("Lane distribution factors are required.")
    if (remaining_area_effect is None) != (remaining_area_distribution is None):
        raise ValueError(
            "Remaining-area effect and distribution must either both be supplied or both omitted."
        )

    first_effect = effects[0]
    response_kind = first_effect.response_kind
    response_span_index = first_effect.response_span_index
    response_position_m = first_effect.response_position_m
    if any(
        effect.response_kind != response_kind
        or effect.response_span_index != response_span_index
        or abs(effect.response_position_m - response_position_m) > 1e-9
        for effect in effects
    ):
        raise ValueError("Continuous LM1 effects must refer to one common response section.")

    effect_lanes = [effect.lane_number for effect in effects]
    if len(set(effect_lanes)) != len(effect_lanes):
        raise ValueError("Duplicate continuous LM1 lane effects are not allowed.")

    by_lane = {item.lane_number: item for item in distributions}
    if len(by_lane) != len(distributions):
        raise ValueError("Duplicate lane distribution definitions are not allowed.")

    girder_count = distributions[0].girder_count
    if any(item.girder_count != girder_count for item in distributions):
        raise ValueError("All lane distributions must use the same girder count.")
    if (
        remaining_area_distribution is not None
        and remaining_area_distribution.girder_count != girder_count
    ):
        raise ValueError("Remaining-area distribution must use the same girder count as lane distributions.")

    positive = [0.0] * girder_count
    negative = [0.0] * girder_count
    methods: set[str] = set()

    for effect in effects:
        distribution = by_lane.get(effect.lane_number)
        if distribution is None:
            raise ValueError(f"Missing distribution for LM1 lane {effect.lane_number}.")
        methods.add(distribution.method)
        fractions = (
            distribution.moment_fractions
            if response_kind == "moment"
            else distribution.shear_fractions
        )
        for index, fraction in enumerate(fractions):
            positive[index] += effect.combined_maximum_positive_effect * fraction
            negative[index] += effect.combined_minimum_negative_effect * fraction

    if remaining_area_effect is not None and remaining_area_distribution is not None:
        methods.add(remaining_area_distribution.method)
        fractions = (
            remaining_area_distribution.moment_fractions
            if response_kind == "moment"
            else remaining_area_distribution.shear_fractions
        )
        for index, fraction in enumerate(fractions):
            positive[index] += remaining_area_effect.maximum_positive_effect * fraction
            negative[index] += remaining_area_effect.minimum_negative_effect * fraction

    method_label = "+".join(sorted(methods))
    return [
        AggregatedGirderSectionEffect(
            girder_index=index + 1,
            response_kind=response_kind,
            response_span_index=response_span_index,
            response_position_m=response_position_m,
            maximum_positive_effect=positive[index],
            minimum_negative_effect=negative[index],
            method=method_label,
        )
        for index in range(girder_count)
    ]
