import pytest

from rc_bridge.design.bs5400_cracking import (
    controlling_surface_distance_mm,
    surface_crack_width_bs5400,
)


def test_bs5400_surface_crack_width_matches_published_worked_value() -> None:
    result = surface_crack_width_bs5400(
        acr_mm=60.71,
        mean_strain=5.96e-4,
        nominal_cover_mm=40.0,
        overall_depth_mm=600.0,
        compression_depth_mm=136.74,
        allowable_crack_width_mm=0.15,
    )
    assert result.crack_width_mm == pytest.approx(0.09964, abs=5e-5)
    assert result.passes
    assert result.g_crack_mm > 0.0


def test_bs5400_zero_compression_depth_uses_alternative_equation() -> None:
    result = surface_crack_width_bs5400(
        acr_mm=75.0,
        mean_strain=8.0e-4,
        nominal_cover_mm=40.0,
        overall_depth_mm=600.0,
        compression_depth_mm=0.0,
        allowable_crack_width_mm=0.25,
    )
    assert result.crack_width_mm == pytest.approx(0.18)
    assert result.passes


def test_surface_distance_helper_uses_spacing_cover_and_bar_radius() -> None:
    acr = controlling_surface_distance_mm(
        bar_spacing_mm=100.0,
        nominal_cover_to_bar_surface_mm=40.0,
        bar_diameter_mm=20.0,
    )
    assert acr == pytest.approx((50.0**2 + 50.0**2) ** 0.5 - 10.0)


def test_bs5400_crack_width_rejects_invalid_compression_depth() -> None:
    with pytest.raises(ValueError, match="compression_depth_mm"):
        surface_crack_width_bs5400(
            acr_mm=60.0,
            mean_strain=5.0e-4,
            nominal_cover_mm=40.0,
            overall_depth_mm=600.0,
            compression_depth_mm=600.0,
            allowable_crack_width_mm=0.25,
        )
