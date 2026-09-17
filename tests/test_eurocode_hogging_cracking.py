import pytest

from rc_bridge.design.eurocode_cracking import (
    crack_width_ec2_t_section,
    cracked_t_section_sls,
)
from rc_bridge.design.eurocode_hogging_cracking import (
    crack_width_ec2_hogging_section,
    cracked_hogging_section_sls,
)


def test_hogging_cracked_rectangular_mirror_matches_existing_positive_solver() -> None:
    modular_ratio = 200000.0 / 34000.0
    positive = cracked_t_section_sls(
        effective_flange_width_m=0.30,
        flange_thickness_m=0.20,
        web_width_m=0.30,
        total_depth_m=1.00,
        steel_area_mm2=4000.0,
        steel_depth_m=0.95,
        modular_ratio=modular_ratio,
        service_moment_knm=500.0,
    )
    hogging = cracked_hogging_section_sls(
        bottom_flange_width_m=0.30,
        bottom_flange_thickness_m=0.0,
        web_width_m=0.30,
        total_depth_m=1.00,
        top_tension_flange_width_m=0.30,
        top_tension_flange_thickness_m=0.20,
        steel_area_mm2=4000.0,
        steel_depth_from_bottom_m=0.95,
        modular_ratio=modular_ratio,
        service_moment_knm=500.0,
    )

    assert hogging.neutral_axis_from_bottom_mm == pytest.approx(
        positive.neutral_axis_from_top_mm,
        rel=1e-10,
    )
    assert hogging.second_moment_mm4 == pytest.approx(positive.second_moment_mm4, rel=1e-10)
    assert hogging.top_steel_stress_mpa == pytest.approx(positive.steel_stress_mpa, rel=1e-10)


def test_hogging_crack_width_mirror_matches_existing_rectangular_case() -> None:
    common = dict(
        steel_area_mm2=4000.0,
        bar_diameter_mm=25.0,
        bar_spacing_mm=150.0,
        cover_mm=40.0,
        service_moment_knm=500.0,
        cracking_moment_knm=150.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )
    positive = crack_width_ec2_t_section(
        effective_flange_width_m=0.30,
        flange_thickness_m=0.20,
        web_width_m=0.30,
        total_depth_m=1.00,
        steel_depth_m=0.95,
        **common,
    )
    hogging = crack_width_ec2_hogging_section(
        bottom_flange_width_m=0.30,
        bottom_flange_thickness_m=0.0,
        web_width_m=0.30,
        total_depth_m=1.00,
        top_tension_flange_width_m=0.30,
        top_tension_flange_thickness_m=0.20,
        steel_depth_from_bottom_m=0.95,
        **common,
    )

    assert hogging.steel_stress_mpa == pytest.approx(positive.steel_stress_mpa, rel=1e-10)
    assert hogging.effective_tension_depth_mm == pytest.approx(
        positive.effective_tension_depth_mm,
        rel=1e-10,
    )
    assert hogging.effective_tension_area_mm2 == pytest.approx(
        positive.effective_tension_area_mm2,
        rel=1e-10,
    )
    assert hogging.crack_width_mm == pytest.approx(positive.crack_width_mm, rel=1e-10)


def test_i_girder_hogging_crack_model_uses_bottom_compression_and_top_deck_tension() -> None:
    cracked = cracked_hogging_section_sls(
        bottom_flange_width_m=0.65,
        bottom_flange_thickness_m=0.18,
        web_width_m=0.30,
        total_depth_m=1.20,
        top_tension_flange_width_m=1.70,
        top_tension_flange_thickness_m=0.175,
        steel_area_mm2=6500.0,
        steel_depth_from_bottom_m=1.14,
        modular_ratio=200000.0 / 34000.0,
        service_moment_knm=900.0,
    )

    assert 0.0 < cracked.neutral_axis_from_bottom_mm < 1140.0
    assert cracked.second_moment_mm4 > 0.0
    assert cracked.top_steel_stress_mpa > 0.0
    assert cracked.compression_zone in {"bottom_flange_only", "bottom_flange_and_web"}


def test_hogging_crack_check_returns_zero_below_explicit_cracking_moment() -> None:
    result = crack_width_ec2_hogging_section(
        bottom_flange_width_m=0.65,
        bottom_flange_thickness_m=0.18,
        web_width_m=0.30,
        total_depth_m=1.20,
        top_tension_flange_width_m=1.70,
        top_tension_flange_thickness_m=0.175,
        steel_area_mm2=6500.0,
        steel_depth_from_bottom_m=1.14,
        bar_diameter_mm=25.0,
        bar_spacing_mm=150.0,
        cover_mm=40.0,
        service_moment_knm=100.0,
        cracking_moment_knm=200.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )

    assert result.crack_width_mm == pytest.approx(0.0)
    assert result.g_crack_mm == pytest.approx(0.30)
    assert "uncracked" in result.status
