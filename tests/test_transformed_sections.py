import pytest

from rc_bridge.analysis.transformed_sections import cracked_t_section_properties
from rc_bridge.design.eurocode_cracking import cracked_t_section_sls


def test_code_neutral_cracked_t_section_matches_existing_solver() -> None:
    kwargs = dict(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6500.0,
        steel_depth_m=1.10,
        modular_ratio=6.25,
        service_moment_knm=1400.0,
    )
    neutral = cracked_t_section_properties(**kwargs)
    existing = cracked_t_section_sls(**kwargs)

    assert neutral.neutral_axis_from_top_mm == pytest.approx(
        existing.neutral_axis_from_top_mm
    )
    assert neutral.second_moment_mm4 == pytest.approx(existing.second_moment_mm4)
    assert neutral.steel_stress_mpa == pytest.approx(existing.steel_stress_mpa)


def test_code_neutral_cracked_t_section_rejects_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="Web width cannot exceed"):
        cracked_t_section_properties(
            effective_flange_width_m=0.25,
            flange_thickness_m=0.175,
            web_width_m=0.30,
            total_depth_m=1.20,
            steel_area_mm2=6500.0,
            steel_depth_m=1.10,
            modular_ratio=6.25,
            service_moment_knm=1400.0,
        )
