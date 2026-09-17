import pytest

from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.effective_width import effective_flange_width_ec2
from rc_bridge.design.eurocode_flanged_flexure import (
    t_section_singly_reinforced_resistance,
)
from rc_bridge.design.girder_design import design_t_girder_ec2


def test_effective_width_is_capped_by_physical_width() -> None:
    result = effective_flange_width_ec2(
        web_width_m=0.30,
        left_outstand_m=0.70,
        right_outstand_m=0.70,
        l0_m=15.0,
    )
    assert result.physical_flange_width_m == pytest.approx(1.70)
    assert result.effective_flange_width_m == pytest.approx(1.70)


def test_effective_width_reduces_for_short_l0() -> None:
    result = effective_flange_width_ec2(
        web_width_m=0.30,
        left_outstand_m=0.70,
        right_outstand_m=0.70,
        l0_m=2.0,
    )
    assert result.left_effective_outstand_m == pytest.approx(0.34)
    assert result.right_effective_outstand_m == pytest.approx(0.34)
    assert result.effective_flange_width_m == pytest.approx(0.98)


def test_t_section_compression_block_can_stay_in_flange() -> None:
    result = t_section_singly_reinforced_resistance(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=5000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    assert result.compression_zone == "flange_only"
    assert result.resistance_knm > 0.0


def test_t_section_compression_block_can_enter_web() -> None:
    result = t_section_singly_reinforced_resistance(
        effective_flange_width_m=0.70,
        flange_thickness_m=0.10,
        web_width_m=0.30,
        effective_depth_m=0.90,
        steel_area_mm2=8000.0,
        fck_mpa=30.0,
        fyk_mpa=500.0,
    )
    assert result.compression_zone == "flange_and_web"
    assert result.compression_block_depth_m > 0.10


def test_integrated_t_girder_design_returns_limit_states() -> None:
    design = design_t_girder_ec2(
        girder_index=4,
        design_effects=LoadEffects(moment_knm=1800.0, shear_kn=450.0),
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        effective_depth_m=1.10,
        provided_steel_area_mm2=6000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    assert design.flexure.required_steel_area_mm2 > 0.0
    assert design.flexure.resistance_knm > 0.0
    assert design.flexure.g_flexure_knm == pytest.approx(
        design.flexure.resistance_knm - 1800.0
    )
    assert design.shear.design_shear_kn == pytest.approx(450.0)
