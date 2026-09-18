import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.project_native_fatigue import (
    run_project_native_flm3_continuous_grillage_search,
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
    shear = result.shear_range_for_girder(4)
    assert shear.shear_range_kn > 0.0
    assert shear.maximum_case_id is not None or shear.minimum_case_id is not None
    assert result.vehicle_centres_y_m == (0.0,)
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


def test_native_flm3_can_envelope_notional_lane_centre_candidates() -> None:
    result = run_project_native_flm3_grillage_search(
        ProjectInput(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        movement_step_m=15.0,
        section_step_m=5.0,
    )

    assert result.vehicle_centre_y_m is None
    assert result.vehicle_centres_y_m == pytest.approx((-2.0, -1.0, 1.0, 2.0))
    assert len({case.vehicle_centre_y_m for case in result.cases}) == 4
    assert result.range_for_girder(4).moment_range_knm > 0.0
    assert result.shear_range_for_girder(4).shear_range_kn > 0.0


def test_native_flm3_can_check_actual_shear_link_fatigue() -> None:
    project = ProjectInput()
    search = _search()
    base = _section()
    section = TGirderDesignInput(
        effective_flange_width_m=base.effective_flange_width_m,
        flange_thickness_m=base.flange_thickness_m,
        web_width_m=base.web_width_m,
        total_depth_m=base.total_depth_m,
        effective_depth_m=base.effective_depth_m,
        steel_area_mm2=base.steel_area_mm2,
        bar_diameter_mm=base.bar_diameter_mm,
        bar_spacing_mm=base.bar_spacing_mm,
        cover_mm=base.cover_mm,
        provided_shear_asw_per_s_mm2_per_m=1200.0,
    )
    result = run_project_t_girder_fatigue_from_native_flm3(
        project,
        search=search,
        girder_index=4,
        section=section,
        lambda_s=0.90,
        characteristic_fatigue_strength_mpa=162.5,
        shear_link_characteristic_fatigue_strength_mpa=162.5,
        shear_link_lambda_s=0.90,
    )

    assert result.shear_links is not None
    assert result.shear_links.traffic_range.shear_range_kn > 0.0
    assert result.shear_links.reference_link_stress_range_mpa > 0.0
    assert result.shear_links.fatigue.reference_stress_range_mpa == pytest.approx(
        result.shear_links.reference_link_stress_range_mpa
    )


def test_shear_link_fatigue_requires_actual_provided_links() -> None:
    with pytest.raises(ValueError, match="actual provided"):
        run_project_t_girder_fatigue_from_native_flm3(
            ProjectInput(),
            search=_search(),
            girder_index=4,
            section=_section(),
            lambda_s=0.90,
            characteristic_fatigue_strength_mpa=162.5,
            shear_link_characteristic_fatigue_strength_mpa=162.5,
        )



def test_continuous_native_flm3_preserves_signed_station_ranges() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )
    result = run_project_native_flm3_continuous_grillage_search(
        project,
        longitudinal_sections_by_span=(_longitudinal(), _longitudinal()),
        transverse_section=_transverse(),
        transverse_stations_m=(10.0,),
        vehicle_centre_y_m=0.0,
        movement_step_m=10.0,
        section_step_m=5.0,
    )

    assert result.cases
    assert result.total_length_m == pytest.approx(20.0)
    assert result.support_positions_m == pytest.approx((0.0, 10.0, 20.0))
    centre = result.ranges_for_girder(4)
    assert any(abs(item.x_m - 10.0) <= 1.0e-9 for item in centre)
    assert max(item.moment_range_knm for item in centre) > 0.0
    assert max(item.shear_range_kn for item in centre) > 0.0
    assert "does not certify" in result.status
