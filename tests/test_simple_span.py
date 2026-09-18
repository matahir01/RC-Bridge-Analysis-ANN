import pytest

from rc_bridge.analysis.simple_span import (
    DistributedLoadSegment,
    simple_span_distributed_load_response,
    udl_simple_span,
)


def test_udl_simple_span():
    result = udl_simple_span(span_m=10.0, udl_kn_m=20.0)
    assert result.reaction_left_kn == 100.0
    assert result.reaction_right_kn == 100.0
    assert result.max_moment_knm == 250.0
    assert result.max_shear_kn == 100.0


def test_symmetric_partial_udl_has_exact_reactions_and_moment_extreme() -> None:
    result = simple_span_distributed_load_response(
        10.0,
        (DistributedLoadSegment(4.0, 2.0, 8.0),),
    )

    assert result.reaction_left_kn == pytest.approx(12.0)
    assert result.reaction_right_kn == pytest.approx(12.0)
    assert result.max_moment_knm == pytest.approx(42.0)
    assert result.max_moment_position_m == pytest.approx(5.0)
    assert result.max_abs_shear_kn == pytest.approx(12.0)


def test_eccentric_partial_udl_finds_zero_shear_without_station_scan() -> None:
    result = simple_span_distributed_load_response(
        10.0,
        (DistributedLoadSegment(2.0, 0.0, 4.0),),
        evaluation_stations_m=(1.0, 9.0),
    )

    assert result.reaction_left_kn == pytest.approx(6.4)
    assert result.reaction_right_kn == pytest.approx(1.6)
    assert result.max_moment_position_m == pytest.approx(3.2)
    assert result.max_moment_knm == pytest.approx(10.24)
    assert result.max_abs_shear_kn == pytest.approx(6.4)
