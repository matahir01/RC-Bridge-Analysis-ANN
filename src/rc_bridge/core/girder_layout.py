from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class GirderLayoutEvaluation:
    """Relationships between deck width, girder count, and uniform spacing.

    The three primary quantities remain independent editable inputs. This object
    reports their geometric consequences so a UI can guide the user without
    silently changing any project input.
    """

    deck_width_m: float
    girder_count: int
    girder_spacing_m: float
    girder_line_width_m: float
    implied_edge_overhang_m: float
    fits_deck: bool
    minimum_deck_width_m: float
    maximum_spacing_m_for_current_deck: float | None
    maximum_girder_count_for_current_spacing: int


def _validate_inputs(*, deck_width_m: float, girder_count: int, girder_spacing_m: float) -> None:
    if deck_width_m <= 0.0:
        raise ValueError("deck_width_m must be positive.")
    if girder_count < 1:
        raise ValueError("girder_count must be at least 1.")
    if girder_spacing_m <= 0.0:
        raise ValueError("girder_spacing_m must be positive.")


def evaluate_girder_layout(
    *,
    deck_width_m: float,
    girder_count: int,
    girder_spacing_m: float,
) -> GirderLayoutEvaluation:
    """Evaluate an editable uniform-girder layout without modifying its inputs."""
    deck_width = float(deck_width_m)
    count = int(girder_count)
    spacing = float(girder_spacing_m)
    _validate_inputs(
        deck_width_m=deck_width,
        girder_count=count,
        girder_spacing_m=spacing,
    )

    girder_line_width = (count - 1) * spacing
    overhang = (deck_width - girder_line_width) / 2.0
    max_spacing = None if count == 1 else deck_width / (count - 1)
    max_count = math.floor(deck_width / spacing + 1e-12) + 1

    return GirderLayoutEvaluation(
        deck_width_m=deck_width,
        girder_count=count,
        girder_spacing_m=spacing,
        girder_line_width_m=girder_line_width,
        implied_edge_overhang_m=overhang,
        fits_deck=girder_line_width <= deck_width + 1e-9,
        minimum_deck_width_m=girder_line_width,
        maximum_spacing_m_for_current_deck=max_spacing,
        maximum_girder_count_for_current_spacing=max_count,
    )


def deck_width_for_layout(
    *,
    girder_count: int,
    girder_spacing_m: float,
    edge_overhang_m: float = 0.0,
) -> float:
    """Return deck width needed for count/spacing and a chosen symmetric overhang."""
    if girder_count < 1:
        raise ValueError("girder_count must be at least 1.")
    if girder_spacing_m <= 0.0:
        raise ValueError("girder_spacing_m must be positive.")
    if edge_overhang_m < 0.0:
        raise ValueError("edge_overhang_m cannot be negative.")
    return (int(girder_count) - 1) * float(girder_spacing_m) + 2.0 * float(edge_overhang_m)


def spacing_for_layout(
    *,
    deck_width_m: float,
    girder_count: int,
    edge_overhang_m: float = 0.0,
) -> float | None:
    """Return uniform spacing that fits count into a deck with chosen edge overhang."""
    if deck_width_m <= 0.0:
        raise ValueError("deck_width_m must be positive.")
    if girder_count < 1:
        raise ValueError("girder_count must be at least 1.")
    if edge_overhang_m < 0.0:
        raise ValueError("edge_overhang_m cannot be negative.")
    usable_width = float(deck_width_m) - 2.0 * float(edge_overhang_m)
    if usable_width < 0.0:
        raise ValueError("Edge overhangs cannot exceed the deck width.")
    if girder_count == 1:
        return None
    return usable_width / (int(girder_count) - 1)
