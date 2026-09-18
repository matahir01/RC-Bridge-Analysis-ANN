from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise


@dataclass(frozen=True)
class SimpleSpanResult:
    reaction_left_kn: float
    reaction_right_kn: float
    max_moment_knm: float
    max_shear_kn: float


@dataclass(frozen=True)
class DistributedLoadSegment:
    """Constant downward line load over a bounded part of a simple span."""

    magnitude_kn_m: float
    start_m: float
    end_m: float
    label: str = "distributed load"
    stage: str = "unspecified"

    def __post_init__(self) -> None:
        if self.magnitude_kn_m < 0.0:
            raise ValueError("Distributed-load magnitude cannot be negative.")
        if self.start_m < 0.0 or self.end_m <= self.start_m:
            raise ValueError("Distributed-load bounds must define a positive length.")
        if not self.label.strip():
            raise ValueError("Distributed-load label cannot be empty.")

    @property
    def total_load_kn(self) -> float:
        return self.magnitude_kn_m * (self.end_m - self.start_m)

    @property
    def centroid_m(self) -> float:
        return 0.5 * (self.start_m + self.end_m)


@dataclass(frozen=True)
class SimpleSpanDistributedResult:
    reaction_left_kn: float
    reaction_right_kn: float
    max_moment_knm: float
    max_moment_position_m: float
    max_abs_shear_kn: float
    max_abs_shear_position_m: float
    stations_m: tuple[float, ...]
    moments_knm: tuple[float, ...]
    shears_kn: tuple[float, ...]


def udl_simple_span(span_m: float, udl_kn_m: float) -> SimpleSpanResult:
    """Closed-form simply supported beam response to a full-span UDL."""
    if span_m <= 0:
        raise ValueError("span_m must be greater than zero")
    if udl_kn_m < 0:
        raise ValueError("udl_kn_m cannot be negative")

    reaction = udl_kn_m * span_m / 2.0
    return SimpleSpanResult(
        reaction_left_kn=reaction,
        reaction_right_kn=reaction,
        max_moment_knm=udl_kn_m * span_m**2 / 8.0,
        max_shear_kn=reaction,
    )


def _validate_distributed_loads(
    span_m: float,
    loads: Sequence[DistributedLoadSegment],
) -> None:
    if span_m <= 0.0:
        raise ValueError("span_m must be greater than zero")
    if any(load.end_m > span_m + 1.0e-9 for load in loads):
        raise ValueError("Distributed load extends beyond the simple span.")


def simple_span_distributed_reactions(
    span_m: float,
    loads: Sequence[DistributedLoadSegment],
) -> tuple[float, float]:
    """Return exact reactions for arbitrary piecewise-uniform downward loads."""
    _validate_distributed_loads(span_m, loads)
    total = sum(load.total_load_kn for load in loads)
    reaction_right = sum(
        load.total_load_kn * load.centroid_m for load in loads
    ) / span_m
    return total - reaction_right, reaction_right


def simple_span_distributed_response_at_x(
    span_m: float,
    loads: Sequence[DistributedLoadSegment],
    x_m: float,
) -> tuple[float, float]:
    """Return sagging-positive moment and upward-left-face shear at ``x_m``."""
    _validate_distributed_loads(span_m, loads)
    if not 0.0 <= x_m <= span_m:
        raise ValueError("Response coordinate lies outside the simple span.")
    reaction_left, _ = simple_span_distributed_reactions(span_m, loads)
    shear = reaction_left
    moment = reaction_left * x_m
    for load in loads:
        loaded_length = min(max(x_m - load.start_m, 0.0), load.end_m - load.start_m)
        if loaded_length <= 0.0:
            continue
        shear -= load.magnitude_kn_m * loaded_length
        loaded_centroid = load.start_m + loaded_length / 2.0
        moment -= load.magnitude_kn_m * loaded_length * (x_m - loaded_centroid)
    return moment, shear


def simple_span_distributed_load_response(
    span_m: float,
    loads: Sequence[DistributedLoadSegment],
    *,
    evaluation_stations_m: Sequence[float] = (),
) -> SimpleSpanDistributedResult:
    """Return exact extrema and an auditable response field for segmented UDLs.

    Candidate stations contain every load boundary and each zero-shear point,
    so the maximum sagging moment is not dependent on a numerical scan density.
    Optional reporting stations are added without changing the extrema logic.
    """
    _validate_distributed_loads(span_m, loads)
    stations = {0.0, span_m}
    for load in loads:
        stations.update((load.start_m, min(load.end_m, span_m)))

    boundaries = sorted(stations)
    reaction_left, reaction_right = simple_span_distributed_reactions(span_m, loads)
    for left, right in pairwise(boundaries):
        midpoint = 0.5 * (left + right)
        intensity = sum(
            load.magnitude_kn_m
            for load in loads
            if load.start_m <= midpoint < load.end_m
        )
        if intensity <= 0.0:
            continue
        _, shear_left = simple_span_distributed_response_at_x(span_m, loads, left)
        root = left + shear_left / intensity
        if left < root < right:
            stations.add(root)

    for station in evaluation_stations_m:
        value = float(station)
        if not 0.0 <= value <= span_m:
            raise ValueError("Evaluation station lies outside the simple span.")
        stations.add(value)

    ordered = tuple(sorted(stations))
    responses = tuple(
        simple_span_distributed_response_at_x(span_m, loads, x_m)
        for x_m in ordered
    )
    moments = tuple(item[0] for item in responses)
    shears = tuple(item[1] for item in responses)
    moment_index = max(range(len(ordered)), key=lambda index: moments[index])
    shear_index = max(range(len(ordered)), key=lambda index: abs(shears[index]))
    # Include the right reaction explicitly in the shear envelope; the internal
    # left-face value at x=L equals -R_right for downward loading.
    max_abs_shear = max(abs(shears[shear_index]), abs(reaction_left), abs(reaction_right))
    if abs(reaction_right) > abs(shears[shear_index]):
        shear_position = span_m
    elif abs(reaction_left) > abs(shears[shear_index]):
        shear_position = 0.0
    else:
        shear_position = ordered[shear_index]
    return SimpleSpanDistributedResult(
        reaction_left_kn=reaction_left,
        reaction_right_kn=reaction_right,
        max_moment_knm=moments[moment_index],
        max_moment_position_m=ordered[moment_index],
        max_abs_shear_kn=max_abs_shear,
        max_abs_shear_position_m=shear_position,
        stations_m=ordered,
        moments_knm=moments,
        shears_kn=shears,
    )
