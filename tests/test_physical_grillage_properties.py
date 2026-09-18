import pytest

from rc_bridge.analysis.physical_sections import (
    composite_concrete_layers,
    composite_girder_properties,
    deck_construction_girder_properties,
    girder_tributary_slab_widths_m,
    precast_girder_properties,
    rectangular_torsion_constant_m4,
    station_tributary_strip_widths_m,
    transverse_deck_strip_properties,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    DeckConstruction,
    IGirderProfile,
    PermanentActionStage,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)
from rc_bridge.workflow.grillage_verification_export import (
    GrillageSectionProperties,
    GrillageStiffnessModifiers,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
    service_grillage_stiffness_modifiers,
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


def test_edge_aware_girder_strips_recover_exact_deck_width() -> None:
    widths = girder_tributary_slab_widths_m(BridgeGeometry())

    assert widths == pytest.approx((1.25, 1.70, 1.70, 1.70, 1.70, 1.70, 1.25))
    assert sum(widths) == pytest.approx(11.0)


def test_station_strip_widths_recover_length_for_nonuniform_grid() -> None:
    widths = station_tributary_strip_widths_m((0.0, 2.0, 7.0, 15.0))

    assert widths == pytest.approx((1.0, 3.5, 6.5, 4.0))
    assert sum(widths) == pytest.approx(15.0)


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

    edge_longitudinal = composite_girder_properties(
        project.geometry,
        slab_width_m=1.25,
    )
    internal_longitudinal = composite_girder_properties(
        project.geometry,
        slab_width_m=1.70,
    )
    end_transverse = transverse_deck_strip_properties(
        project.geometry,
        strip_width_m=2.5,
    )
    internal_transverse = transverse_deck_strip_properties(
        project.geometry,
        strip_width_m=5.0,
    )
    assert len(model.sections) == 11
    assert model.sections[0].area_m2 == pytest.approx(edge_longitudinal.area_m2)
    assert model.sections[1].iy_m4 == pytest.approx(internal_longitudinal.iy_m4)
    assert model.sections[6].area_m2 == pytest.approx(edge_longitudinal.area_m2)
    assert model.sections[7].area_m2 == pytest.approx(end_transverse.area_m2)
    assert model.sections[8].area_m2 == pytest.approx(internal_transverse.area_m2)
    assert model.sections[10].area_m2 == pytest.approx(end_transverse.area_m2)
    assert "gross composite" in model.metadata["longitudinal_stiffness_basis"]
    assert "edge-aware" in model.metadata["longitudinal_stiffness_basis"]
    assert "station-specific" in model.metadata["transverse_stiffness_basis"]

    longitudinal_beams = model.beams[:21]
    assert [beam.section_id for beam in longitudinal_beams[:7]] == list(range(1, 8))
    assert [beam.section_id for beam in longitudinal_beams[7:14]] == list(range(1, 8))
    transverse_beams = model.beams[21:]
    assert {beam.section_id for beam in transverse_beams[:8]} == {8}
    assert {beam.section_id for beam in transverse_beams[8:16]} == {9}


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


def test_explicit_stiffness_modifiers_scale_vertical_bending_and_torsion() -> None:
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
    gross = build_project_grillage_verification_model(
        project,
        transverse_stations_m=(7.5,),
        load_case=GrillageVerificationLoadCase(name="gross"),
    )
    modified = build_project_grillage_verification_model(
        project,
        transverse_stations_m=(7.5,),
        load_case=GrillageVerificationLoadCase(name="modified"),
        stiffness_modifiers=GrillageStiffnessModifiers(
            longitudinal_bending_factors_by_span=(0.60,),
            longitudinal_torsion_factors_by_span=(0.75,),
            transverse_bending_factor=0.50,
            transverse_torsion_factor=0.80,
            basis="test explicit modifiers",
        ),
    )

    assert modified.sections[0].iy_m4 == pytest.approx(0.60 * gross.sections[0].iy_m4)
    assert modified.sections[0].torsion_constant_m4 == pytest.approx(
        0.75 * gross.sections[0].torsion_constant_m4
    )
    first_transverse = 7
    assert modified.sections[first_transverse].iy_m4 == pytest.approx(
        0.50 * gross.sections[first_transverse].iy_m4
    )
    assert modified.sections[first_transverse].torsion_constant_m4 == pytest.approx(
        0.80 * gross.sections[first_transverse].torsion_constant_m4
    )
    assert modified.metadata["stiffness_modifier_basis"] == "test explicit modifiers"


def test_service_stiffness_helper_requires_explicit_cracked_ratios_and_creep() -> None:
    modifiers = service_grillage_stiffness_modifiers(
        span_count=2,
        creep_coefficient=1.0,
        longitudinal_cracked_inertia_ratios_by_span=(0.60, 0.50),
        transverse_cracked_inertia_ratio=0.40,
    )

    assert modifiers.longitudinal_bending_factors_by_span == pytest.approx((0.30, 0.25))
    assert modifiers.transverse_bending_factor == pytest.approx(0.20)
    assert "cracked/creep-adjusted" in modifiers.basis

    with pytest.raises(ValueError, match="per span"):
        service_grillage_stiffness_modifiers(
            span_count=2,
            creep_coefficient=1.0,
            longitudinal_cracked_inertia_ratios_by_span=(0.60,),
            transverse_cracked_inertia_ratio=0.40,
        )

def test_noncomposite_false_slab_preserves_physical_vertical_order() -> None:
    geometry = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
    )
    layers = composite_concrete_layers(geometry, slab_width_m=1.70)

    assert layers[0].label == "composite in-situ deck slab"
    assert layers[0].top_m == pytest.approx(0.0)
    assert layers[0].bottom_m == pytest.approx(0.175)
    assert layers[1].label == "precast rectangular girder"
    assert layers[1].top_m == pytest.approx(0.25)
    assert layers[1].bottom_m == pytest.approx(1.20)

    result = composite_girder_properties(geometry, slab_width_m=1.70)
    slab_area = 1.70 * 0.175
    girder_area = 0.30 * 0.95
    expected_centroid = (
        slab_area * 0.0875 + girder_area * (0.25 + 0.95 / 2.0)
    ) / (slab_area + girder_area)
    assert result.centroid_from_top_m == pytest.approx(expected_centroid)


