import pytest

from rc_bridge.analysis.loads import PointLoad
from rc_bridge.core.models import DesignCode, MaterialProperties, ProjectInput
from rc_bridge.design.bs5400_deflection import bs5400_simple_span_elastic_deflection
from rc_bridge.workflow.project_bs5400_deflection import (
    BS5400ProjectDeflectionInput,
    run_project_internal_bs5400_deflection_verification,
)


def test_bs5400_deflection_separates_long_term_and_short_term_components() -> None:
    span_m = 15.0
    inertia = 2.5e11
    long_term_e = 16000.0
    short_term_e = 32000.0

    result = bs5400_simple_span_elastic_deflection(
        span_m=span_m,
        permanent_udl_kn_m=20.0,
        live_udl_kn_m=10.0,
        live_point_loads=(PointLoad(120.0, 7.5),),
        long_term_concrete_modulus_mpa=long_term_e,
        short_term_concrete_modulus_mpa=short_term_e,
        permanent_second_moment_mm4=inertia,
        live_second_moment_mm4=inertia,
        allowable_deflection_mm=100.0,
    )

    span_mm = span_m * 1000.0
    expected_permanent = 5.0 * 20.0 * span_mm**4 / (384.0 * long_term_e * inertia)
    expected_live_udl = 5.0 * 10.0 * span_mm**4 / (384.0 * short_term_e * inertia)
    expected_live_point = 120000.0 * span_mm**3 / (48.0 * short_term_e * inertia)

    assert result.permanent_long_term_deflection_mm == pytest.approx(expected_permanent)
    assert result.live_short_term_deflection_mm == pytest.approx(
        expected_live_udl + expected_live_point
    )
    assert result.total_deflection_mm == pytest.approx(
        expected_permanent + expected_live_udl + expected_live_point
    )
    assert result.passes is True
    assert result.g_deflection_mm is not None


def test_bs5400_deflection_without_project_limit_reports_no_pass_fail() -> None:
    result = bs5400_simple_span_elastic_deflection(
        span_m=15.0,
        permanent_udl_kn_m=20.0,
        live_udl_kn_m=10.0,
        live_point_loads=(),
        long_term_concrete_modulus_mpa=16000.0,
        short_term_concrete_modulus_mpa=32000.0,
        permanent_second_moment_mm4=2.5e11,
        live_second_moment_mm4=2.5e11,
    )
    assert result.allowable_deflection_mm is None
    assert result.utilization is None
    assert result.g_deflection_mm is None
    assert result.passes is None


def test_project_bs5400_deflection_retains_ha_load_shape() -> None:
    project = ProjectInput(
        design_code=DesignCode.BS5400,
        materials=MaterialProperties(fck_mpa=35.0, fcu_mpa=40.0, fyk_mpa=500.0),
    )
    result = run_project_internal_bs5400_deflection_verification(
        project,
        girder_index=4,
        input=BS5400ProjectDeflectionInput(
            long_term_concrete_modulus_mpa=16000.0,
            short_term_concrete_modulus_mpa=32000.0,
            permanent_second_moment_mm4=2.5e11,
            live_second_moment_mm4=2.5e11,
            allowable_deflection_mm=100.0,
        ),
    )

    assert result.permanent_udl_kn_m == pytest.approx(10.625)
    assert result.live_udl_kn_m == pytest.approx(15.0006022850)
    assert len(result.live_point_loads) == 2
    assert all(load.position_m == pytest.approx(7.5) for load in result.live_point_loads)
    assert all(load.magnitude_kn == pytest.approx(16.44) for load in result.live_point_loads)
    assert result.deflection.total_deflection_mm > 0.0
    assert "equal_share_verification_only" in result.traffic_distribution_method
