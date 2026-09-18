from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import (
    BridgeGeometry,
    GirderProfile,
    IGirderProfile,
    RectangularGirderProfile,
    TGirderProfile,
)


@dataclass(frozen=True)
class PhysicalSectionProperties:
    """Gross elastic properties derived from a physical concrete section.

    ``iy_m4`` is the second moment used for vertical bending. ``iz_m4`` is the
    plan-axis second moment. The torsion constant is a Saint-Venant rectangle-
    component approximation; it is suitable for a transparent initial grillage
    model, but not a substitute for thin-wall/cell-specific torsion modelling.
    """

    area_m2: float
    centroid_from_top_m: float
    torsion_constant_m4: float
    iy_m4: float
    iz_m4: float
    basis: str

    def __post_init__(self) -> None:
        if min(self.area_m2, self.torsion_constant_m4, self.iy_m4, self.iz_m4) <= 0.0:
            raise ValueError("Physical section area and stiffness properties must be positive.")


@dataclass(frozen=True)
class _Rectangle:
    width_m: float
    depth_m: float
    centroid_from_top_m: float

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m


def rectangular_torsion_constant_m4(width_m: float, depth_m: float) -> float:
    """Return the standard engineering approximation for a solid rectangle.

    The formula is symmetric in the supplied dimensions and remains accurate
    enough for beam-grillage property generation across practical aspect ratios.
    """
    if width_m <= 0.0 or depth_m <= 0.0:
        raise ValueError("Rectangle dimensions must be positive.")
    long_side = max(width_m, depth_m)
    short_side = min(width_m, depth_m)
    ratio = short_side / long_side
    return long_side * short_side**3 * (
        1.0 / 3.0 - 0.21 * ratio * (1.0 - ratio**4 / 12.0)
    )


def _girder_rectangles(
    profile: GirderProfile,
    *,
    top_m: float,
) -> tuple[_Rectangle, ...]:
    if isinstance(profile, RectangularGirderProfile):
        return (
            _Rectangle(
                width_m=float(profile.width_m),
                depth_m=float(profile.depth_m),
                centroid_from_top_m=top_m + float(profile.depth_m) / 2.0,
            ),
        )
    if isinstance(profile, TGirderProfile):
        flange_depth = float(profile.flange_thickness_m)
        web_depth = float(profile.total_depth_m - profile.flange_thickness_m)
        return (
            _Rectangle(
                width_m=float(profile.flange_width_m),
                depth_m=flange_depth,
                centroid_from_top_m=top_m + flange_depth / 2.0,
            ),
            _Rectangle(
                width_m=float(profile.web_width_m),
                depth_m=web_depth,
                centroid_from_top_m=top_m + flange_depth + web_depth / 2.0,
            ),
        )
    if isinstance(profile, IGirderProfile):
        top_depth = float(profile.top_flange_thickness_m)
        web_depth = float(profile.web_depth_m)
        bottom_depth = float(profile.bottom_flange_thickness_m)
        return (
            _Rectangle(
                width_m=float(profile.top_flange_width_m),
                depth_m=top_depth,
                centroid_from_top_m=top_m + top_depth / 2.0,
            ),
            _Rectangle(
                width_m=float(profile.web_width_m),
                depth_m=web_depth,
                centroid_from_top_m=top_m + top_depth + web_depth / 2.0,
            ),
            _Rectangle(
                width_m=float(profile.bottom_flange_width_m),
                depth_m=bottom_depth,
                centroid_from_top_m=(
                    top_m + top_depth + web_depth + bottom_depth / 2.0
                ),
            ),
        )
    raise TypeError("Unsupported physical girder profile.")


def _properties_from_rectangles(
    rectangles: tuple[_Rectangle, ...],
    *,
    basis: str,
) -> PhysicalSectionProperties:
    area = sum(item.area_m2 for item in rectangles)
    centroid = sum(
        item.area_m2 * item.centroid_from_top_m for item in rectangles
    ) / area
    iy = sum(
        item.width_m * item.depth_m**3 / 12.0
        + item.area_m2 * (item.centroid_from_top_m - centroid) ** 2
        for item in rectangles
    )
    iz = sum(item.depth_m * item.width_m**3 / 12.0 for item in rectangles)
    torsion = sum(
        rectangular_torsion_constant_m4(item.width_m, item.depth_m)
        for item in rectangles
    )
    return PhysicalSectionProperties(
        area_m2=area,
        centroid_from_top_m=centroid,
        torsion_constant_m4=torsion,
        iy_m4=iy,
        iz_m4=iz,
        basis=basis,
    )


def composite_girder_properties(
    geometry: BridgeGeometry,
    *,
    slab_width_m: float | None = None,
) -> PhysicalSectionProperties:
    """Derive gross composite longitudinal properties from project geometry.

    The default slab width is the mean physical deck width per girder. This
    preserves the full deck area across the grillage while remaining compatible
    with the current one-longitudinal-section-per-span model. Expert callers may
    override it with an effective or otherwise verified strip width.
    """
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Automatic longitudinal properties require a complete physical girder profile."
        )
    width = (
        float(geometry.deck_width_m) / int(geometry.girder_count)
        if slab_width_m is None
        else float(slab_width_m)
    )
    if width <= 0.0:
        raise ValueError("Longitudinal slab strip width must be positive.")
    flange_depth = float(geometry.composite_flange_depth_m)
    if flange_depth <= 0.0:
        raise ValueError("Automatic composite properties require participating deck concrete.")

    physical_deck_depth = float(geometry.physical_deck_depth_m)
    slab_centroid = (physical_deck_depth - flange_depth) + flange_depth / 2.0
    rectangles = (
        _Rectangle(width, flange_depth, slab_centroid),
        *_girder_rectangles(profile, top_m=physical_deck_depth),
    )
    source = "mean deck width/girder" if slab_width_m is None else "expert slab-width override"
    return _properties_from_rectangles(
        rectangles,
        basis=(
            f"gross composite {profile.section_type.value} girder; {source}; "
            "rectangle-component Saint-Venant J approximation"
        ),
    )


def transverse_deck_strip_properties(
    geometry: BridgeGeometry,
    *,
    strip_width_m: float,
) -> PhysicalSectionProperties:
    """Derive gross properties of a solid transverse physical deck strip."""
    width = float(strip_width_m)
    depth = float(geometry.physical_deck_depth_m)
    if width <= 0.0:
        raise ValueError("Transverse deck-strip width must be positive.")
    return _properties_from_rectangles(
        (_Rectangle(width, depth, depth / 2.0),),
        basis=(
            "gross physical deck strip; representative longitudinal strip width; "
            "solid-rectangle Saint-Venant J approximation"
        ),
    )