def test_false_slab_participates_only_when_explicitly_enabled() -> None:
    geometry = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
        deck_construction=DeckConstruction(
            false_slab_composite_participation=True,
        ),
    )
    layers = composite_concrete_layers(geometry, slab_width_m=1.70)

    assert [layer.label for layer in layers[:2]] == [
        "composite in-situ deck slab",
        "composite precast false slab",
    ]
    assert layers[1].top_m == pytest.approx(0.175)
    assert layers[1].bottom_m == pytest.approx(0.25)
    result = composite_girder_properties(geometry, slab_width_m=1.70)
    assert result.area_m2 == pytest.approx(0.30 * 0.95 + 1.70 * 0.25)


def test_precast_girder_properties_exclude_deck_build_up() -> None:
    geometry = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
    )
    result = precast_girder_properties(geometry)

    assert result.area_m2 == pytest.approx(0.30 * 0.95)
    assert result.centroid_from_top_m == pytest.approx(0.475)
    assert "gross precast rectangular" in result.basis


def test_precast_automatic_stage_uses_girder_only_and_requires_transverse_override() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        )
    )
    with pytest.raises(ValueError, match="Automatic transverse deck stiffness"):
        build_project_grillage_verification_model(
            project,
            transverse_stations_m=(7.5,),
            load_case=GrillageVerificationLoadCase(name="precast no diaphragm"),
            automatic_section_stage=PermanentActionStage.PRECAST_GIRDER,
        )

    diaphragm = GrillageSectionProperties("Verified diaphragm", 0.20, 0.01, 0.02, 0.03)
    model = build_project_grillage_verification_model(
        project,
        transverse_section=diaphragm,
        transverse_stations_m=(7.5,),
        load_case=GrillageVerificationLoadCase(name="precast with diaphragm"),
        automatic_section_stage=PermanentActionStage.PRECAST_GIRDER,
    )
    expected = precast_girder_properties(project.geometry)
    assert model.sections[0].area_m2 == pytest.approx(expected.area_m2)
    assert model.sections[0].iy_m4 == pytest.approx(expected.iy_m4)
    assert model.metadata["automatic_section_stage"] == "precast_girder"
    assert "gross precast" in model.metadata["longitudinal_stiffness_basis"]


def test_deck_construction_stage_never_credits_wet_in_situ_slab() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
        )
    )
    diaphragm = GrillageSectionProperties("Verified construction tie", 0.20, 0.01, 0.02, 0.03)
    model = build_project_grillage_verification_model(
        project,
        transverse_section=diaphragm,
        transverse_stations_m=(7.5,),
        load_case=GrillageVerificationLoadCase(name="wet deck"),
        automatic_section_stage=PermanentActionStage.DECK_CONSTRUCTION,
    )
    expected = precast_girder_properties(project.geometry)
    final = composite_girder_properties(project.geometry, slab_width_m=1.70)
    assert model.sections[1].area_m2 == pytest.approx(expected.area_m2)
    assert model.sections[1].area_m2 < final.area_m2
    assert model.metadata["automatic_section_stage"] == "deck_construction"


def test_false_slab_construction_stiffness_requires_explicit_project_and_stage_opt_in() -> None:
    geometry = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
    )
    with pytest.raises(ValueError, match="does not declare"):
        deck_construction_girder_properties(
            geometry,
            slab_width_m=1.70,
            false_slab_participates=True,
        )

    participating = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
        deck_construction=DeckConstruction(false_slab_composite_participation=True),
    )
    result = deck_construction_girder_properties(
        participating,
        slab_width_m=1.70,
        false_slab_participates=True,
    )
    precast = precast_girder_properties(participating)
    final = composite_girder_properties(participating, slab_width_m=1.70)
    assert result.area_m2 == pytest.approx(precast.area_m2 + 1.70 * 0.075)
    assert result.area_m2 < final.area_m2
    assert "wet in-situ concrete excluded" in result.basis
