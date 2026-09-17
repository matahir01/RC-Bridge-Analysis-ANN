from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rc_bridge.analysis.moving_loads import AxleTrain


class BS5400TrafficProfile(str, Enum):
    """Explicit highway-loading profile used by the legacy BS 5400 mode."""

    BS5400_1978 = "bs5400_part2_1978"
    BD37_01_2001 = "bd37_01_2001_composite"


@dataclass(frozen=True)
class BS5400NotionalLaneLayout:
    carriageway_width_m: float
    lane_count: int
    lane_width_m: float
    remaining_width_m: float


@dataclass(frozen=True)
class HALaneLoad:
    lane_number: int
    lane_factor: float
    udl_kn_m: float
    kel_kn: float
    loaded_length_m: float
    traffic_profile: BS5400TrafficProfile


@dataclass(frozen=True)
class HBVehicleDefinition:
    units: float
    inner_axle_spacing_m: float
    axle_load_kn: float
    total_vehicle_load_kn: float
    overall_length_m: float
    train: AxleTrain


def notional_lane_layout_bd37_01(carriageway_width_m: float) -> BS5400NotionalLaneLayout:
    """Return BD 37/01 notional-lane subdivision for one carriageway.

    This first implementation covers carriageway widths from 2.5 m to 21.9 m.
    For widths below 5 m a single 2.5 m notional lane is used and the remaining
    carriageway width is reported separately. Widths of 5 m and above are split
    into the equal-width lane counts tabulated by BD 37/01.
    """
    w = float(carriageway_width_m)
    if w < 2.5:
        raise ValueError("Carriageway width below 2.5 m is outside this BD 37/01 implementation.")
    if w < 5.0:
        return BS5400NotionalLaneLayout(w, 1, 2.5, max(w - 2.5, 0.0))

    limits = (
        (7.50, 2),
        (10.95, 3),
        (14.60, 4),
        (18.25, 5),
        (21.90, 6),
    )
    for upper, count in limits:
        if w <= upper:
            return BS5400NotionalLaneLayout(w, count, w / count, 0.0)

    raise ValueError(
        "Carriageway widths above 21.90 m require an extended notional-lane rule set."
    )


def ha_udl_kn_m(
    loaded_length_m: float,
    *,
    traffic_profile: BS5400TrafficProfile = BS5400TrafficProfile.BD37_01_2001,
) -> float:
    """Return nominal Type HA UDL per linear metre of notional lane.

    Two profiles are kept explicit because the original 1978 curve and the
    later BD 37/01 composite curve are not the same.
    """
    length = float(loaded_length_m)
    if length <= 0.0:
        raise ValueError("loaded_length_m must be positive.")

    if traffic_profile == BS5400TrafficProfile.BS5400_1978:
        if length <= 30.0:
            return 30.0
        return max(151.0 * length ** (-0.475), 9.0)

    if traffic_profile == BS5400TrafficProfile.BD37_01_2001:
        if length <= 50.0:
            return 336.0 * length ** (-0.67)
        if length <= 1600.0:
            return 36.0 * length ** (-0.10)
        raise ValueError(
            "BD 37/01 HA UDL for loaded lengths above 1600 m requires authority agreement."
        )

    raise ValueError(f"Unsupported BS 5400 traffic profile: {traffic_profile}")


def ha_kel_kn() -> float:
    """Nominal Type HA knife-edge load per notional lane."""
    return 120.0


def ha_lane_factor_bd37_01(
    *,
    lane_number: int,
    loaded_length_m: float,
    lane_width_m: float,
    total_notional_lanes: int,
) -> float:
    """Return the BD 37/01 HA lane factor for one notional lane."""
    if lane_number < 1 or total_notional_lanes < 1:
        raise ValueError("Lane numbers and lane count must be positive.")
    if lane_number > total_notional_lanes:
        raise ValueError("lane_number cannot exceed total_notional_lanes.")
    if loaded_length_m <= 0.0 or lane_width_m <= 0.0:
        raise ValueError("Loaded length and lane width must be positive.")

    length = float(loaded_length_m)
    alpha1 = min(0.274 * lane_width_m, 1.0)
    alpha2 = 0.0137 * (
        lane_width_m * (40.0 - length) + 3.65 * (length - 20.0)
    )

    if length <= 20.0:
        if lane_number in (1, 2):
            return alpha1
        if lane_number == 3:
            return 0.60
        return 0.60 * alpha1

    if length <= 40.0:
        if lane_number in (1, 2):
            return alpha2
        if lane_number == 3:
            return 0.60
        return 0.60 * alpha2

    if length <= 50.0:
        return 1.0 if lane_number in (1, 2) else 0.60

    if length <= 112.0:
        if lane_number == 1:
            return 1.0
        if lane_number == 2:
            return 1.0 if total_notional_lanes >= 6 else 7.1 / length**0.5
        return 0.60

    if lane_number == 1:
        return 1.0
    if lane_number == 2:
        return 1.0 if total_notional_lanes >= 6 else 0.67
    return 0.60


def ha_lane_load_bd37_01(
    *,
    lane_number: int,
    loaded_length_m: float,
    lane_width_m: float,
    total_notional_lanes: int,
) -> HALaneLoad:
    factor = ha_lane_factor_bd37_01(
        lane_number=lane_number,
        loaded_length_m=loaded_length_m,
        lane_width_m=lane_width_m,
        total_notional_lanes=total_notional_lanes,
    )
    return HALaneLoad(
        lane_number=lane_number,
        lane_factor=factor,
        udl_kn_m=ha_udl_kn_m(
            loaded_length_m,
            traffic_profile=BS5400TrafficProfile.BD37_01_2001,
        )
        * factor,
        kel_kn=ha_kel_kn() * factor,
        loaded_length_m=loaded_length_m,
        traffic_profile=BS5400TrafficProfile.BD37_01_2001,
    )


def hb_vehicle_train(
    *,
    units: float,
    inner_axle_spacing_m: float,
) -> HBVehicleDefinition:
    """Build the longitudinal four-axle nominal Type HB vehicle.

    One HB unit is 10 kN per axle. The two outer axle spacings are 1.8 m and
    the permitted inner spacing is 6, 11, 16, 21 or 26 m, giving overall
    vehicle lengths of 10, 15, 20, 25 or 30 m respectively.

    Project/authority requirements determine the number of HB units. This
    implementation accepts up to 45 units and does not silently choose a
    project minimum.
    """
    if units <= 0.0 or units > 45.0:
        raise ValueError("HB units must be greater than zero and no more than 45.")
    allowed = (6.0, 11.0, 16.0, 21.0, 26.0)
    if inner_axle_spacing_m not in allowed:
        raise ValueError(f"HB inner axle spacing must be one of {allowed} m.")

    axle_load_kn = 10.0 * units
    offsets = (
        0.0,
        1.8,
        1.8 + inner_axle_spacing_m,
        3.6 + inner_axle_spacing_m,
    )
    train = AxleTrain(
        axle_loads_kn=(axle_load_kn,) * 4,
        axle_offsets_m=offsets,
        label=f"BS 5400 Type HB {units:g}-unit",
    )
    return HBVehicleDefinition(
        units=units,
        inner_axle_spacing_m=inner_axle_spacing_m,
        axle_load_kn=axle_load_kn,
        total_vehicle_load_kn=4.0 * axle_load_kn,
        overall_length_m=inner_axle_spacing_m + 3.6,
        train=train,
    )
