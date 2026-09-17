import pytest

from rc_bridge.analysis.continuous_beam import BeamSpan, SpanPointLoad, solve_continuous_beam
from rc_bridge.analysis.continuous_deflection import (
    member_section_displacement,
    member_span_deflection_envelope,
)


def test_simple_span_udl_midspan_deflection_matches_closed_form() -> None:
    length = 10.0
    udl = 20.0
    ei = 1.0e6
    span = BeamSpan(length_m=length, ei_kn_m2=ei, udl_kn_m=udl)
    solution = solve_continuous_beam((span,))

    midspan = member_section_displacement(
        span,
        solution.members[0],
        solution.nodes[0],
        length / 2.0,
    )
    expected = -5.0 * udl * length**4 / (384.0 * ei)
    assert midspan.vertical_displacement_m == pytest.approx(expected, rel=1e-12)
    assert midspan.rotation_rad == pytest.approx(0.0, abs=1e-12)

    right = member_section_displacement(
        span,
        solution.members[0],
        solution.nodes[0],
        length,
    )
    assert right.vertical_displacement_m == pytest.approx(
        solution.nodes[1].vertical_displacement_m,
        abs=1e-12,
    )
    assert right.rotation_rad == pytest.approx(solution.nodes[1].rotation_rad, rel=1e-12)


def test_simple_span_central_point_load_deflection_matches_closed_form() -> None:
    length = 10.0
    point = 100.0
    ei = 1.0e6
    span = BeamSpan(
        length_m=length,
        ei_kn_m2=ei,
        point_loads=(SpanPointLoad(point, length / 2.0),),
    )
    solution = solve_continuous_beam((span,))

    midspan = member_section_displacement(
        span,
        solution.members[0],
        solution.nodes[0],
        length / 2.0,
    )
    expected = -point * length**3 / (48.0 * ei)
    assert midspan.vertical_displacement_m == pytest.approx(expected, rel=1e-12)
    assert midspan.rotation_rad == pytest.approx(0.0, abs=1e-12)

    right = member_section_displacement(
        span,
        solution.members[0],
        solution.nodes[0],
        length,
    )
    assert right.vertical_displacement_m == pytest.approx(0.0, abs=1e-12)
    assert right.rotation_rad == pytest.approx(solution.nodes[1].rotation_rad, rel=1e-12)


def test_deflection_envelope_finds_simple_span_udl_midspan() -> None:
    span = BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0)
    solution = solve_continuous_beam((span,))
    envelope = member_span_deflection_envelope(
        span,
        solution.members[0],
        solution.nodes[0],
        stations=401,
    )

    expected = 5.0 * 20.0 * 10.0**4 / (384.0 * 1.0e6)
    assert envelope.minimum_downward_position_m == pytest.approx(5.0)
    assert envelope.minimum_downward_displacement_m == pytest.approx(-expected, rel=1e-12)
    assert envelope.max_abs_displacement_m == pytest.approx(expected, rel=1e-12)
    assert envelope.max_abs_position_m == pytest.approx(5.0)


def test_two_span_deflection_recovery_is_continuous_at_internal_support() -> None:
    spans = (
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
        BeamSpan(length_m=10.0, ei_kn_m2=1.0e6, udl_kn_m=20.0),
    )
    solution = solve_continuous_beam(spans)

    first_right = member_section_displacement(
        spans[0],
        solution.members[0],
        solution.nodes[0],
        spans[0].length_m,
    )
    second_left = member_section_displacement(
        spans[1],
        solution.members[1],
        solution.nodes[1],
        0.0,
    )
    first_mid = member_section_displacement(
        spans[0],
        solution.members[0],
        solution.nodes[0],
        spans[0].length_m / 2.0,
    )
    second_mid = member_section_displacement(
        spans[1],
        solution.members[1],
        solution.nodes[1],
        spans[1].length_m / 2.0,
    )

    assert first_right.vertical_displacement_m == pytest.approx(0.0, abs=1e-12)
    assert second_left.vertical_displacement_m == pytest.approx(0.0, abs=1e-12)
    assert first_right.rotation_rad == pytest.approx(second_left.rotation_rad, abs=1e-12)
    assert first_mid.vertical_displacement_m == pytest.approx(
        second_mid.vertical_displacement_m,
        rel=1e-12,
    )
