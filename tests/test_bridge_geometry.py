import pytest

from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.core.models import BridgeGeometry, DeckConstruction


def test_reference_geometry_separates_deck_and_carriageway_widths() -> None:
    geometry = BridgeGeometry()
    assert geometry.deck_width_m == pytest.approx(11.0)
    assert geometry.carriageway_width_m == pytest.approx(7.0)

    layout = notional_lane_layout(float(geometry.carriageway_width_m))
    assert layout.lane_count == 2
    assert layout.lane_width_m == pytest.approx(3.0)
    assert layout.remaining_width_m == pytest.approx(1.0)


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
