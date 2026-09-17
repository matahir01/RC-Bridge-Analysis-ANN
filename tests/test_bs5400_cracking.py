import pytest

from rc_bridge.design.bs5400_cracking import (
    controlling_surface_distance_mm,
    crack_width_t_section_bs5400,
    mean_strain_bs5400,
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


def test_bs5400_equation_25_caps_mean_strain_at_epsilon_1() -> None:
    result = mean_strain_bs5400(
        epsilon_1=1.0e-3,
        epsilon_s=8.0e-4,
        tension_zone_width_mm=300.0,
        overall_depth_mm=1200.0,
        crack_point_depth_mm=1200.0,
        compression_depth_mm=200.0,
        steel_area_mm2=6500.0,
        permanent_moment_knm=500.0,
        live_moment_knm=800.0,
    )
    assert result.raw_mean_strain > result.epsilon_1
    assert result.mean_strain == pytest.approx(result.epsilon_1)


def test_negative_bs5400_mean_strain_is_treated_as_uncracked() -> None:
    strain = mean_strain_bs5400(
        epsilon_1=1.0e-4,
        epsilon_s=5.0e-4,
        tension_zone_width_mm=1000.0,
        overall_depth_mm=600.0,
        crack_point_depth_mm=590.0,
        compression_depth_mm=136.74,
        steel_area_mm2=3141.59,
        permanent_moment_knm=100.0,
        live_moment_knm=0.0,
    )
    assert strain.mean_strain < 0.0

    crack = surface_crack_width_bs5400(
        acr_mm=60.71,
        mean_strain=strain.mean_strain,
        nominal_cover_mm=40.0,
        overall_depth_mm=600.0,
        compression_depth_mm=136.74,
        allowable_crack_width_mm=0.15,
    )
    assert crack.crack_width_mm == pytest.approx(0.0)
    assert crack.passes


def test_bs5400_t_section_service_path_runs_cracked_elastic_analysis() -> None:
    result = crack_width_t_section_bs5400(
        effective_flange_width_m=1.0,
        flange_thickness_m=0.10,
        web_width_m=1.0,
        total_depth_m=0.60,
        steel_area_mm2=3141.59,
        steel_depth_m=0.54,
        permanent_moment_knm=56.72,
        live_moment_knm=83.07,
        es_mpa=200000.0,
        ec_modified_mpa=27100.0,
        crack_point_depth_mm=590.0,
        acr_mm=60.71,
        nominal_cover_mm=40.0,
        allowable_crack_width_mm=0.15,
    )

    assert result.section.neutral_axis_from_top_mm == pytest.approx(136.7446, abs=1e-3)
    assert result.modular_ratio == pytest.approx(200000.0 / 27100.0)
    assert result.strain.mean_strain <= result.strain.epsilon_1
    assert result.crack.crack_width_mm > 0.0
    assert result.crack.passes
