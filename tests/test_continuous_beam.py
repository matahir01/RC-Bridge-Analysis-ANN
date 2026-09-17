import pytest

from rc_bridge.analysis.continuous_beam import (
    BeamSpan,
    SpanPointLoad,
    ei_kn_m2_from_mpa_mm4,
    member_section_response,
    member_span_envelope,
    solve_continuous_beam,
)


def test_ei_conversion_from_mpa_mm4() -> None:
    assert ei_kn_m2_from_mpa_mm4(30000.0, 2.5e11) == pytest.approx(7.5e6)


def test_single_simple_span_udl_matches_closed_form_reactions_and_moment() -> None:
    length = 10.0
    udl = 20.0
    ei = 1.0e6
    span = BeamSpan(length_m=length, ei_kn_m2=ei, udl_kn_m=udl)
    result = solve_continuous_beam((span,))

    assert result.nodes[0].vertical_reaction_kn == pytest.approx(udl * length / 2.0)
    assert result.nodes[1].vertical_reaction_kn == pytest.approx(udl * length / 2.0)
    assert result.members[0].left_moment_knm == pytest.approx(0.0, abs=1e-10)
    assert result.members[0].right_moment_knm == pytest.approx(0.0, abs=1e-10)

    midspan = member_section_response(span, result.members[0], length / 2.0)
    assert midspan.moment_knm == pytest.approx(udl * length**2 / 8.0)

    expected_rotation = udl * length**3 / (24.0 * ei)
    assert result.nodes[0].rotation_rad == pytest.approx(-expected_rotation)
    assert result.nodes[1].rotation_rad == pytest.approx(expected_rotation)


def test_single_simple_span_central_point_load_matches_closed_form() -> None:
    length = 10.0
    point = 100.0
    ei = 1.0e6
    span = BeamSpan(
        length_m=length,
        ei_kn_m2=ei,
        point_loads=(SpanPointLoad(point, length / 2.0),),
    )
    result = solve_continuous_beam((span,))
    envelope = member_span_envelope(span, result.members[0], stations=101)

    assert result.nodes[0].vertical_reaction_kn == pytest.approx(point / 2.0)
    assert result.nodes[1].vertical_reaction_kn == pytest.approx(point / 2.0)
    assert envelope.max_sagging_moment_knm == pytest.approx(point * length / 4.0)
    assert envelope.max_sagging_position_m == pytest.approx(length / 2.0)
    expected_rotation = point * length**2 / (16.0 * ei)
    assert result.nodes[0].rotation_rad == pytest.approx(-expected_rotation)
    assert result.nodes[1].rotation_rad == pytest.approx(expected_rotation)


def test_two_equal_spans_udl_matches_classical_continuous_beam_solution() -> None:
    length = 10.0
    udl = 20.0
    ei = 1.0e6
    spans = (
        BeamSpan(length_m=length, ei_kn_m2=ei, udl_kn_m=udl),
        BeamSpan(length_m=length, ei_kn_m2=ei, udl_kn_m=udl),
    )
    result = solve_continuous_beam(spans)

    expected_outer_reaction = 3.0 * udl * length / 8.0
    expected_central_reaction = 5.0 * udl * length / 4.0
    expected_support_moment = -udl * length**2 / 8.0

    assert result.nodes[0].vertical_reaction_kn == pytest.approx(expected_outer_reaction)
    assert result.nodes[1].vertical_reaction_kn == pytest.approx(expected_central_reaction)
    assert result.nodes[2].vertical_reaction_kn == pytest.approx(expected_outer_reaction)
    assert sum(node.vertical_reaction_kn for node in result.nodes) == pytest.approx(
        2.0 * udl * length
    )

    assert result.members[0].right_moment_knm == pytest.approx(expected_support_moment)
    assert result.members[1].left_moment_knm == pytest.approx(expected_support_moment)
    assert result.nodes[1].rotation_rad == pytest.approx(0.0, abs=1e-12)

    first = member_span_envelope(spans[0], result.members[0], stations=401)
    second = member_span_envelope(spans[1], result.members[1], stations=401)
    expected_sagging = 140.625
    assert first.max_sagging_moment_knm == pytest.approx(expected_sagging, rel=1e-4)
    assert second.max_sagging_moment_knm == pytest.approx(expected_sagging, rel=1e-4)
    assert first.min_hogging_moment_knm == pytest.approx(expected_support_moment)
    assert second.min_hogging_moment_knm == pytest.approx(expected_support_moment)


def test_under_restrained_beam_is_rejected_as_singular() -> None:
    span = BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=10.0)
    with pytest.raises(ValueError, match="singular"):
        solve_continuous_beam((span,), vertical_support_nodes=(0,))
