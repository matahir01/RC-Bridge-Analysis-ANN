import pytest

from rc_bridge.design.eurocode_flanged_flexure import t_section_singly_reinforced_resistance
from rc_bridge.design.eurocode_oriented_flexure import (
    oriented_flanged_singly_reinforced_resistance,
)


def test_top_compression_matches_existing_t_section_kernel() -> None:
    existing = t_section_singly_reinforced_resistance(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    oriented = oriented_flanged_singly_reinforced_resistance(
        compression_flange_width_m=1.70,
        compression_flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_from_compression_face_m=1.10,
        steel_area_mm2=6500.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        compression_face="top",
    )

    assert oriented.resistance_knm == pytest.approx(existing.resistance_knm, rel=1e-12)
    assert oriented.neutral_axis_from_compression_face_m == pytest.approx(
        existing.neutral_axis_m,
        rel=1e-12,
    )
    assert oriented.lever_arm_m == pytest.approx(existing.lever_arm_m, rel=1e-12)
    assert oriented.compression_zone == existing.compression_zone


def test_bottom_compression_uses_supplied_lower_flange_geometry() -> None:
    result = oriented_flanged_singly_reinforced_resistance(
        compression_flange_width_m=0.70,
        compression_flange_thickness_m=0.18,
        web_width_m=0.30,
        effective_depth_from_compression_face_m=1.12,
        steel_area_mm2=5000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        compression_face="bottom",
    )

    assert result.compression_face == "bottom"
    assert result.resistance_knm > 0.0
    assert result.neutral_axis_from_compression_face_m > 0.0
    assert result.lever_arm_m < 1.12


def test_oriented_flanged_flexure_rejects_using_narrower_flange_than_web() -> None:
    with pytest.raises(ValueError, match="Web width"):
        oriented_flanged_singly_reinforced_resistance(
            compression_flange_width_m=0.25,
            compression_flange_thickness_m=0.15,
            web_width_m=0.30,
            effective_depth_from_compression_face_m=1.10,
            steel_area_mm2=4000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
            compression_face="bottom",
        )
