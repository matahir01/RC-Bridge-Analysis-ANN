import pytest

from rc_bridge.analysis.lane_distribution import equal_lane_distribution
from rc_bridge.workflow.bs5400_bridge_traffic import (
    run_simple_span_ha_bridge_traffic_bd37_01,
)


def test_reference_ha_equal_share_distribution_conserves_bridge_effects() -> None:
    distributions = [
        equal_lane_distribution(lane_number, 7)
        for lane_number in (1, 2)
    ]
    result = run_simple_span_ha_bridge_traffic_bd37_01(
        span_m=15.0,
        carriageway_width_m=7.0,
        lane_distributions=distributions,
    )

    assert result.lane_layout.lane_count == 2
    assert len(result.girder_effects) == 7
    total_lane_moment = sum(item.effects.moment_knm for item in result.lane_envelopes)
    total_lane_shear = sum(item.effects.shear_kn for item in result.lane_envelopes)
    assert sum(item.moment_knm for item in result.girder_effects) == pytest.approx(
        total_lane_moment
    )
    assert sum(item.shear_kn for item in result.girder_effects) == pytest.approx(
        total_lane_shear
    )
    assert all(
        "equal_share_verification_only" in item.method
        for item in result.girder_effects
    )


def test_reference_internal_girder_equal_share_ha_effects() -> None:
    result = run_simple_span_ha_bridge_traffic_bd37_01(
        span_m=15.0,
        carriageway_width_m=7.0,
        lane_distributions=[
            equal_lane_distribution(1, 7),
            equal_lane_distribution(2, 7),
        ],
    )
    girder4 = result.girder_effects[3]
    assert girder4.moment_knm == pytest.approx(545.191939266)
    assert girder4.shear_kn == pytest.approx(145.384517138)
