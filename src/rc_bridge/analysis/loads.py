from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UniformLoad:
    magnitude_kn_m: float
    label: str = "UDL"

    def __post_init__(self) -> None:
        if self.magnitude_kn_m < 0:
            raise ValueError("Uniform load magnitude cannot be negative.")


@dataclass(frozen=True)
class PointLoad:
    magnitude_kn: float
    position_m: float
    label: str = "Point load"

    def __post_init__(self) -> None:
        if self.magnitude_kn < 0:
            raise ValueError("Point load magnitude cannot be negative.")
        if self.position_m < 0:
            raise ValueError("Point-load position cannot be negative.")


def section_self_weight_kn_m(
    area_m2: float,
    concrete_density_kn_m3: float = 25.0,
) -> float:
    """Self-weight line load from the physical concrete section area."""
    if area_m2 <= 0.0 or concrete_density_kn_m3 <= 0.0:
        raise ValueError("Section area and concrete density must be positive.")
    return area_m2 * concrete_density_kn_m3


def deck_self_weight_per_girder_kn_m(
    deck_thickness_m: float,
    girder_spacing_m: float,
    concrete_density_kn_m3: float = 25.0,
) -> float:
    """Tributary deck self-weight carried by an internal girder.

    This is a deterministic geometric calculation only. Edge-girder tributary
    widths and transverse distribution are handled separately.
    """
    if deck_thickness_m <= 0 or girder_spacing_m <= 0 or concrete_density_kn_m3 <= 0:
        raise ValueError("Deck thickness, spacing and density must be positive.")
    return deck_thickness_m * girder_spacing_m * concrete_density_kn_m3


def line_load_from_area_pressure_kn_m(
    pressure_kn_m2: float,
    tributary_width_m: float,
) -> float:
    if pressure_kn_m2 < 0 or tributary_width_m <= 0:
        raise ValueError("Pressure must be non-negative and tributary width positive.")
    return pressure_kn_m2 * tributary_width_m
