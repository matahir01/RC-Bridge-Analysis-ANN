import pytest

from rc_bridge.design.eurocode_torsion import (
    shear_torsion_interaction,
    torsion_reinforcement_and_resistance,
)


def test_ec2_torsion_reinforcement_and_strut_resistance() -> None:
    result = torsion_reinforcement_and_resistance(
        ted_knm=100.0,
        ak_m2=0.10,
        uk_m=1.40,
        tef_m=0.15,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        cot_theta=2.0,
    )

    assert result.nu1 == pytest.approx(0.516)
    assert result.transverse_asw_per_s_mm2_per_mm == pytest.approx(0.575)
    assert result.transverse_asw_per_s_mm2_per_m == pytest.approx(575.0)
    assert result.longitudinal_asl_mm2 == pytest.approx(3220.0)
    assert result.trdmax_knm == pytest.approx(144.48)


def test_zero_torsion_requires_no_calculated_torsion_steel() -> None:
    result = torsion_reinforcement_and_resistance(
        ted_knm=0.0,
        ak_m2=0.10,
        uk_m=1.40,
        tef_m=0.15,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    assert result.transverse_asw_per_s_mm2_per_mm == pytest.approx(0.0)
    assert result.longitudinal_asl_mm2 == pytest.approx(0.0)
    assert result.trdmax_knm > 0.0


def test_shear_torsion_interaction_is_linear_strut_check() -> None:
    interaction = shear_torsion_interaction(
        ted_knm=100.0,
        trdmax_knm=200.0,
        ved_kn=150.0,
        vrdmax_kn=500.0,
    )
    assert interaction.torsion_ratio == pytest.approx(0.5)
    assert interaction.shear_ratio == pytest.approx(0.3)
    assert interaction.utilization == pytest.approx(0.8)
    assert interaction.passes is True


def test_shear_torsion_interaction_fails_above_unity() -> None:
    interaction = shear_torsion_interaction(
        ted_knm=120.0,
        trdmax_knm=150.0,
        ved_kn=150.0,
        vrdmax_kn=500.0,
    )
    assert interaction.utilization == pytest.approx(1.1)
    assert interaction.passes is False


def test_torsion_requires_valid_strut_angle() -> None:
    with pytest.raises(ValueError, match=r"cot\(theta\)"):
        torsion_reinforcement_and_resistance(
            ted_knm=100.0,
            ak_m2=0.10,
            uk_m=1.40,
            tef_m=0.15,
            fck_mpa=35.0,
            fyk_mpa=500.0,
            cot_theta=3.0,
        )
