import pytest

from rc_bridge.core.girder_layout import (
    deck_width_for_layout,
    evaluate_girder_layout,
    spacing_for_layout,
)
from rc_bridge.core.models import BridgeGeometry


def test_layout_evaluation_links_count_spacing_and_deck_width() -> None:
    layout = evaluate_girder_layout(
        deck_width_m=11.0,
        girder_count=8,
        girder_spacing_m=1.40,
    )

    assert layout.fits_deck is True
    assert layout.girder_line_width_m == pytest.approx(9.80)
    assert layout.implied_edge_overhang_m == pytest.approx(0.60)
    assert layout.minimum_deck_width_m == pytest.approx(9.80)
    assert layout.maximum_spacing_m_for_current_deck == pytest.approx(11.0 / 7.0)
    assert layout.maximum_girder_count_for_current_spacing == 8


def test_conflicting_layout_reports_both_deck_and_spacing_options() -> None:
    layout = evaluate_girder_layout(
        deck_width_m=11.0,
        girder_count=8,
        girder_spacing_m=1.70,
    )

    assert layout.fits_deck is False
    assert layout.minimum_deck_width_m == pytest.approx(11.90)
    assert layout.maximum_spacing_m_for_current_deck == pytest.approx(11.0 / 7.0)
    assert layout.implied_edge_overhang_m == pytest.approx(-0.45)

    with pytest.raises(ValueError) as exc_info:
        BridgeGeometry(deck_width_m=11.0, girder_count=8, girder_spacing_m=1.70)

    message = str(exc_info.value)
    assert "requires at least 11.900 m deck width" in message
    assert "reduce girder_spacing_m to at most 1.571 m" in message
    assert "independently editable inputs" in message


def test_deck_width_can_be_increased_without_changing_count_or_spacing() -> None:
    geometry = BridgeGeometry(
        deck_width_m=12.70,
        girder_count=8,
        girder_spacing_m=1.70,
    )

    assert geometry.girder_count == 8
    assert geometry.girder_spacing_m == pytest.approx(1.70)
    assert geometry.girder_line_width_m == pytest.approx(11.90)
    assert geometry.nominal_edge_overhang_m == pytest.approx(0.40)


def test_layout_helpers_work_in_both_editing_directions() -> None:
    required_width = deck_width_for_layout(
        girder_count=8,
        girder_spacing_m=1.70,
        edge_overhang_m=0.40,
    )
    assert required_width == pytest.approx(12.70)

    spacing = spacing_for_layout(
        deck_width_m=11.0,
        girder_count=8,
        edge_overhang_m=0.40,
    )
    assert spacing == pytest.approx(10.20 / 7.0)


def test_bridge_geometry_exposes_linked_layout_guidance() -> None:
    geometry = BridgeGeometry(deck_width_m=11.0, girder_count=8, girder_spacing_m=1.40)

    assert geometry.minimum_deck_width_m_for_current_layout == pytest.approx(9.80)
    assert geometry.maximum_spacing_m_for_current_deck == pytest.approx(11.0 / 7.0)
    assert geometry.maximum_girder_count_for_current_spacing == 8
