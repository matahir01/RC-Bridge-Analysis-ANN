from __future__ import annotations

from dataclasses import dataclass
from math import floor

from rc_bridge.analysis.moving_loads import AxleTrain


@dataclass(frozen=True)
class NotionalLaneLayout:
    carriageway_width_m: float
    lane_count: int
    lane_width_m: float
    remaining_width_m: float


@dataclass(frozen=True)
class LM1LaneLoad:
    lane_number: int
    axle_load_kn: float
    udl_kn_m2: float


@dataclass(frozen=True)
class LM1AdjustmentFactors:
    """National/project adjustment factors for EN 1991-2 Load Model 1.

    Defaults of 1.0 are the recommended/basic values used in the JRC worked
    examples when no project-specific values are supplied. National Annex or
    project-specific values must be checked before design use.
    """

    alpha_q1: float = 1.0
    alpha_q2: float = 1.0
    alpha_q3: float = 1.0
    alpha_q_other: float = 1.0
    alpha_q_remaining: float = 1.0
    alpha_Q1: float = 1.0
    alpha_Q2: float = 1.0
    alpha_Q3: float = 1.0


def notional_lane_layout(carriageway_width_m: float) -> NotionalLaneLayout:
    """Return EN 1991-2 notional-lane subdivision for road traffic models.

    First-generation EN 1991-2 rules implemented here:
      * w < 5.4 m: one 3 m notional lane, remaining area w - 3 m
      * 5.4 <= w < 6.0 m: two equal lanes of w / 2, no remaining area
      * w >= 6.0 m: int(w / 3) lanes of 3 m, remainder w - 3*n
    """
    w = float(carriageway_width_m)
    if w < 3.0:
        raise ValueError("Carriageway width must be at least 3.0 m.")

    if w < 5.4:
        return NotionalLaneLayout(w, 1, 3.0, w - 3.0)
    if w < 6.0:
        return NotionalLaneLayout(w, 2, w / 2.0, 0.0)

    count = floor(w / 3.0)
    return NotionalLaneLayout(w, count, 3.0, w - 3.0 * count)


def lm1_characteristic_lane_load(
    lane_number: int,
    factors: LM1AdjustmentFactors | None = None,
) -> LM1LaneLoad:
    """Characteristic EN 1991-2 LM1 values for a numbered notional lane.

    Q values are per axle. A tandem system consists of two axles at 1.2 m
    longitudinal spacing. UDL values are area pressures over the relevant
    notional lane.
    """
    if lane_number < 1:
        raise ValueError("Lane number must be 1 or greater.")
    f = factors or LM1AdjustmentFactors()

    if lane_number == 1:
        return LM1LaneLoad(1, 300.0 * f.alpha_Q1, 9.0 * f.alpha_q1)
    if lane_number == 2:
        return LM1LaneLoad(2, 200.0 * f.alpha_Q2, 2.5 * f.alpha_q2)
    if lane_number == 3:
        return LM1LaneLoad(3, 100.0 * f.alpha_Q3, 2.5 * f.alpha_q3)
    return LM1LaneLoad(lane_number, 0.0, 2.5 * f.alpha_q_other)


def lm1_tandem_train(
    lane_number: int,
    factors: LM1AdjustmentFactors | None = None,
) -> AxleTrain:
    """Build the longitudinal two-axle LM1 tandem for a notional lane."""
    lane = lm1_characteristic_lane_load(lane_number, factors)
    return AxleTrain(
        axle_loads_kn=(lane.axle_load_kn, lane.axle_load_kn),
        axle_offsets_m=(0.0, 1.2),
        label=f"EN 1991-2 LM1 lane {lane_number}",
    )


def lm1_remaining_area_udl_kn_m2(
    factors: LM1AdjustmentFactors | None = None,
) -> float:
    f = factors or LM1AdjustmentFactors()
    return 2.5 * f.alpha_q_remaining


def lm1_tandem_axle_spacing_m() -> float:
    return 1.2
