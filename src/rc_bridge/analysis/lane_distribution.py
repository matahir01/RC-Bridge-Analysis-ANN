from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.eurocode.lm1_effects import LM1Envelope


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
        if not self.moment_fractions or not self.shear_fractions:
            raise ValueError("Moment and shear distributions cannot be empty.")
        if len(self.moment_fractions) != len(self.shear_fractions):
            raise ValueError("Moment and shear distributions must have equal girder counts.")
        if any(value < 0 for value in self.moment_fractions + self.shear_fractions):
            raise ValueError("Distribution fractions cannot be negative.")
        if abs(sum(self.moment_fractions) - 1.0) > 1e-9:
            raise ValueError("Moment distribution fractions must sum to 1.0.")
        if abs(sum(self.shear_fractions) - 1.0) > 1e-9:
            raise ValueError("Shear distribution fractions must sum to 1.0.")

    @property
    def girder_count(self) -> int:
        return len(self.moment_fractions)


@dataclass(frozen=True)
class AggregatedGirderTrafficEffect:
    girder_index: int
    moment_knm: float
    shear_kn: float
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


def aggregate_lm1_lane_envelopes(
    envelopes: list[LM1Envelope],
    distributions: list[LaneGirderDistribution],
) -> list[AggregatedGirderTrafficEffect]:
    """Map lane-wise LM1 envelopes to girders using lane-specific factors.

    The routine superposes each lane's independently optimized positive moment
    and absolute shear envelope. This is a conservative lane-envelope
    aggregation, not a substitute for simultaneous grillage moving-load
    optimization. Production use should supply validated grillage/distribution
    results and retain that method identifier in the calculation trace.
    """
    if not envelopes:
        raise ValueError("At least one LM1 lane envelope is required.")
    if not distributions:
        raise ValueError("Lane distribution factors are required.")

    by_lane = {item.lane_number: item for item in distributions}
    if len(by_lane) != len(distributions):
        raise ValueError("Duplicate lane distribution definitions are not allowed.")

    first = distributions[0]
    girder_count = first.girder_count
    if any(item.girder_count != girder_count for item in distributions):
        raise ValueError("All lane distributions must use the same girder count.")

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
