import pytest

from rc_bridge.design.eurocode_cracking import (
    crack_width_ec2_t_section,
    cracked_t_section_sls,
)
from rc_bridge.design.eurocode_layered_cracking import (
    HorizontalSectionLayer,
    crack_width_ec2_layered_section,
    cracked_layered_section_sls,
)


def _positive_t_layers() -> tuple[HorizontalSectionLayer, ...]:
    return (
        HorizontalSectionLayer(
            width_m=1.70,
            start_depth_m=0.0,
            end_depth_m=0.25,
            label="deck compression flange",
        ),
        HorizontalSectionLayer(
            width_m=0.30,
            start_depth_m=0.25,
            end_depth_m=1.20,
            label="girder web",
        ),
    )


def test_layered_cracked_section_matches_existing_positive_t_solver() -> None:
    service_moment = 700.0
    modular_ratio = 200000.0 / 34000.0
    existing = cracked_t_section_sls(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_m=1.10,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment,
    )
    layered = cracked_layered_section_sls(
        _positive_t_layers(),
        total_depth_m=1.20,
        steel_area_mm2=6000.0,
        steel_depth_from_compression_face_m=1.10,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment,
        fct_eff_mpa=3.2,
    )

    assert layered.neutral_axis_from_compression_face_mm == pytest.approx(
        existing.neutral_axis_from_top_mm,
        rel=1e-9,
    )
    assert layered.second_moment_mm4 == pytest.approx(existing.second_moment_mm4, rel=1e-9)
    assert layered.steel_stress_mpa == pytest.approx(existing.steel_stress_mpa, rel=1e-9)


def test_layered_crack_width_matches_existing_positive_t_solver() -> None:
    kwargs = {
        "total_depth_m": 1.20,
        "steel_area_mm2": 6000.0,
        "bar_diameter_mm": 25.0,
        "bar_spacing_mm": 150.0,
        "cover_mm": 45.0,
        "service_moment_knm": 700.0,
        "es_mpa": 200000.0,
        "ecm_mpa": 34000.0,
        "fct_eff_mpa": 3.2,
        "crack_limit_mm": 0.30,
    }
    existing = crack_width_ec2_t_section(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        steel_depth_m=1.10,
        cracking_moment_knm=250.0,
        **kwargs,
    )
    layered = crack_width_ec2_layered_section(
        layers=_positive_t_layers(),
        steel_depth_from_compression_face_m=1.10,
        **kwargs,
    )

    assert layered.steel_stress_mpa == pytest.approx(existing.steel_stress_mpa, rel=1e-9)
    assert layered.effective_tension_depth_mm == pytest.approx(
        existing.effective_tension_depth_mm,
        rel=1e-9,
    )
    assert layered.effective_tension_area_mm2 == pytest.approx(
        existing.effective_tension_area_mm2,
        rel=1e-9,
    )
    assert layered.max_crack_spacing_mm == pytest.approx(existing.max_crack_spacing_mm, rel=1e-9)


def test_layered_support_orientation_handles_bottom_flange_web_and_deck_tension_zone() -> None:
    layers = (
        HorizontalSectionLayer(0.80, 0.00, 0.15, "bottom compression flange"),
        HorizontalSectionLayer(0.30, 0.15, 0.95, "web"),
        HorizontalSectionLayer(1.70, 0.95, 1.20, "deck tension zone"),
    )
    result = crack_width_ec2_layered_section(
        layers=layers,
        total_depth_m=1.20,
        steel_area_mm2=7500.0,
        steel_depth_from_compression_face_m=1.12,
        bar_diameter_mm=25.0,
        bar_spacing_mm=125.0,
        cover_mm=45.0,
        service_moment_knm=850.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )

    assert 0.0 < result.steel_stress_mpa
    assert 0.0 < result.effective_tension_depth_mm < 600.0
    assert result.effective_tension_area_mm2 > 0.0
    assert result.crack_width_mm >= 0.0


def test_inactive_false_slab_keeps_depth_but_is_excluded_from_tension_area() -> None:
    inactive_false_slab = (
        HorizontalSectionLayer(0.65, 0.00, 0.18, "bottom flange"),
        HorizontalSectionLayer(0.30, 0.18, 0.80, "web"),
        HorizontalSectionLayer(0.70, 0.80, 0.95, "precast top flange"),
        HorizontalSectionLayer(1.70, 0.95, 1.025, "precast false slab", active=False),
        HorizontalSectionLayer(1.70, 1.025, 1.20, "in-situ deck"),
    )
    active_false_slab = tuple(
        HorizontalSectionLayer(
            layer.width_m,
            layer.start_depth_m,
            layer.end_depth_m,
            layer.label,
            active=True,
        )
        for layer in inactive_false_slab
    )

    inactive = cracked_layered_section_sls(
        inactive_false_slab,
        total_depth_m=1.20,
        steel_area_mm2=6500.0,
        steel_depth_from_compression_face_m=1.10,
        modular_ratio=200000.0 / 34000.0,
        service_moment_knm=850.0,
        fct_eff_mpa=3.2,
    )
    active = cracked_layered_section_sls(
        active_false_slab,
        total_depth_m=1.20,
        steel_area_mm2=6500.0,
        steel_depth_from_compression_face_m=1.10,
        modular_ratio=200000.0 / 34000.0,
        service_moment_knm=850.0,
        fct_eff_mpa=3.2,
    )

    assert inactive.effective_tension_depth_mm == pytest.approx(250.0)
    assert inactive.effective_tension_area_mm2 == pytest.approx(1.70 * 1000.0 * 175.0)
    assert active.effective_tension_area_mm2 == pytest.approx(1.70 * 1000.0 * 250.0)
    assert inactive.effective_tension_area_mm2 < active.effective_tension_area_mm2
    assert inactive.gross_cracking_moment_knm != pytest.approx(active.gross_cracking_moment_knm)


def test_layered_section_rejects_noncontiguous_strips() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        cracked_layered_section_sls(
            (
                HorizontalSectionLayer(0.5, 0.0, 0.2),
                HorizontalSectionLayer(0.3, 0.3, 1.0),
            ),
            total_depth_m=1.0,
            steel_area_mm2=3000.0,
            steel_depth_from_compression_face_m=0.9,
            modular_ratio=6.0,
            service_moment_knm=300.0,
            fct_eff_mpa=3.0,
        )
