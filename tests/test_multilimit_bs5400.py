import pytest

from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.core.models import DesignCode, MaterialProperties, ProjectInput
from rc_bridge.research.multilimit_records import bs5400_multilimit_record_from_project
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)
from rc_bridge.workflow.bs5400_girder import BS5400TGirderInput
from rc_bridge.workflow.project_bs5400 import BS5400TServiceabilityInput
from rc_bridge.workflow.project_bs5400_complete import (
    run_project_internal_bs5400_complete_verification,
)
from rc_bridge.workflow.project_bs5400_deflection import BS5400ProjectDeflectionInput


def _verified_bs5400() -> DeterministicSolverVerification:
    return DeterministicSolverVerification(
        solver_profile=SolverProfile.BS5400_BD37_01,
        traffic_loading=True,
        load_combinations=True,
        flexure=True,
        shear=True,
        cracking=True,
        deflection=True,
        fatigue=True,
        detailing=True,
        transverse_distribution=True,
        independent_benchmark=True,
    )


def _complete_case():
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
    return project, section, result


def test_bs5400_multilimit_record_preserves_cube_strength_and_four_margins() -> None:
    project, section, result = _complete_case()
    provided_links = result.uls.design.shear.governing_asv_per_s_mm2_per_m * 1.25
    record = bs5400_multilimit_record_from_project(
        result,
        project=project,
        section=section,
        verification=_verified_bs5400(),
        provided_shear_steel_mm2_per_m=provided_links,
    )

    assert record.girder_index == 4
    assert record.solver_profile == SolverProfile.BS5400_BD37_01.value
    assert record.fck_mpa is None
    assert record.fcu_mpa == pytest.approx(40.0)
    assert record.g_flexure_knm == pytest.approx(result.uls.design.flexure.g_flexure_knm)
    assert record.g_crack_mm == pytest.approx(result.cracking.crack.crack.g_crack_mm)
    assert record.g_deflection_mm == pytest.approx(
        result.deflection.deflection.g_deflection_mm
    )
    assert record.g_shear_kn == pytest.approx(
        record.shear_resistance_kn - record.design_shear_kn
    )
    assert record.provided_shear_steel_mm2_per_m == pytest.approx(provided_links)


def test_bs5400_multilimit_record_rejects_eurocode_verification_profile() -> None:
    project, section, result = _complete_case()
    wrong_profile = DeterministicSolverVerification(
        solver_profile=SolverProfile.EUROCODE_1G,
        traffic_loading=True,
        load_combinations=True,
        flexure=True,
        shear=True,
        cracking=True,
        deflection=True,
        fatigue=True,
        detailing=True,
        transverse_distribution=True,
        independent_benchmark=True,
    )
    with pytest.raises(RuntimeError, match="does not match"):
        bs5400_multilimit_record_from_project(
            result,
            project=project,
            section=section,
            verification=wrong_profile,
            provided_shear_steel_mm2_per_m=1000.0,
        )
