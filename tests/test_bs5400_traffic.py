import pytest

from rc_bridge.codes.bs5400.traffic import (
    BS5400TrafficProfile,
    ha_kel_kn,
    ha_lane_factor_bd37_01,
    ha_lane_load_bd37_01,
    ha_udl_kn_m,
    hb_vehicle_train,
    notional_lane_layout_bd37_01,
)


def test_reference_7m_carriageway_has_two_equal_bd37_lanes() -> None:
    layout = notional_lane_layout_bd37_01(7.0)
    assert layout.lane_count == 2
    assert layout.lane_width_m == pytest.approx(3.5)
    assert layout.remaining_width_m == pytest.approx(0.0)


def test_bd37_ha_udl_for_15m_loaded_length() -> None:
    udl = ha_udl_kn_m(
        15.0,
        traffic_profile=BS5400TrafficProfile.BD37_01_2001,
    )
    assert udl == pytest.approx(54.7467236679)
    assert ha_kel_kn() == pytest.approx(120.0)


def test_original_1978_ha_curve_is_kept_separate() -> None:
    assert ha_udl_kn_m(
        15.0,
        traffic_profile=BS5400TrafficProfile.BS5400_1978,
    ) == pytest.approx(30.0)
    assert ha_udl_kn_m(
        40.0,
        traffic_profile=BS5400TrafficProfile.BS5400_1978,
    ) == pytest.approx(151.0 * 40.0 ** (-0.475))


def test_reference_15m_lane_factors_are_0959_for_both_lanes() -> None:
    layout = notional_lane_layout_bd37_01(7.0)
    for lane_number in (1, 2):
        factor = ha_lane_factor_bd37_01(
            lane_number=lane_number,
            loaded_length_m=15.0,
            lane_width_m=layout.lane_width_m,
            total_notional_lanes=layout.lane_count,
        )
        assert factor == pytest.approx(0.959)

    lane = ha_lane_load_bd37_01(
        lane_number=1,
        loaded_length_m=15.0,
        lane_width_m=layout.lane_width_m,
        total_notional_lanes=layout.lane_count,
    )
    assert lane.udl_kn_m == pytest.approx(52.5021079976)
    assert lane.kel_kn == pytest.approx(115.08)


def test_30_unit_hb_vehicle_has_four_300kn_axles() -> None:
    vehicle = hb_vehicle_train(units=30.0, inner_axle_spacing_m=6.0)
    assert vehicle.axle_load_kn == pytest.approx(300.0)
    assert vehicle.total_vehicle_load_kn == pytest.approx(1200.0)
    assert vehicle.overall_length_m == pytest.approx(10.0)
    assert vehicle.train.axle_loads_kn == pytest.approx((300.0, 300.0, 300.0, 300.0))
    assert vehicle.train.axle_offsets_m == pytest.approx((0.0, 1.8, 7.8, 9.6))
    assert vehicle.train.train_length_m == pytest.approx(9.6)


def test_hb_vehicle_rejects_nonstandard_inner_spacing() -> None:
    with pytest.raises(ValueError, match="inner axle spacing"):
        hb_vehicle_train(units=30.0, inner_axle_spacing_m=8.0)
