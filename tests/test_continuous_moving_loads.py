import pytest

from rc_bridge.analysis.continuous_beam import BeamSpan
from rc_bridge.analysis.continuous_moving_loads import moving_train_continuous_envelope
from rc_bridge.analysis.moving_loads import AxleTrain, moving_train_max_moment


def test_single_span_moving_axle_matches_closed_form_and_simple_solver() -> None:
    length = 10.0
    point = 100.0
    ei = 1.0e6
    span = BeamSpan(length_m=length, ei_kn_m2=ei)
    train = AxleTrain(axle_loads_kn=(point,), axle_offsets_m=(0.0,), label="100 kN axle")

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
        length,
        train,
        movement_steps=101,
        section_stations=101,
    )
    assert envelope.max_sagging_moment_knm == pytest.approx(simple_moment)
    assert envelope.max_sagging_position_m == pytest.approx(simple_section)
    assert envelope.max_sagging_lead_position_m == pytest.approx(simple_lead)

    expected_deflection = point * length**3 / (48.0 * ei)
    assert envelope.minimum_downward_displacement_m == pytest.approx(
        -expected_deflection,
        rel=1e-12,
    )
    assert envelope.minimum_downward_displacement_position_m == pytest.approx(5.0)
    assert envelope.minimum_downward_displacement_lead_position_m == pytest.approx(5.0)
    assert envelope.max_abs_displacement_m == pytest.approx(expected_deflection, rel=1e-12)
    assert envelope.max_abs_displacement_position_m == pytest.approx(5.0)
    assert envelope.max_abs_displacement_lead_position_m == pytest.approx(5.0)
    assert result.max_abs_displacement_m == pytest.approx(expected_deflection, rel=1e-12)
    assert result.max_abs_displacement_span_index == 0
    assert result.max_abs_displacement_global_position_m == pytest.approx(5.0)
    assert result.max_abs_displacement_lead_position_m == pytest.approx(5.0)

    assert result.support_envelopes[0].max_vertical_reaction_kn == pytest.approx(point)
    assert result.support_envelopes[1].max_vertical_reaction_kn == pytest.approx(point)


def test_two_equal_spans_produce_symmetric_sagging_hogging_reactions_and_deflection() -> None:
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
    assert left.max_abs_displacement_m > 0.0
    assert left.max_abs_displacement_m == pytest.approx(
        right.max_abs_displacement_m,
        rel=1e-10,
    )
    assert left.minimum_downward_displacement_m == pytest.approx(
        right.minimum_downward_displacement_m,
        rel=1e-10,
    )
    assert left.maximum_upward_displacement_m > 0.0
    assert left.maximum_upward_displacement_m == pytest.approx(
        right.maximum_upward_displacement_m,
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
