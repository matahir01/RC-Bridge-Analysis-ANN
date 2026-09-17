import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.design.eurocode_shear import provided_vertical_shear_resistance
from rc_bridge.research.multilimit_records import eurocode_multilimit_record_from_project
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import (
    SLSCombinationChoice,
    run_project_internal_t_girder_verification,
)


def _fully_verified() -> DeterministicSolverVerification:
    return DeterministicSolverVerification(
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


def _narrow_web_case():
    project = ProjectInput()
    section = TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.15,
        total_depth_m=1.20,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )
    result = run_project_internal_t_girder_verification(
        project,
        girder_index=4,
        section=section,
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        ),
        crack_combination=SLSCombinationChoice.CHARACTERISTIC,
        deflection_combination=SLSCombinationChoice.FREQUENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        movement_steps=21,
        section_stations=41,
    )
    return project, section, result


def test_provided_vertical_links_use_smaller_of_vrds_and_vrdmax() -> None:
    result = provided_vertical_shear_resistance(
        provided_asw_per_s_mm2_per_m=1500.0,
        web_width_m=0.15,
        effective_depth_m=1.10,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        cot_theta=2.0,
    )
    assert result.vrds_kn > 0.0
    assert result.vrdmax_kn > 0.0
    assert result.governing_resistance_kn == pytest.approx(
        min(result.vrds_kn, result.vrdmax_kn)
    )


def test_multilimit_export_requires_actual_links_when_concrete_shear_is_exceeded() -> None:
    project, section, result = _narrow_web_case()
    assert (
        result.design.uls_design.shear.design_shear_kn
        > result.design.uls_design.shear.concrete_resistance_kn
    )

    with pytest.raises(ValueError, match="Actual provided A_sw/s"):
        eurocode_multilimit_record_from_project(
            result,
            project=project,
            section=section,
            verification=_fully_verified(),
        )


def test_multilimit_record_carries_four_continuous_limit_state_reserves() -> None:
    project, section, result = _narrow_web_case()
    record = eurocode_multilimit_record_from_project(
        result,
        project=project,
        section=section,
        verification=_fully_verified(),
        provided_shear_steel_mm2_per_m=1500.0,
    )

    assert record.solver_profile == SolverProfile.EUROCODE_1G.value
    assert record.fck_mpa == pytest.approx(35.0)
    assert record.fcu_mpa is None
    assert record.g_flexure_knm == pytest.approx(result.design.g_flexure_knm)
    assert record.g_crack_mm == pytest.approx(result.design.g_crack_mm)
    assert record.g_deflection_mm == pytest.approx(result.design.g_deflection_mm)
    assert record.g_shear_kn == pytest.approx(
        record.shear_resistance_kn - record.design_shear_kn
    )
    assert record.provided_shear_steel_mm2_per_m == pytest.approx(1500.0)
    assert "equal_share" in record.traffic_distribution_method
