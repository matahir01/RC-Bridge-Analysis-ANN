import pytest

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.codes.eurocode.lm1_continuous import (
    lm1_carriageway_continuous_section_effect,
    lm1_lane_continuous_section_effect,
)


def test_simple_span_lm1_lane_midspan_uses_full_positive_udl_region() -> None:
    spans = (BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),)
    result = lm1_lane_continuous_section_effect(
        spans,
        response_span_index=0,
        response_position_m=5.0,
        lane_number=1,
        lane_width_m=3.0,
        response_kind="moment",
        influence_positions=101,
        movement_steps=101,
    )

    assert result.udl_line_load_kn_m == pytest.approx(27.0)
    assert result.udl_effect.maximum_positive_effect == pytest.approx(337.5, rel=1e-12)
    assert result.udl_effect.minimum_negative_effect == pytest.approx(0.0, abs=1e-12)
    assert result.tandem_effect.maximum_positive_effect > 0.0
    assert result.tandem_effect.minimum_negative_effect == pytest.approx(0.0, abs=1e-12)
    assert result.maximum_positive_effect == pytest.approx(
        result.tandem_effect.maximum_positive_effect
        + result.udl_effect.maximum_positive_effect
    )


def test_two_span_internal_support_lm1_is_hogging_and_keeps_remaining_area() -> None:
    spans = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
    )
    result = lm1_carriageway_continuous_section_effect(
        spans,
        carriageway_width_m=7.0,
        response_span_index=0,
        response_position_m=10.0,
        response_kind="moment",
        influence_positions=201,
        movement_steps=201,
    )

    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.lane_width_m == pytest.approx(3.0)
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)
    assert tuple(item.udl_line_load_kn_m for item in result.lane_effects) == pytest.approx(
        (27.0, 7.5)
    )
    assert result.remaining_area_effect.line_load_kn_m == pytest.approx(2.5)

    assert result.summed_adverse_positive_effect == pytest.approx(0.0, abs=1e-8)
    assert result.summed_adverse_negative_effect < 0.0
    assert all(item.minimum_negative_effect < 0.0 for item in result.lane_effects)
    assert result.remaining_area_effect.minimum_negative_effect < 0.0
    assert result.summed_adverse_negative_effect == pytest.approx(
        sum(item.minimum_negative_effect for item in result.lane_effects)
        + result.remaining_area_effect.minimum_negative_effect
    )


def test_two_span_midspan_lm1_separates_positive_and_negative_influence_regions() -> None:
    spans = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
    )
    result = lm1_carriageway_continuous_section_effect(
        spans,
        carriageway_width_m=7.0,
        response_span_index=0,
        response_position_m=5.0,
        response_kind="moment",
        influence_positions=201,
        movement_steps=201,
    )

    assert result.summed_adverse_positive_effect > 0.0
    assert result.summed_adverse_negative_effect < 0.0
    assert all(item.udl_effect.positive_loaded_length_m > 0.0 for item in result.lane_effects)
    assert all(item.udl_effect.negative_loaded_length_m > 0.0 for item in result.lane_effects)
