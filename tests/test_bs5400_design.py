import pytest

from rc_bridge.design.bs5400_flanged_flexure import check_t_section_flexure_bs5400
from rc_bridge.design.bs5400_flexure import check_rectangular_flexure_bs5400
from rc_bridge.design.bs5400_shear import check_shear_bs5400


def test_bs5400_rectangular_flexure_matches_reference_example() -> None:
    result = check_rectangular_flexure_bs5400(
        med_knm=1339.0,
        width_m=1.0,
        effective_depth_m=0.824,
        steel_area_mm2=5362.0,
        fcu_mpa=40.0,
        fy_mpa=500.0,
    )

    assert result.lever_arm_m == pytest.approx(0.7502725)
    assert result.steel_controlled_resistance_knm == pytest.approx(1749.988098075)
    assert result.concrete_limit_resistance_knm == pytest.approx(4073.856)
    assert result.resistance_knm == pytest.approx(1749.988098075)
    assert result.utilization == pytest.approx(1339.0 / 1749.988098075)
    assert result.g_flexure_knm > 0.0


def test_bs5400_t_section_compression_block_can_stay_in_flange() -> None:
    result = check_t_section_flexure_bs5400(
        med_knm=1800.0,
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        fcu_mpa=40.0,
        fy_mpa=500.0,
    )
    assert result.compression_zone == "flange"
    assert result.neutral_axis_depth_m == pytest.approx(0.103952205882)
    assert result.lever_arm_m == pytest.approx(1.045)
    assert result.resistance_knm == pytest.approx(2954.7375)
    assert result.g_flexure_knm > 0.0


def test_bs5400_t_section_compression_block_can_enter_web() -> None:
    result = check_t_section_flexure_bs5400(
        med_knm=4000.0,
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=13000.0,
        fcu_mpa=40.0,
        fy_mpa=500.0,
    )
    assert result.compression_zone == "flange_and_web"
    assert result.neutral_axis_depth_m == pytest.approx(0.361458333333)
    assert result.lever_arm_m == pytest.approx(0.983896533304)
    assert result.resistance_knm == pytest.approx(5563.934895833)
    assert result.g_flexure_knm > 0.0


def test_bs5400_t_section_rejects_neutral_axis_beyond_singly_reinforced_scope() -> None:
    with pytest.raises(ValueError, match="Neutral axis exceeds"):
        check_t_section_flexure_bs5400(
            med_knm=6000.0,
            effective_flange_width_m=1.70,
            flange_thickness_m=0.175,
            web_width_m=0.30,
            effective_depth_m=1.10,
            steel_area_mm2=18000.0,
            fcu_mpa=40.0,
            fy_mpa=500.0,
        )


def test_bs5400_shear_matches_reference_example_screening() -> None:
    result = check_shear_bs5400(
        ved_kn=443.0,
        web_width_m=1.0,
        effective_depth_m=0.824,
        longitudinal_steel_area_mm2=5362.0,
        fcu_mpa=40.0,
        fyv_mpa=500.0,
    )

    assert result.design_shear_stress_mpa == pytest.approx(0.537621359223)
    assert result.concrete_shear_stress_mpa == pytest.approx(0.640138008264)
    assert result.depth_factor == pytest.approx(0.882593446079)
    assert result.concrete_resistance_kn == pytest.approx(465.544847200)
    assert not result.requires_shear_reinforcement
    assert not result.exceeds_maximum_shear
    assert result.g_shear_concrete_kn > 0.0


def test_bs5400_shear_flags_when_concrete_resistance_is_exceeded() -> None:
    result = check_shear_bs5400(
        ved_kn=600.0,
        web_width_m=1.0,
        effective_depth_m=0.824,
        longitudinal_steel_area_mm2=5362.0,
        fcu_mpa=40.0,
        fyv_mpa=500.0,
    )
    assert result.requires_shear_reinforcement
    assert result.minimum_asv_per_s_mm2_per_m > 0.0


def test_bs5400_shear_flags_absolute_web_crushing_limit() -> None:
    result = check_shear_bs5400(
        ved_kn=5000.0,
        web_width_m=1.0,
        effective_depth_m=0.824,
        longitudinal_steel_area_mm2=5362.0,
        fcu_mpa=40.0,
        fyv_mpa=500.0,
    )
    assert result.exceeds_maximum_shear
