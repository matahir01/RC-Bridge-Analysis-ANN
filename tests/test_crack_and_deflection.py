import pytest

from rc_bridge.analysis.loads import PointLoad
from rc_bridge.design.eurocode_cracking import (
    crack_width_ec2_t_section,
    cracked_t_section_sls,
)
from rc_bridge.design.eurocode_deflection import (
    SimpleSpanMomentDiagram,
    ec2_interpolated_load_pattern_deflection,
    ec2_interpolated_moment_diagram_deflection,
    ec2_interpolated_udl_deflection,
    effective_concrete_modulus_mpa,
    simply_supported_full_span_udl_deflection_mm,
)
from rc_bridge.design.eurocode_serviceability import uncracked_t_section_sls


def test_cracked_t_section_properties_and_steel_stress_are_positive() -> None:
    result = cracked_t_section_sls(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        modular_ratio=6.0,
        service_moment_knm=1200.0,
    )
    assert 0.0 < result.neutral_axis_from_top_mm < 1100.0
    assert result.second_moment_mm4 > 0.0
    assert result.steel_stress_mpa > 0.0


def test_uncracked_member_returns_zero_crack_width() -> None:
    result = crack_width_ec2_t_section(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
        service_moment_knm=100.0,
        cracking_moment_knm=300.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )
    assert result.crack_width_mm == pytest.approx(0.0)
    assert result.g_crack_mm == pytest.approx(0.30)


def test_cracked_member_returns_continuous_crack_limit_state() -> None:
    result = crack_width_ec2_t_section(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
        service_moment_knm=1200.0,
        cracking_moment_knm=300.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )
    assert result.crack_width_mm > 0.0
    assert result.max_crack_spacing_mm > 0.0
    assert result.g_crack_mm == pytest.approx(0.30 - result.crack_width_mm)
    assert result.utilization == pytest.approx(result.crack_width_mm / 0.30)


def test_effective_modulus_reduces_with_creep() -> None:
    assert effective_concrete_modulus_mpa(34000.0, 1.0) == pytest.approx(17000.0)


def test_elastic_udl_deflection_matches_closed_form() -> None:
    value = simply_supported_full_span_udl_deflection_mm(
        udl_kn_m=20.0,
        span_m=10.0,
        elastic_modulus_mpa=30000.0,
        second_moment_mm4=8.0e9,
    )
    expected = 5.0 * 20.0 * 10000.0**4 / (384.0 * 30000.0 * 8.0e9)
    assert value == pytest.approx(expected)


def test_ec2_deflection_result_carries_limit_state() -> None:
    uncracked = uncracked_t_section_sls(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        modular_ratio=6.0,
        fct_eff_mpa=3.2,
    )
    cracked = cracked_t_section_sls(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        modular_ratio=6.0,
        service_moment_knm=700.0,
    )
    result = ec2_interpolated_udl_deflection(
        udl_kn_m=25.0,
        span_m=15.0,
        ecm_mpa=34000.0,
        uncracked_second_moment_mm4=uncracked.second_moment_mm4,
        cracked_second_moment_mm4=cracked.second_moment_mm4,
        cracking_moment_knm=uncracked.cracking_moment_knm,
        allowable_deflection_mm=30.0,
        beta=0.5,
    )
    assert result.interpolated_deflection_mm >= result.uncracked_deflection_mm
    assert result.interpolated_deflection_mm <= result.fully_cracked_deflection_mm
    assert result.g_deflection_mm == pytest.approx(
        30.0 - result.interpolated_deflection_mm
    )


def test_load_pattern_deflection_recovers_full_span_udl_closed_form() -> None:
    result = ec2_interpolated_load_pattern_deflection(
        span_m=10.0,
        ecm_mpa=30000.0,
        uncracked_second_moment_mm4=8.0e9,
        cracked_second_moment_mm4=8.0e9,
        service_moment_knm=250.0,
        cracking_moment_knm=500.0,
        allowable_deflection_mm=50.0,
        udl_kn_m=20.0,
        evaluation_stations=51,
        integration_segments=400,
    )
    expected = simply_supported_full_span_udl_deflection_mm(
        udl_kn_m=20.0,
        span_m=10.0,
        elastic_modulus_mpa=30000.0,
        second_moment_mm4=8.0e9,
    )
    assert result.interpolated_deflection_mm == pytest.approx(expected, rel=1.0e-7)
    assert "load-pattern" in result.status


def test_load_pattern_deflection_uses_actual_asymmetric_axle_positions() -> None:
    left_pattern = ec2_interpolated_load_pattern_deflection(
        span_m=12.0,
        ecm_mpa=32000.0,
        uncracked_second_moment_mm4=1.0e10,
        cracked_second_moment_mm4=6.0e9,
        service_moment_knm=300.0,
        cracking_moment_knm=180.0,
        allowable_deflection_mm=48.0,
        point_loads=(PointLoad(100.0, 2.0), PointLoad(120.0, 3.5)),
        evaluation_stations=61,
        integration_segments=400,
    )
    mirrored_pattern = ec2_interpolated_load_pattern_deflection(
        span_m=12.0,
        ecm_mpa=32000.0,
        uncracked_second_moment_mm4=1.0e10,
        cracked_second_moment_mm4=6.0e9,
        service_moment_knm=300.0,
        cracking_moment_knm=180.0,
        allowable_deflection_mm=48.0,
        point_loads=(PointLoad(100.0, 10.0), PointLoad(120.0, 8.5)),
        evaluation_stations=61,
        integration_segments=400,
    )
    central_equivalent = ec2_interpolated_load_pattern_deflection(
        span_m=12.0,
        ecm_mpa=32000.0,
        uncracked_second_moment_mm4=1.0e10,
        cracked_second_moment_mm4=6.0e9,
        service_moment_knm=300.0,
        cracking_moment_knm=180.0,
        allowable_deflection_mm=48.0,
        point_loads=(PointLoad(220.0, 6.0),),
        evaluation_stations=61,
        integration_segments=400,
    )

    assert left_pattern.interpolated_deflection_mm == pytest.approx(
        mirrored_pattern.interpolated_deflection_mm,
        rel=1.0e-7,
    )
    assert left_pattern.interpolated_deflection_mm < central_equivalent.interpolated_deflection_mm


def test_ec2_moment_diagram_deflection_carries_traceable_source() -> None:
    result = ec2_interpolated_moment_diagram_deflection(
        diagram=SimpleSpanMomentDiagram(
            stations_m=(0.0, 5.0, 10.0),
            moments_knm=(0.0, 250.0, 0.0),
            source="native LM1 case 17 girder 4 plus permanent UDL",
        ),
        ecm_mpa=30_000.0,
        uncracked_second_moment_mm4=8.0e9,
        cracked_second_moment_mm4=5.0e9,
        service_moment_knm=250.0,
        cracking_moment_knm=150.0,
        allowable_deflection_mm=40.0,
    )

    assert result.fully_cracked_deflection_mm > result.uncracked_deflection_mm
    assert result.interpolated_deflection_mm > result.uncracked_deflection_mm
    assert "native LM1 case 17" in result.status
