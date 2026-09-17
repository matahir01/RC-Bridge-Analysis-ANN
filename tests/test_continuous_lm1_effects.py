import pytest

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.analysis.continuous_influence import (
    moving_train_influence_effect,
    section_influence_line,
)
from rc_bridge.analysis.moving_loads import AxleTrain
from rc_bridge.codes.eurocode.lm1_effects import lm1_lane_continuous_section_effect


def test_single_axle_influence_envelope_matches_simple_span_midspan() -> None:
    span = BeamSpan(length_m=15.0, ei_kn_m2=1.0e6)
    influence = section_influence_line(
        (span,),
        response_span_index=0,
        response_position_m=7.5,
        response_kind="moment",
        load_positions=301,
    )
    result = moving_train_influence_effect(
        influence,
        AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,), label="100 kN axle"),
        movement_steps=301,
    )

    assert result.maximum_positive_effect == pytest.approx(375.0, rel=1e-10)
    assert result.maximum_positive_lead_position_m == pytest.approx(7.5, abs=1e-10)
    assert result.minimum_negative_effect == pytest.approx(0.0, abs=1e-10)


def test_lm1_lane_one_midspan_matches_closed_form_components() -> None:
    span = BeamSpan(length_m=15.0, ei_kn_m2=1.0e6)
    result = lm1_lane_continuous_section_effect(
        (span,),
        lane_number=1,
        response_span_index=0,
        response_position_m=7.5,
        response_kind="moment",
        lane_width_m=3.0,
        influence_positions=1501,
        movement_steps=1621,
    )

    # Lane 1 UDL = 9 kN/m2 x 3 m = 27 kN/m; Mmid = wL2/8.
    assert result.udl_maximum_positive_effect == pytest.approx(759.375, rel=2e-5)
    # Two 300 kN axles at 1.2 m spacing govern symmetrically about midspan.
    assert result.tandem_maximum_positive_effect == pytest.approx(2070.0, rel=2e-5)
    assert result.combined_maximum_positive_effect == pytest.approx(2829.375, rel=2e-5)
    assert result.combined_minimum_negative_effect == pytest.approx(0.0, abs=1e-8)


def test_two_span_internal_support_has_negative_lm1_moment_effect() -> None:
    spans = (
        BeamSpan(length_m=15.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=15.0, ei_kn_m2=1.0e6),
    )
    result = lm1_lane_continuous_section_effect(
        spans,
        lane_number=1,
        response_span_index=0,
        response_position_m=15.0,
        response_kind="moment",
        lane_width_m=3.0,
        influence_positions=301,
        movement_steps=401,
    )

    assert result.combined_minimum_negative_effect < 0.0
    assert result.tandem_minimum_negative_effect < 0.0
    assert result.udl_minimum_negative_effect < 0.0
