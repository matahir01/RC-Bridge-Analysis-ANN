from __future__ import annotations

from dataclasses import dataclass

from .loads import PointLoad
from .point_loads import moment_envelope, simply_supported_reactions


@dataclass(frozen=True)
class AxleTrain:
    axle_loads_kn: tuple[float, ...]
    axle_offsets_m: tuple[float, ...]
    label: str = "Axle train"

    def __post_init__(self) -> None:
        if len(self.axle_loads_kn) == 0:
            raise ValueError("At least one axle is required.")
        if len(self.axle_loads_kn) != len(self.axle_offsets_m):
            raise ValueError("Axle loads and offsets must have equal lengths.")
        if any(p < 0 for p in self.axle_loads_kn):
            raise ValueError("Axle loads cannot be negative.")
        if any(x < 0 for x in self.axle_offsets_m):
            raise ValueError("Axle offsets cannot be negative.")

    @property
    def train_length_m(self) -> float:
        return max(self.axle_offsets_m)


def positioned_axles(train: AxleTrain, lead_position_m: float, span_m: float) -> list[PointLoad]:
    """Place axle train on span, discarding axles that are off the bridge."""
    loads: list[PointLoad] = []
    for i, (magnitude, offset) in enumerate(zip(train.axle_loads_kn, train.axle_offsets_m)):
        x = lead_position_m - offset
        if 0.0 <= x <= span_m:
            loads.append(PointLoad(magnitude, x, f"{train.label} axle {i + 1}"))
    return loads


def moving_train_max_moment(
    span_m: float,
    train: AxleTrain,
    movement_steps: int = 601,
    section_stations: int = 401,
) -> tuple[float, float, float]:
    """Numerically move an axle train and return max moment, section x and lead x.

    This general mechanical routine does not encode any traffic design code.
    Eurocode LM1/LM2 and BS 5400 vehicle definitions are constructed in their
    respective code modules and passed into this solver.
    """
    if span_m <= 0:
        raise ValueError("Span must be positive.")
    if movement_steps < 2:
        raise ValueError("At least two movement steps are required.")

    start = 0.0
    end = span_m + train.train_length_m
    best_m = 0.0
    best_section = 0.0
    best_lead = 0.0

    for i in range(movement_steps):
        lead = start + (end - start) * i / (movement_steps - 1)
        loads = positioned_axles(train, lead, span_m)
        if not loads:
            continue
        m, x = moment_envelope(span_m, loads, stations=section_stations)
        if m > best_m:
            best_m = m
            best_section = x
            best_lead = lead
    return best_m, best_section, best_lead


def moving_train_max_support_reaction(
    span_m: float,
    train: AxleTrain,
    movement_steps: int = 1201,
) -> tuple[float, str, float]:
    """Numerically return the largest support reaction from a moving axle train.

    For a simply supported beam this is the support-shear envelope immediately
    inside the bearing. The returned tuple is ``(reaction_kN, side, lead_x_m)``.
    """
    if span_m <= 0.0:
        raise ValueError("Span must be positive.")
    if movement_steps < 2:
        raise ValueError("At least two movement steps are required.")

    start = 0.0
    end = span_m + train.train_length_m
    best_reaction = 0.0
    best_side = "left"
    best_lead = 0.0

    for i in range(movement_steps):
        lead = start + (end - start) * i / (movement_steps - 1)
        loads = positioned_axles(train, lead, span_m)
        if not loads:
            continue
        left, right = simply_supported_reactions(span_m, loads)
        if left > best_reaction:
            best_reaction = left
            best_side = "left"
            best_lead = lead
        if right > best_reaction:
            best_reaction = right
            best_side = "right"
            best_lead = lead

    return best_reaction, best_side, best_lead
