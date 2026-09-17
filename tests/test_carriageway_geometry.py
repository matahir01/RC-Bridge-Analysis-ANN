import pytest

from rc_bridge.core.models import BridgeGeometry


def test_centered_reference_carriageway_edges() -> None:
    geometry = BridgeGeometry()
    assert geometry.carriageway_offset_m == pytest.approx(0.0)
    assert geometry.carriageway_left_edge_m == pytest.approx(-3.5)
    assert geometry.carriageway_right_edge_m == pytest.approx(3.5)


def test_carriageway_offset_is_independently_editable() -> None:
    geometry = BridgeGeometry(
        deck_width_m=11.0,
        carriageway_width_m=7.0,
        carriageway_offset_m=1.0,
    )
    assert geometry.carriageway_left_edge_m == pytest.approx(-2.5)
    assert geometry.carriageway_right_edge_m == pytest.approx(4.5)


def test_carriageway_offset_cannot_move_roadway_outside_deck() -> None:
    with pytest.raises(ValueError, match="outside the physical deck width"):
        BridgeGeometry(
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            carriageway_offset_m=2.1,
        )
