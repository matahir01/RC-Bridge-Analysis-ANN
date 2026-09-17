import pytest

from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.codes.common import LoadEffects
from rc_bridge.core.models import DesignCode, MaterialProperties, ProjectInput
from rc_bridge.workflow.bs5400_girder import (
    BS5400RectangularGirderInput,
    BS5400TGirderInput,
    run_bs5400_rectangular_girder_case,
    run_bs5400_t_girder_case,
)


def _project() -> ProjectInput:
    return ProjectInput(
        design_code=DesignCode.BS5400,
        materials=MaterialProperties(
            fck_mpa=30.0,
            fyk_mpa=500.0,
            fcu_mpa=40.0,
        ),
    )


def _section() -> BS5400RectangularGirderInput:
    return BS5400RectangularGirderInput(
        width_m=1.0,
        web_width_m=1.0,
        effective_depth_m=0.824,
        steel_area_mm2=5362.0,
    )


def _t_section() -> BS5400TGirderInput:
    return BS5400TGirderInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
    )


def test_bs5400_project_workflow_combines_actions_and_checks_member() -> None:
    result = run_bs5400_rectangular_girder_case(
        _project(),
        permanent_effects=LoadEffects(moment_knm=700.0, shear_kn=200.0),
        live_effects=LoadEffects(moment_knm=300.0, shear_kn=100.0),
        factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
        section=_section(),
    )

    assert result.uls_combination.effects.moment_knm == pytest.approx(1260.0)
    assert result.uls_combination.effects.shear_kn == pytest.approx(380.0)
    assert result.flexure.resistance_knm == pytest.approx(1749.988098075)
    assert result.flexure.g_flexure_knm > 0.0
    assert result.shear.g_shear_concrete_kn > 0.0
    assert not result.shear.requires_shear_reinforcement


def test_bs5400_t_girder_project_path_uses_flange_for_flexure_and_web_for_shear() -> None:
    result = run_bs5400_t_girder_case(
        _project(),
        permanent_effects=LoadEffects(moment_knm=700.0, shear_kn=200.0),
        live_effects=LoadEffects(moment_knm=300.0, shear_kn=100.0),
        factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
        section=_t_section(),
    )

    assert result.uls_combination.effects.moment_knm == pytest.approx(1260.0)
    assert result.flexure.compression_zone == "flange"
    assert result.flexure.resistance_knm == pytest.approx(2954.7375)
    assert result.flexure.g_flexure_knm > 0.0
    assert result.shear.design_shear_kn == pytest.approx(380.0)
    assert result.shear.requires_shear_reinforcement
    assert not result.shear.exceeds_maximum_shear


def test_bs5400_project_requires_explicit_cube_strength() -> None:
    project = ProjectInput(
        design_code=DesignCode.BS5400,
        materials=MaterialProperties(fck_mpa=30.0, fyk_mpa=500.0),
    )
    with pytest.raises(ValueError, match="explicit concrete cube strength"):
        run_bs5400_rectangular_girder_case(
            project,
            permanent_effects=LoadEffects(moment_knm=700.0, shear_kn=200.0),
            live_effects=LoadEffects(moment_knm=300.0, shear_kn=100.0),
            factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
            section=_section(),
        )


def test_bs5400_workflow_rejects_eurocode_project() -> None:
    with pytest.raises(ValueError, match="requires a BS5400 project"):
        run_bs5400_rectangular_girder_case(
            ProjectInput(),
            permanent_effects=LoadEffects(moment_knm=700.0, shear_kn=200.0),
            live_effects=LoadEffects(moment_knm=300.0, shear_kn=100.0),
            factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
            section=_section(),
        )
