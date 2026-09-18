import pytest

from rc_bridge.analysis.physical_sections import (
    composite_girder_properties,
    rectangular_torsion_constant_m4,
    transverse_deck_strip_properties,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)
from rc_bridge.workflow.grillage_verification_export import (
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)


@pytest.mark.parametrize(
    "section_type,profile",
    [
        (
            SectionType.RECTANGULAR,
            RectangularGirderProfile(width_m=0.30, depth_m=0.95),
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
                web_width_m=0.20,
                web_depth_m=0.65,
                bottom_flange_width_m=0.50,
                bottom_flange_thickness_m=0.15,
            ),
        ),
    ],
)
def test_composite_properties_are_generated_for_all_physical_profiles(
    section_type: SectionType,
    profile: RectangularGirderProfile | TGirderProfile | IGirderProfile,
) -> None:
    geometry = BridgeGeometry(section_type=section_type, girder_profile=profile)

    result = composite_girder_properties(geometry)

    expected_slab_area = 11.0 / 7.0 * 0.175
    assert result.area_m2 == pytest.approx(profile.area_m2 + expected_slab_area)
    assert 0.0 < result.centroid_from_top_m < 1.20
    assert result.iy_m4 > 0.0
    assert result.iz_m4 > 0.0
    assert result.torsion_constant_m4 > 0.0


def test_composite_properties_respect_expert_slab_width_override() -> None:
    geometry = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
    )

    result = composite_girder_properties(geometry, slab_width_m=1.70)

    assert result.area_m2 == pytest.approx(0.30 * 0.95 + 1.70 * 0.175)
    assert "expert slab-width override" in result.basis


def test_transverse_strip_matches_closed_form_rectangle_properties() -> None:
    geometry = BridgeGeometry()

    result = transverse_deck_strip_properties(geometry, strip_width_m=2.0)

    assert result.area_m2 == pytest.approx(0.50)
    assert result.iy_m4 == pytest.approx(2.0 * 0.25**3 / 12.0)
    assert result.iz_m4 == pytest.approx(0.25 * 2.0**3 / 12.0)
    assert result.torsion_constant_m4 == pytest.approx(
        rectangular_torsion_constant_m4(2.0, 0.25)
    )


def test_automatic_grillage_sections_flow_into_exact_analysis_model() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        )
    )

    model = build_project_grillage_verification_model(
        project,
        transverse_stations_m=(5.0, 10.0),
        load_case=GrillageVerificationLoadCase(name="physical properties"),
    )

    expected_longitudinal = composite_girder_properties(project.geometry)
    expected_transverse = transverse_deck_strip_properties(
        project.geometry,
        strip_width_m=5.0,
    )
    assert model.sections[0].area_m2 == pytest.approx(expected_longitudinal.area_m2)
    assert model.sections[0].iy_m4 == pytest.approx(expected_longitudinal.iy_m4)
    assert model.sections[1].area_m2 == pytest.approx(expected_transverse.area_m2)
    assert "gross composite" in model.metadata["longitudinal_stiffness_basis"]
    assert "gross physical deck strip" in model.metadata["transverse_stiffness_basis"]


def test_explicit_grillage_sections_remain_expert_overrides() -> None:
    project = ProjectInput()
    longitudinal = GrillageSectionProperties("L", 0.5, 0.02, 0.03, 0.04)
    transverse = GrillageSectionProperties("T", 0.2, 0.01, 0.02, 0.03)

    model = build_project_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(longitudinal,),
        transverse_section=transverse,
        transverse_stations_m=(5.0, 10.0),
        load_case=GrillageVerificationLoadCase(name="overrides"),
    )

    assert model.sections[0].area_m2 == pytest.approx(0.5)
    assert model.sections[1].area_m2 == pytest.approx(0.2)
    assert "expert override" in model.metadata["longitudinal_stiffness_basis"]
    assert "expert override" in model.metadata["transverse_stiffness_basis"]


def test_automatic_longitudinal_properties_require_physical_profile() -> None:
    with pytest.raises(ValueError, match="physical girder profile"):
        build_project_grillage_verification_model(
            ProjectInput(),
            transverse_stations_m=(5.0, 10.0),
            load_case=GrillageVerificationLoadCase(name="missing profile"),
        )
