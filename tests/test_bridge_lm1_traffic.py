import pytest

from rc_bridge.analysis.lane_distribution import (
    equal_lane_distribution,
    equal_remaining_area_distribution,
)
from rc_bridge.codes.eurocode.lm1_effects import lm1_remaining_area_simple_span_envelope
from rc_bridge.workflow.eurocode_bridge_traffic import run_simple_span_lm1_bridge_traffic


def test_7m_carriageway_remaining_area_effects() -> None:
    result = lm1_remaining_area_simple_span_envelope(
        span_m=15.0,
        carriageway_width_m=7.0,
    )
    assert result.remaining_width_m == pytest.approx(1.0)
    assert result.udl_kn_m2 == pytest.approx(2.5)
    assert result.line_load_kn_m == pytest.approx(2.5)
    assert result.max_moment_knm == pytest.approx(70.3125)
    assert result.max_abs_shear_kn == pytest.approx(18.75)


def test_7m_bridge_workflow_requires_remaining_area_distribution() -> None:
    lane_distributions = [
        equal_lane_distribution(1, 7),
        equal_lane_distribution(2, 7),
    ]
    with pytest.raises(ValueError, match="remaining carriageway area"):
        run_simple_span_lm1_bridge_traffic(
            span_m=15.0,
            carriageway_width_m=7.0,
            lane_distributions=lane_distributions,
            movement_steps=11,
            section_stations=21,
        )


def test_7m_bridge_workflow_conserves_lane_and_remaining_area_effects() -> None:
    lane_distributions = [
        equal_lane_distribution(1, 7),
        equal_lane_distribution(2, 7),
    ]
    result = run_simple_span_lm1_bridge_traffic(
        span_m=15.0,
        carriageway_width_m=7.0,
        lane_distributions=lane_distributions,
        remaining_area_distribution=equal_remaining_area_distribution(7),
        movement_steps=21,
        section_stations=31,
    )

    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.lane_width_m == pytest.approx(3.0)
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)

    total_lane_moment = sum(item.max_moment_knm for item in result.lane_envelopes)
    total_lane_shear = sum(item.max_abs_shear_kn for item in result.lane_envelopes)
    expected_moment = total_lane_moment + result.remaining_area_envelope.max_moment_knm
    expected_shear = total_lane_shear + result.remaining_area_envelope.max_abs_shear_kn

    assert sum(item.moment_knm for item in result.girder_effects) == pytest.approx(
        expected_moment
    )
    assert sum(item.shear_kn for item in result.girder_effects) == pytest.approx(
        expected_shear
    )
