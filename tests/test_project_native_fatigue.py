import pytest

from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.project_native_fatigue import (
    run_project_native_flm3_grillage_search,
    run_project_t_girder_fatigue_from_native_flm3,
)


def _longitudinal() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.025,
        iy_m4=0.05,
        iz_m4=0.08,
    )


def _transverse() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.012,
        iy_m4=0.018,
        iz_m4=0.025,
    )


def _section() -> TGirderDesignInput:
    return TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.20,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )


def _search():
    return run_project_native_flm3_grillage_search(
        ProjectInput(),
        vehicle_centre_y_m=0.0,
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        movement_step_m=8.0,
        section_step_m=2.5,
    )


def test_native_flm3_full_width_search_retains_girder_range_trace() -> None:
    result = _search()

    assert result.cases
    assert len(result.girders) == 7
    centre = result.range_for_girder(4)
    assert centre.moment_range_knm > 0.0
    assert centre.maximum_moment_knm > 0.0
    assert 0.0 <= centre.section_position_m <= 15.0
    assert centre.maximum_case_id is not None
    assert centre.maximum_lead_position_m is not None
    assert "not LM1" not in result.status
    assert "FLM3" in result.status


def test_native_flm3_requires_explicit_vehicle_position_inside_carriageway() -> None:
    with pytest.raises(ValueError, match="wheel centres"):
        run_project_native_flm3_grillage_search(
            ProjectInput(),
            vehicle_centre_y_m=3.0,
            longitudinal_sections_by_span=(_longitudinal(),),
            transverse_section=_transverse(),
            transverse_stations_m=(7.5,),
            movement_step_m=8.0,
            section_step_m=2.5,
        )


def test_native_flm3_drives_ec2_t_girder_fatigue_without_lm1_substitution() -> None:
    project = ProjectInput()
    search = _search()

    result = run_project_t_girder_fatigue_from_native_flm3(
        project,
        search=search,
        girder_index=4,
        section=_section(),
        lambda_s=0.90,
        characteristic_fatigue_strength_mpa=162.5,
    )

    assert result.reference_steel_stress_range_mpa > 0.0
    assert result.maximum_total_moment_knm > result.minimum_total_moment_knm
    assert result.maximum_concrete_compression_mpa >= (
        result.minimum_concrete_compression_mpa
    )
    assert result.fatigue.concrete is not None
    assert "FLM3" in result.fatigue.source_description
    assert "not LM1" in result.status
