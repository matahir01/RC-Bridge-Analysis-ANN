import math

from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import EurocodeFactors, persistent_uls
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.research.dataset import TrainingRecord


def test_eurocode_combination_is_transparent() -> None:
    permanent = LoadEffects(moment_knm=100.0, shear_kn=20.0)
    traffic = LoadEffects(moment_knm=50.0, shear_kn=10.0)
    combo = persistent_uls(permanent, traffic, EurocodeFactors(1.35, 1.50))
    assert math.isclose(combo.effects.moment_knm, 210.0)
    assert math.isclose(combo.effects.shear_kn, 42.0)
    assert combo.factors == {"G": 1.35, "Q_traffic": 1.50}


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
        span_m=15.0,
        girder_spacing_m=1.70,
        girder_depth_m=0.95,
        deck_thickness_m=0.25,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        steel_area_mm2=4800.0,
        permanent_moment_knm=800.0,
        traffic_moment_knm=600.0,
        design_moment_knm=1980.0,
        resistance_moment_knm=2200.0,
        g_flexure_knm=220.0,
    )
    row = record.to_dict()
    assert row["span_m"] == 15.0
    assert row["g_flexure_knm"] == 220.0
