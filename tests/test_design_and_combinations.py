import math

from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.research.dataset import TrainingRecord
from rc_bridge.research.verification import SolverProfile


def test_default_road_bridge_traffic_factor_is_jrc_reference_value() -> None:
    factors = EurocodeFactors()

    assert math.isclose(factors.gamma_g_unfavourable, 1.35)
    assert math.isclose(factors.gamma_q_traffic, 1.35)
    assert math.isclose(factors.gamma_g_favourable, 1.00)


def test_eurocode_combination_is_transparent() -> None:
    permanent = LoadEffects(moment_knm=100.0, shear_kn=20.0)
    traffic = LoadEffects(moment_knm=50.0, shear_kn=10.0)
    combo = persistent_uls(permanent, traffic, EurocodeFactors(1.35, 1.50))
    assert math.isclose(combo.effects.moment_knm, 210.0)
    assert math.isclose(combo.effects.shear_kn, 42.0)
    assert combo.factors == {"G": 1.35, "Q_traffic": 1.50}


def test_characteristic_sls_uses_unity_factors_for_single_leading_traffic_action() -> None:
    permanent = LoadEffects(moment_knm=100.0, shear_kn=50.0)
    traffic = LoadEffects(moment_knm=40.0, shear_kn=20.0)
    combo = characteristic_sls(permanent, traffic)
    assert math.isclose(combo.effects.moment_knm, 140.0)
    assert math.isclose(combo.effects.shear_kn, 70.0)
    assert combo.factors == {"G": 1.0, "Q_traffic": 1.0}


def test_frequent_and_quasi_permanent_sls_use_explicit_psi_factors() -> None:
    permanent = LoadEffects(moment_knm=100.0, shear_kn=50.0)
    traffic = LoadEffects(moment_knm=40.0, shear_kn=20.0)
    factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)

    frequent = frequent_sls(permanent, traffic, factors)
    quasi = quasi_permanent_sls(permanent, traffic, factors)

    assert math.isclose(frequent.effects.moment_knm, 130.0)
    assert math.isclose(frequent.effects.shear_kn, 65.0)
    assert frequent.factors == {"G": 1.0, "Q_traffic": 0.75}

    assert math.isclose(quasi.effects.moment_knm, 112.0)
    assert math.isclose(quasi.effects.shear_kn, 56.0)
    assert quasi.factors == {"G": 1.0, "Q_traffic": 0.30}


def test_preliminary_ec2_flexure_returns_positive_resistance() -> None:
    result = rectangular_singly_reinforced_resistance(
        width_m=0.30,
        effective_depth_m=0.87,
        steel_area_mm2=4800.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    assert result.resistance_knm > 0
    assert result.neutral_axis_m > 0
    assert 0 < result.lever_arm_m < 0.87
    assert "preliminary" in result.status


def test_training_record_exports_solver_outputs() -> None:
    record = TrainingRecord(
        solver_profile=SolverProfile.EUROCODE_1G.value,
        span_m=15.0,
        girder_spacing_m=1.70,
        girder_depth_m=0.95,
        deck_thickness_m=0.25,
        fck_mpa=35.0,
        fcu_mpa=None,
        fyk_mpa=500.0,
        steel_area_mm2=4800.0,
        permanent_moment_knm=800.0,
        traffic_moment_knm=600.0,
        design_moment_knm=1980.0,
        resistance_moment_knm=2200.0,
        g_flexure_knm=220.0,
    )
    row = record.to_dict()
    assert row["solver_profile"] == SolverProfile.EUROCODE_1G.value
    assert row["span_m"] == 15.0
    assert row["g_flexure_knm"] == 220.0
