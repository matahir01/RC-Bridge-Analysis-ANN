import pytest

from rc_bridge.codes.bs5400.traffic_effects import (
    governing_hb_simple_span_envelope,
    ha_carriageway_simple_span_envelopes_bd37_01,
    ha_simple_span_lane_envelope_bd37_01,
    hb_simple_span_envelope,
)


def test_reference_15m_ha_lane_simple_span_effects() -> None:
    result = ha_simple_span_lane_envelope_bd37_01(
        span_m=15.0,
        carriageway_width_m=7.0,
        lane_number=1,
    )
    assert result.lane_load.lane_factor == pytest.approx(0.959)
    assert result.effects.moment_knm == pytest.approx(1908.171787431)
    assert result.effects.shear_kn == pytest.approx(508.845809982)
    assert result.max_moment_position_m == pytest.approx(7.5)


def test_reference_7m_carriageway_returns_two_ha_lane_envelopes() -> None:
    envelopes = ha_carriageway_simple_span_envelopes_bd37_01(
        span_m=15.0,
        carriageway_width_m=7.0,
    )
    assert len(envelopes) == 2
    assert envelopes[0].effects.moment_knm == pytest.approx(
        envelopes[1].effects.moment_knm
    )


def test_30_unit_hb_6m_spacing_moves_across_15m_span() -> None:
    result = hb_simple_span_envelope(
        span_m=15.0,
        units=30.0,
        inner_axle_spacing_m=6.0,
    )
    assert result.effects.moment_knm == pytest.approx(2337.876, abs=0.01)
    assert result.effects.shear_kn == pytest.approx(814.84, abs=0.02)
    assert result.max_moment_position_m == pytest.approx(9.1125, abs=0.02)


def test_30_unit_hb_6m_spacing_governs_15m_sagging_moment() -> None:
    result = governing_hb_simple_span_envelope(
        span_m=15.0,
        units=30.0,
    )
    assert result.governing_inner_axle_spacing_m == pytest.approx(6.0)
    assert result.effects.moment_knm == pytest.approx(2337.876, abs=0.01)
