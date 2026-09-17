import pytest

from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.core.models import (
    BridgeGeometry,
    DeckConstruction,
    IGirderProfile,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)


def test_reference_geometry_separates_deck_and_carriageway_widths() -> None:
    geometry = BridgeGeometry()
    assert geometry.deck_width_m == pytest.approx(11.0)
    assert geometry.carriageway_width_m == pytest.approx(7.0)

    layout = notional_lane_layout(float(geometry.carriageway_width_m))
    assert layout.lane_count == 2
    assert layout.lane_width_m == pytest.approx(3.0)
    assert layout.remaining_width_m == pytest.approx(1.0)


def test_reference_girder_layout_matches_11m_deck() -> None:
    geometry = BridgeGeometry()
    assert geometry.girder_line_width_m == pytest.approx(10.2)
    assert geometry.nominal_edge_overhang_m == pytest.approx(0.4)


def test_girder_count_and_spacing_are_independently_editable() -> None:
    geometry = BridgeGeometry(
        deck_width_m=11.0,
        girder_count=8,
        girder_spacing_m=1.40,
    )

    assert geometry.girder_count == 8
    assert geometry.girder_spacing_m == pytest.approx(1.40)
    assert geometry.girder_line_width_m == pytest.approx(9.80)
    assert geometry.nominal_edge_overhang_m == pytest.approx(0.60)


def test_editable_girder_count_and_spacing_still_respect_deck_width() -> None:
    with pytest.raises(ValueError, match="outside the deck width"):
        BridgeGeometry(
            deck_width_m=11.0,
            girder_count=8,
            girder_spacing_m=1.70,
        )


def test_girder_layout_cannot_extend_beyond_deck_width() -> None:
    with pytest.raises(ValueError, match="outside the deck width"):
        BridgeGeometry(
            deck_width_m=10.0,
            girder_count=7,
            girder_spacing_m=1.70,
        )


def test_reference_geometry_does_not_invent_physical_girder_profile() -> None:
    geometry = BridgeGeometry()
    assert geometry.girder_profile is None
    assert geometry.girder_profile_area_m2 is None


def test_rectangular_t_and_i_profiles_compute_physical_area() -> None:
    rectangular = BridgeGeometry(
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
    )
    assert rectangular.girder_profile_area_m2 == pytest.approx(0.285)

    t_girder = BridgeGeometry(
        section_type=SectionType.T,
        girder_profile=TGirderProfile(
            flange_width_m=0.70,
            flange_thickness_m=0.15,
            web_width_m=0.30,
            total_depth_m=0.95,
        ),
    )
    assert t_girder.girder_profile_area_m2 == pytest.approx(0.345)

    i_girder = BridgeGeometry(
        section_type=SectionType.I,
        girder_profile=IGirderProfile(
            top_flange_width_m=0.60,
            top_flange_thickness_m=0.15,
            web_width_m=0.20,
            web_depth_m=0.65,
            bottom_flange_width_m=0.50,
            bottom_flange_thickness_m=0.15,
        ),
    )
    assert i_girder.girder_profile_area_m2 == pytest.approx(0.295)


def test_physical_profile_must_match_section_type_and_depth() -> None:
    with pytest.raises(ValueError, match="shape must match"):
        BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.95),
        )

    with pytest.raises(ValueError, match="profile depth"):
        BridgeGeometry(
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.30, depth_m=0.90),
        )


def test_false_slab_is_physical_depth_but_not_composite_by_default() -> None:
    geometry = BridgeGeometry()
    assert geometry.physical_deck_depth_m == pytest.approx(0.25)
    assert geometry.composite_flange_depth_m == pytest.approx(0.175)


def test_false_slab_can_only_join_flange_when_explicitly_enabled() -> None:
    geometry = BridgeGeometry(
        deck_construction=DeckConstruction(
            precast_false_slab_depth_m=0.075,
            in_situ_slab_depth_m=0.175,
            false_slab_composite_participation=True,
        )
    )
    assert geometry.composite_flange_depth_m == pytest.approx(0.25)


def test_physical_deck_depth_must_match_component_build_up() -> None:
    with pytest.raises(ValueError):
        BridgeGeometry(
            deck_structural_depth_m=0.30,
            deck_construction=DeckConstruction(
                precast_false_slab_depth_m=0.075,
                in_situ_slab_depth_m=0.175,
            ),
        )
