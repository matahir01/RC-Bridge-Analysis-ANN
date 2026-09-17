import pytest

from rc_bridge.analysis.layered_sections import (
    ConcreteLayer,
    cracked_layered_section_sls,
    layered_effective_tension_area_from_top_mm2,
    layered_total_depth_m,
)
from rc_bridge.design.eurocode_cracking import cracked_t_section_sls


def test_single_width_layer_matches_existing_rectangular_cracked_section() -> None:
    modular_ratio = 200000.0 / 34000.0
    existing = cracked_t_section_sls(
        effective_flange_width_m=0.30,
        flange_thickness_m=0.20,
        web_width_m=0.30,
        total_depth_m=1.00,
        steel_area_mm2=4000.0,
        steel_depth_m=0.95,
        modular_ratio=modular_ratio,
        service_moment_knm=500.0,
    )
    layered = cracked_layered_section_sls(
        (ConcreteLayer(width_m=0.30, thickness_m=1.00, label="rectangular concrete"),),
        steel_area_mm2=4000.0,
        steel_depth_from_bottom_m=0.95,
        modular_ratio=modular_ratio,
        service_moment_knm=500.0,
    )

    assert layered.neutral_axis_from_bottom_mm == pytest.approx(
        existing.neutral_axis_from_top_mm,
        rel=1e-10,
    )
    assert layered.second_moment_mm4 == pytest.approx(existing.second_moment_mm4, rel=1e-10)
    assert layered.steel_stress_mpa == pytest.approx(existing.steel_stress_mpa, rel=1e-10)


def test_i_girder_and_deck_layers_preserve_physical_depth_and_inactive_false_slab() -> None:
    layers = (
        ConcreteLayer(0.65, 0.18, "bottom flange"),
        ConcreteLayer(0.30, 0.62, "web"),
        ConcreteLayer(0.70, 0.15, "precast top flange"),
        ConcreteLayer(1.70, 0.075, "precast false slab", active=False),
        ConcreteLayer(1.70, 0.175, "in-situ deck"),
    )

    assert layered_total_depth_m(layers) == pytest.approx(1.20)
    result = cracked_layered_section_sls(
        layers,
        steel_area_mm2=6500.0,
        steel_depth_from_bottom_m=1.14,
        modular_ratio=200000.0 / 34000.0,
        service_moment_knm=900.0,
    )

    assert 0.0 < result.neutral_axis_from_bottom_mm < 1140.0
    assert result.second_moment_mm4 > 0.0
    assert result.steel_stress_mpa > 0.0
    assert "precast false slab" not in result.active_compression_layers


def test_effective_top_tension_area_ignores_inactive_layer_but_keeps_geometry() -> None:
    layers = (
        ConcreteLayer(0.65, 0.18, "bottom flange"),
        ConcreteLayer(0.30, 0.62, "web"),
        ConcreteLayer(0.70, 0.15, "precast top flange"),
        ConcreteLayer(1.70, 0.075, "precast false slab", active=False),
        ConcreteLayer(1.70, 0.175, "in-situ deck"),
    )

    top_150 = layered_effective_tension_area_from_top_mm2(layers, tension_depth_mm=150.0)
    top_200 = layered_effective_tension_area_from_top_mm2(layers, tension_depth_mm=200.0)

    assert top_150 == pytest.approx(1.70 * 1000.0 * 150.0)
    assert top_200 == pytest.approx(1.70 * 1000.0 * 175.0)
    assert top_200 == pytest.approx(top_150 + 1.70 * 1000.0 * 25.0)
