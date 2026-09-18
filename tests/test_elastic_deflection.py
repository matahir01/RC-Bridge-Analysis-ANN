from math import sqrt

import pytest

from rc_bridge.analysis.elastic_deflection import (
    simply_supported_deflection_at_x_mm,
    simply_supported_deflection_from_moment_diagram_mm,
    simply_supported_midspan_deflection_mm,
)
from rc_bridge.analysis.loads import PointLoad


def test_midspan_udl_deflection_matches_closed_form() -> None:
    span_m = 15.0
    udl_kn_m = 25.0
    elastic_modulus_mpa = 32000.0
    second_moment_mm4 = 2.5e11

    numerical = simply_supported_midspan_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=elastic_modulus_mpa,
        second_moment_mm4=second_moment_mm4,
        udl_kn_m=udl_kn_m,
    )
    span_mm = span_m * 1000.0
    exact = 5.0 * udl_kn_m * span_mm**4 / (
        384.0 * elastic_modulus_mpa * second_moment_mm4
    )
    assert numerical == pytest.approx(exact, rel=1e-9)


def test_midspan_central_point_load_deflection_matches_closed_form() -> None:
    span_m = 15.0
    point_kn = 300.0
    elastic_modulus_mpa = 32000.0
    second_moment_mm4 = 2.5e11

    numerical = simply_supported_midspan_deflection_mm(
        span_m=span_m,
        elastic_modulus_mpa=elastic_modulus_mpa,
        second_moment_mm4=second_moment_mm4,
        point_loads=(PointLoad(point_kn, span_m / 2.0),),
    )
    span_mm = span_m * 1000.0
    exact = point_kn * 1000.0 * span_mm**3 / (
        48.0 * elastic_modulus_mpa * second_moment_mm4
    )
    assert numerical == pytest.approx(exact, rel=1e-9)


def test_deflection_integrator_accepts_combined_loading() -> None:
    result = simply_supported_midspan_deflection_mm(
        span_m=15.0,
        elastic_modulus_mpa=32000.0,
        second_moment_mm4=2.5e11,
        udl_kn_m=20.0,
        point_loads=(PointLoad(120.0, 7.5),),
    )
    assert result > 0.0


def test_deflection_integrator_requires_even_segment_count() -> None:
    with pytest.raises(ValueError, match="even integer"):
        simply_supported_midspan_deflection_mm(
            span_m=15.0,
            elastic_modulus_mpa=32000.0,
            second_moment_mm4=2.5e11,
            udl_kn_m=20.0,
            integration_segments=999,
        )


def test_moment_diagram_curvature_integration_matches_central_point_load() -> None:
    result = simply_supported_deflection_from_moment_diagram_mm(
        stations_m=(0.0, 5.0, 10.0),
        moments_knm=(0.0, 250.0, 0.0),
        elastic_modulus_mpa=30_000.0,
        second_moment_mm4=8.0e9,
    )

    expected = 100_000.0 * 10_000.0**3 / (48.0 * 30_000.0 * 8.0e9)
    assert result.maximum_absolute_deflection_mm == pytest.approx(expected)
    assert result.maximum_position_m == pytest.approx(5.0)
    assert result.station_deflections_mm[0] == pytest.approx(0.0)
    assert result.station_deflections_mm[-1] == pytest.approx(0.0)



def test_moment_diagram_deflection_finds_interior_peak_between_stations() -> None:
    span_m = 10.0
    point_kn = 100.0
    load_position_m = 4.0
    elastic_modulus_mpa = 30_000.0
    second_moment_mm4 = 8.0e9

    # Exact bending-moment diagram for a single point load at x=4 m:
    # R_A = 60 kN, so M(4 m) = 240 kNm. The maximum displacement occurs
    # inside the 4-10 m segment rather than at a supplied moment station.
    result = simply_supported_deflection_from_moment_diagram_mm(
        stations_m=(0.0, load_position_m, span_m),
        moments_knm=(0.0, 240.0, 0.0),
        elastic_modulus_mpa=elastic_modulus_mpa,
        second_moment_mm4=second_moment_mm4,
    )

    expected_position_m = span_m - sqrt(
        (span_m**2 - load_position_m**2) / 3.0
    )
    expected_deflection_mm = simply_supported_deflection_at_x_mm(
        span_m=span_m,
        target_x_m=expected_position_m,
        elastic_modulus_mpa=elastic_modulus_mpa,
        second_moment_mm4=second_moment_mm4,
        point_loads=(PointLoad(point_kn, load_position_m),),
    )

    nodal_maximum_mm = max(abs(value) for value in result.station_deflections_mm)
    assert result.maximum_position_m == pytest.approx(expected_position_m, rel=1.0e-10)
    assert result.maximum_absolute_deflection_mm == pytest.approx(
        expected_deflection_mm,
        rel=1.0e-8,
    )
    assert result.maximum_absolute_deflection_mm > nodal_maximum_mm
