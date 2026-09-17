import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import (
    SLSCombinationChoice,
    run_project_internal_t_girder_verification,
)
from rc_bridge.workflow.project_detailing import run_project_t_girder_detailing
from rc_bridge.workflow.project_fatigue import (
    ConcreteFatigueInput,
    ProjectFatigueInput,
    ReinforcementFatigueInput,
    run_project_eurocode_fatigue,
)


def _section() -> TGirderDesignInput:
    return TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.20,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )


def _verification_design():
    return run_project_internal_t_girder_verification(
        ProjectInput(),
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        movement_steps=11,
        section_stations=21,
    )


def test_project_fatigue_requires_traceable_fatigue_source() -> None:
    with pytest.raises(ValueError, match="source_description"):
        ProjectFatigueInput(
            source_description="",
            reinforcement=ReinforcementFatigueInput(
                reference_stress_range_mpa=88.0,
                lambda_s=0.89,
                characteristic_fatigue_strength_mpa=162.5,
            ),
        )


def test_project_fatigue_runs_reinforcement_and_concrete_checks() -> None:
    result = run_project_eurocode_fatigue(
        ProjectInput(),
        fatigue=ProjectFatigueInput(
            source_description="Dedicated fatigue-load-model analysis, girder 4",
            reinforcement=ReinforcementFatigueInput(
                reference_stress_range_mpa=88.0,
                lambda_s=0.89,
                characteristic_fatigue_strength_mpa=162.5,
            ),
            concrete=ConcreteFatigueInput(
                sigma_c_max_mpa=8.0,
                sigma_c_min_mpa=2.0,
                beta_cc_t0=1.10,
            ),
        ),
    )
    assert result.reinforcement.equivalent_stress_range_mpa == pytest.approx(78.32)
    assert result.reinforcement.passes
    assert result.concrete is not None
    assert result.concrete.fcd_fat_mpa > 0.0
    assert "fatigue-analysis" in result.status


def test_project_t_girder_detailing_uses_design_shear_and_ec2_materials() -> None:
    design = _verification_design()
    result = run_project_t_girder_detailing(
        ProjectInput(),
        section=_section(),
        design=design.design,
    )

    assert result.effective_concrete_area_m2 == pytest.approx(
        1.70 * 0.175 + 0.30 * (1.20 - 0.175)
    )
    assert result.tension_zone_width_m == pytest.approx(0.30)
    assert result.detailing.longitudinal.minimum_tension_steel_mm2 > 0.0
    assert result.detailing.longitudinal.satisfies_minimum
    assert result.detailing.longitudinal.satisfies_maximum
    assert result.detailing.shear.minimum_asw_per_s_mm2_per_m > 0.0
    assert result.detailing.shear.governing_required_asw_per_s_mm2_per_m >= (
        result.detailing.shear.minimum_asw_per_s_mm2_per_m
    )
