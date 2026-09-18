import pytest

from rc_bridge.analysis.physical_sections import ConcreteSectionLayer
from rc_bridge.design.eurocode_cracking import cracked_t_section_sls
from rc_bridge.design.eurocode_demand import required_tension_steel_t_section
from rc_bridge.design.eurocode_flanged_flexure import t_section_singly_reinforced_resistance
from rc_bridge.design.eurocode_layered_section import (
    crack_width_layered_section,
    cracked_layered_section_sls,
    layered_singly_reinforced_resistance,
    required_tension_steel_layered,
    uncracked_layered_section_sls,
)
from rc_bridge.design.eurocode_serviceability import uncracked_t_section_sls


def _contiguous_t_layers() -> tuple[ConcreteSectionLayer, ...]:
    return (
        ConcreteSectionLayer(1.70, 0.0, 0.175, "flange"),
        ConcreteSectionLayer(0.30, 0.175, 1.20, "web"),
    )


def test_layered_uls_matches_existing_contiguous_t_section_kernel() -> None:
    layered = layered_singly_reinforced_resistance(
        layers=_contiguous_t_layers(),
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    existing = t_section_singly_reinforced_resistance(
        1.70, 0.175, 0.30, 1.10, 6500.0, 35.0, 500.0
    )

    assert layered.resistance_knm == pytest.approx(existing.resistance_knm, rel=1.0e-10)
    assert layered.compression_block_depth_m == pytest.approx(
        existing.compression_block_depth_m, rel=1.0e-10
    )
    assert layered.lever_arm_m == pytest.approx(existing.lever_arm_m, rel=1.0e-10)


def test_layered_required_steel_matches_existing_t_section_solver() -> None:
    layered = required_tension_steel_layered(
        med_knm=1500.0,
        layers=_contiguous_t_layers(),
        effective_depth_m=1.10,
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )
    existing = required_tension_steel_t_section(
        1500.0, 1.70, 0.175, 0.30, 1.10, 35.0, 500.0
    )
    assert layered == pytest.approx(existing, rel=2.0e-4)


def test_layered_service_properties_match_existing_t_section_without_gaps() -> None:
    modular_ratio = 200000.0 / 34000.0
    uncracked = uncracked_layered_section_sls(
        layers=_contiguous_t_layers(),
        steel_area_mm2=6500.0,
        steel_depth_m=1.10,
        modular_ratio=modular_ratio,
        fct_eff_mpa=3.2,
    )
    existing_uncracked = uncracked_t_section_sls(
        1.70, 0.175, 0.30, 1.20, 6500.0, 1.10, modular_ratio, 3.2
    )
    assert uncracked.neutral_axis_from_top_mm == pytest.approx(
        existing_uncracked.neutral_axis_from_top_mm, rel=1.0e-10
    )
    assert uncracked.second_moment_mm4 == pytest.approx(
        existing_uncracked.second_moment_mm4, rel=1.0e-10
    )

    cracked = cracked_layered_section_sls(
        layers=_contiguous_t_layers(),
        steel_area_mm2=6500.0,
        steel_depth_m=1.10,
        modular_ratio=modular_ratio,
        service_moment_knm=1200.0,
    )
    existing_cracked = cracked_t_section_sls(
        1.70, 0.175, 0.30, 1.20, 6500.0, 1.10, modular_ratio, 1200.0
    )
    assert cracked.neutral_axis_from_top_mm == pytest.approx(
        existing_cracked.neutral_axis_from_top_mm, rel=1.0e-9
    )
    assert cracked.second_moment_mm4 == pytest.approx(
        existing_cracked.second_moment_mm4, rel=1.0e-9
    )
    assert cracked.steel_stress_mpa == pytest.approx(
        existing_cracked.steel_stress_mpa, rel=1.0e-9
    )


def test_nonparticipating_false_slab_gap_changes_layered_section_response() -> None:
    with_gap = (
        ConcreteSectionLayer(1.70, 0.0, 0.175, "in-situ deck"),
        ConcreteSectionLayer(0.30, 0.25, 1.20, "precast girder"),
    )
    filled = (
        ConcreteSectionLayer(1.70, 0.0, 0.25, "fully participating deck"),
        ConcreteSectionLayer(0.30, 0.25, 1.20, "precast girder"),
    )
    gap_result = layered_singly_reinforced_resistance(
        layers=with_gap, effective_depth_m=1.10, steel_area_mm2=18000.0,
        fck_mpa=35.0, fyk_mpa=500.0,
    )
    filled_result = layered_singly_reinforced_resistance(
        layers=filled, effective_depth_m=1.10, steel_area_mm2=18000.0,
        fck_mpa=35.0, fyk_mpa=500.0,
    )
    assert gap_result.resistance_knm < filled_result.resistance_knm


def test_layered_crack_width_uses_actual_bottom_tension_concrete_area() -> None:
    layers = _contiguous_t_layers()
    uncracked = uncracked_layered_section_sls(
        layers=layers, steel_area_mm2=6500.0, steel_depth_m=1.10,
        modular_ratio=200000.0 / 34000.0, fct_eff_mpa=3.2,
    )
    result = crack_width_layered_section(
        layers=layers,
        total_depth_m=1.20,
        steel_area_mm2=6500.0,
        steel_depth_m=1.10,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
        service_moment_knm=1200.0,
        cracking_moment_knm=uncracked.cracking_moment_knm,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )
    assert result.effective_tension_area_mm2 > 0.0
    assert result.crack_width_mm >= 0.0
