import pytest

from rc_bridge.codes.common import LoadEffects
from rc_bridge.core.models import (
    BridgeGeometry,
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeServiceabilityInput,
)
from rc_bridge.workflow.eurocode_layered_girder import (
    LayeredGirderDesignInput,
    run_eurocode_layered_girder_case,
)
from rc_bridge.workflow.project_layered_detailing import (
    run_project_layered_girder_detailing,
)


def _profile_cases():
    return (
        (
            SectionType.RECTANGULAR,
            RectangularGirderProfile(width_m=0.45, depth_m=0.95),
        ),
        (
            SectionType.T,
            TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        ),
        (
            SectionType.I,
            IGirderProfile(
                top_flange_width_m=0.60,
                top_flange_thickness_m=0.15,
                web_width_m=0.25,
                web_depth_m=0.60,
                bottom_flange_width_m=0.55,
                bottom_flange_thickness_m=0.20,
            ),
        ),
    )


def _section() -> LayeredGirderDesignInput:
    return LayeredGirderDesignInput(
        composite_slab_width_m=1.70,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
        provided_shear_asw_per_s_mm2_per_m=1800.0,
    )


@pytest.mark.parametrize("section_type,profile", _profile_cases())
def test_layered_workflow_runs_rectangular_t_and_i_profiles(section_type, profile) -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=section_type,
            girder_profile=profile,
        )
    )
    service = EurocodeServiceabilityInput(
        service_moment_knm=700.0,
        equivalent_full_span_udl_kn_m=25.0,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )
    result = run_eurocode_layered_girder_case(
        project,
        girder_index=4,
        span_m=15.0,
        permanent_effects=LoadEffects(moment_knm=400.0, shear_kn=100.0),
        traffic_effects=LoadEffects(moment_knm=300.0, shear_kn=80.0),
        section=_section(),
        materials=EurocodeMaterialInput(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            ecm_mpa=34000.0,
            fct_eff_mpa=3.2,
        ),
        serviceability=service,
    )

    assert result.section_type == section_type
    assert result.uls_design.flexure.resistance_knm > 0.0
    assert result.uls_design.shear.design_shear_kn > 0.0
    assert result.crack.crack_width_mm >= 0.0
    assert result.deflection.interpolated_deflection_mm >= 0.0
    assert result.provided_shear is not None
    assert result.concrete_layers

    detailing = run_project_layered_girder_detailing(
        project, section=_section(), design=result
    )
    assert detailing.selected_longitudinal_bars.provided_area_mm2 > 0.0
    assert detailing.selected_links.provided_asw_per_s_mm2_per_m > 0.0
    assert detailing.effective_concrete_area_m2 > 0.0


def test_layered_workflow_preserves_noncomposite_false_slab_gap() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.45, depth_m=0.95),
        )
    )
    result = run_eurocode_layered_girder_case(
        project,
        girder_index=1,
        span_m=15.0,
        permanent_effects=LoadEffects(moment_knm=300.0, shear_kn=80.0),
        traffic_effects=LoadEffects(moment_knm=200.0, shear_kn=60.0),
        section=_section(),
        materials=EurocodeMaterialInput(
            fck_mpa=35.0, fyk_mpa=500.0, ecm_mpa=34000.0, fct_eff_mpa=3.2
        ),
        serviceability=EurocodeServiceabilityInput(
            service_moment_knm=600.0,
            equivalent_full_span_udl_kn_m=20.0,
            crack_limit_mm=0.30,
            allowable_deflection_mm=60.0,
        ),
    )
    assert result.concrete_layers[0].bottom_m == pytest.approx(0.175)
    assert result.concrete_layers[1].top_m == pytest.approx(0.25)
