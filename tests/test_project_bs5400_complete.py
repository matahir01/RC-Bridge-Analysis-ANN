import pytest

from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.core.models import DesignCode, MaterialProperties, ProjectInput
from rc_bridge.workflow.bs5400_girder import BS5400TGirderInput
from rc_bridge.workflow.project_bs5400 import BS5400TServiceabilityInput
from rc_bridge.workflow.project_bs5400_complete import (
    run_project_internal_bs5400_complete_verification,
)
from rc_bridge.workflow.project_bs5400_deflection import BS5400ProjectDeflectionInput


def test_project_bs5400_complete_verification_packages_uls_and_sls() -> None:
    project = ProjectInput(
        design_code=DesignCode.BS5400,
        materials=MaterialProperties(fck_mpa=35.0, fcu_mpa=40.0, fyk_mpa=500.0),
    )
    section = BS5400TGirderInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
    )

    result = run_project_internal_bs5400_complete_verification(
        project,
        girder_index=4,
        section=section,
        factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
        serviceability=BS5400TServiceabilityInput(
            total_depth_m=1.20,
            ec_modified_mpa=27000.0,
            crack_point_depth_mm=1150.0,
            acr_mm=75.0,
            nominal_cover_mm=50.0,
            allowable_crack_width_mm=0.25,
        ),
        deflection=BS5400ProjectDeflectionInput(
            long_term_concrete_modulus_mpa=16000.0,
            short_term_concrete_modulus_mpa=32000.0,
            permanent_second_moment_mm4=2.5e11,
            live_second_moment_mm4=2.5e11,
            allowable_deflection_mm=100.0,
        ),
    )

    assert result.uls.design.flexure.g_flexure_knm > 0.0
    assert result.uls.design.shear.governing_asv_per_s_mm2_per_m > 0.0
    assert result.cracking.crack.crack.crack_width_mm >= 0.0
    assert result.deflection.deflection.total_deflection_mm > 0.0
    assert result.deflection.deflection.passes is True
    assert result.uls.permanent_characteristic.moment_knm == pytest.approx(
        result.cracking.permanent_characteristic.moment_knm
    )
    assert result.uls.traffic_characteristic.moment_knm == pytest.approx(
        result.cracking.traffic_characteristic.moment_knm
    )
    assert "equal_share_verification_only" in result.traffic_distribution_method
