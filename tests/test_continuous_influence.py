import pytest

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    member_section_response,
    solve_continuous_beam,
)
from rc_bridge.analysis.continuous_influence import adverse_udl_effect, section_influence_line


def test_simple_span_midspan_moment_influence_matches_closed_form_udl_effect() -> None:
    spans = (BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),)
    line = section_influence_line(
        spans,
        response_span_index=0,
        response_position_m=5.0,
        response_kind="moment",
        load_positions=101,
    )

    assert max(line.ordinates) == pytest.approx(2.5, rel=1e-12)
    effect = adverse_udl_effect(line, line_load_kn_m=20.0)
    assert effect.maximum_positive_effect == pytest.approx(250.0, rel=1e-12)
    assert effect.minimum_negative_effect == pytest.approx(0.0, abs=1e-12)
    assert effect.full_length_effect == pytest.approx(250.0, rel=1e-12)
    assert effect.positive_loaded_length_m == pytest.approx(10.0)
    assert effect.negative_loaded_length_m == pytest.approx(0.0)


def test_two_span_internal_support_influence_reproduces_full_udl_hogging() -> None:
    geometry = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
    )
    line = section_influence_line(
        geometry,
        response_span_index=0,
        response_position_m=10.0,
        response_kind="moment",
        load_positions=801,
    )
    effect = adverse_udl_effect(line, line_load_kn_m=20.0)

    loaded = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
    )
    solution = solve_continuous_beam(loaded)
    direct = member_section_response(loaded[0], solution.members[0], 10.0)

    assert effect.maximum_positive_effect == pytest.approx(0.0, abs=1e-9)
    assert effect.minimum_negative_effect < 0.0
    assert effect.full_length_effect == pytest.approx(direct.moment_knm, rel=2e-5)
    assert effect.full_length_effect == pytest.approx(-250.0, rel=2e-5)


def test_adverse_udl_excludes_remote_negative_influence_for_span_sagging() -> None:
    geometry = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6),
    )
    line = section_influence_line(
        geometry,
        response_span_index=0,
        response_position_m=5.0,
        response_kind="moment",
        load_positions=801,
    )
    effect = adverse_udl_effect(line, line_load_kn_m=20.0)

    loaded = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
    )
    solution = solve_continuous_beam(loaded)
    direct = member_section_response(loaded[0], solution.members[0], 5.0)

    assert effect.positive_loaded_length_m > 0.0
    assert effect.negative_loaded_length_m > 0.0
    assert effect.maximum_positive_effect > effect.full_length_effect
    assert effect.minimum_negative_effect < 0.0
    assert effect.full_length_effect == pytest.approx(direct.moment_knm, rel=2e-5)
