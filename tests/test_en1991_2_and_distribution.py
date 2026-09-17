import pytest

from rc_bridge.analysis.transverse import apply_distribution, equal_distribution, normalize_distribution
from rc_bridge.codes.eurocode.en1991_2 import (
    lm1_characteristic_lane_load,
    lm1_remaining_area_udl_kn_m2,
    notional_lane_layout,
)


def test_11m_carriageway_has_three_lanes_and_two_metre_remainder() -> None:
    layout = notional_lane_layout(11.0)
    assert layout.lane_count == 3
    assert layout.lane_width_m == pytest.approx(3.0)
    assert layout.remaining_width_m == pytest.approx(2.0)


def test_lane_layout_transition_regions() -> None:
    a = notional_lane_layout(5.0)
    assert a.lane_count == 1
    assert a.remaining_width_m == pytest.approx(2.0)

    b = notional_lane_layout(5.6)
    assert b.lane_count == 2
    assert b.lane_width_m == pytest.approx(2.8)
    assert b.remaining_width_m == pytest.approx(0.0)


def test_lm1_basic_characteristic_values() -> None:
    lane1 = lm1_characteristic_lane_load(1)
    lane2 = lm1_characteristic_lane_load(2)
    lane3 = lm1_characteristic_lane_load(3)
    lane4 = lm1_characteristic_lane_load(4)

    assert (lane1.axle_load_kn, lane1.udl_kn_m2) == pytest.approx((300.0, 9.0))
    assert (lane2.axle_load_kn, lane2.udl_kn_m2) == pytest.approx((200.0, 2.5))
    assert (lane3.axle_load_kn, lane3.udl_kn_m2) == pytest.approx((100.0, 2.5))
    assert (lane4.axle_load_kn, lane4.udl_kn_m2) == pytest.approx((0.0, 2.5))
    assert lm1_remaining_area_udl_kn_m2() == pytest.approx(2.5)


def test_distribution_normalization_and_application() -> None:
    normalized = normalize_distribution([1.0, 2.0, 1.0])
    assert [x.fraction for x in normalized] == pytest.approx([0.25, 0.50, 0.25])
    assert apply_distribution(1000.0, normalized) == pytest.approx([250.0, 500.0, 250.0])

    baseline = equal_distribution(4)
    assert sum(x.fraction for x in baseline) == pytest.approx(1.0)
