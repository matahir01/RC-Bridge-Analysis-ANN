import pytest

from rc_bridge.codes.common import LoadEffects
from rc_bridge.design.eurocode_demand import (
    check_flexure_rectangular,
    check_shear,
    required_tension_steel_rectangular,
)
from rc_bridge.design.eurocode_shear import concrete_shear_resistance
from rc_bridge.design.girder_design import design_rectangular_girder_ec2


def test_required_steel_increases_with_design_moment():
    low = required_tension_steel_rectangular(500.0, 0.8, 0.9, 35.0, 500.0)
    high = required_tension_steel_rectangular(1000.0, 0.8, 0.9, 35.0, 500.0)
    assert high > low > 0.0


def test_flexure_limit_state_matches_utilization_direction():
    result = check_flexure_rectangular(700.0, 0.8, 0.9, 5000.0, 35.0, 500.0)
    assert result.resistance_knm > 0.0
    if result.utilization < 1.0:
        assert result.g_flexure_knm > 0.0
    else:
        assert result.g_flexure_knm <= 0.0


def test_concrete_shear_resistance_positive():
    result = concrete_shear_resistance(0.30, 0.90, 5000.0, 35.0)
    assert result.vrdc_kn > 0.0
    assert 0.0 < result.rho_l <= 0.02
    assert result.k <= 2.0


def test_shear_reinforcement_generated_when_ved_exceeds_vrdc():
    concrete = concrete_shear_resistance(0.30, 0.90, 5000.0, 35.0)
    result = check_shear(concrete.vrdc_kn * 1.5, 0.30, 0.90, 5000.0, 35.0, 500.0)
    assert result.shear_reinforcement is not None
    assert result.g_shear_concrete_kn < 0.0
    assert result.shear_reinforcement.asw_per_s_mm2_per_m > 0.0


def test_integrated_girder_design_carries_limit_states():
    result = design_rectangular_girder_ec2(
        girder_index=4,
        design_effects=LoadEffects(moment_knm=800.0, shear_kn=300.0),
        width_m=0.8,
        web_width_m=0.30,
        effective_depth_m=0.90,
        provided_steel_area_mm2=6000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    assert result.girder_index == 4
    assert result.flexure.required_steel_area_mm2 > 0.0
    assert result.flexure.g_flexure_knm == pytest.approx(
        result.flexure.resistance_knm - 800.0
    )
    assert result.shear.g_shear_concrete_kn == pytest.approx(
        result.shear.concrete_resistance_kn - 300.0
    )
