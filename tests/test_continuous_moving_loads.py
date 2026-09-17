import pytest

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.analysis.continuous_moving_loads import moving_train_continuous_envelope
from rc_bridge.analysis.moving_loads import AxleTrain, moving_train_max_moment


def test_single_span_moving_axle_matches_closed_form_and_simple_solver() -> None:
    span = BeamSpan(length_m=10.0, ei_kn_m2=1.0e6)
    train = AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,), label="100 kN axle")

    result = moving_train_continuous_envelope(
        (span,),
        train,
        movement_steps=101,
        section_stations=101,
    )
    envelope = result.span_envelopes[0]

    assert envelope.max_sagging_moment_knm == pytest.approx(250.0, rel=1e-12)
    assert envelope.max_sagging_position_m == pytest.approx(5.0)
    assert envelope.max_sagging_lead_position_m == pytest.approx(5.0)

    simple_moment, simple_section, simple_lead = moving_train_max_moment(
        10.0,
        train,
        movement_steps=101,
        section_stations=101,
    )
    assert envelope.max_sagging_moment_knm == pytest.approx(simple_moment)
    assert envelope.max_sagging_position_m == pytest.approx(simple_section)
    assert envelope.max_sagging_lead_position_m == pytest.approx(simple_lead)

    assert result.support_envelopes[0].max_vertical_reaction_kn == pytest.approx(100.0)
    assert result.support_envelopes[1].max_vertical_reaction_kn == pytest.approx(100.0)


def test_two_equal_spans_produce_symmetric_sagging_hogging_and_reactions() -> None:
    spans = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
    )
    train = AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,))

    result = moving_train_continuous_envelope(
        spans,
        train,
        movement_steps=81,
        section_stations=81,
    )
    left, right = result.span_envelopes

    assert left.max_sagging_moment_knm > 0.0
    assert left.min_hogging_moment_knm < 0.0
    assert left.max_sagging_moment_knm == pytest.approx(
        right.max_sagging_moment_knm,
        rel=1e-10,
    )
    assert left.min_hogging_moment_knm == pytest.approx(
        right.min_hogging_moment_knm,
        rel=1e-10,
    )

    supports = result.support_envelopes
    assert supports[0].max_vertical_reaction_kn == pytest.approx(
        supports[2].max_vertical_reaction_kn,
        rel=1e-10,
    )
    assert supports[0].min_vertical_reaction_kn < 0.0
    assert supports[0].min_vertical_reaction_kn == pytest.approx(
        supports[2].min_vertical_reaction_kn,
        rel=1e-10,
    )
    assert supports[1].min_vertical_reaction_kn == pytest.approx(0.0, abs=1e-12)


def test_moving_envelope_validates_resolution() -> None:
    span = BeamSpan(length_m=10.0, ei_kn_m2=1.0e6)
    train = AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,))

    with pytest.raises(ValueError, match="movement steps"):
        moving_train_continuous_envelope((span,), train, movement_steps=1)
    with pytest.raises(ValueError, match="section stations"):
        moving_train_continuous_envelope((span,), train, section_stations=1)
