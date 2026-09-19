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
class CompositeSectionDescription:
    """Human-readable structural interpretation of the final composite girder.

    The physical precast profile remains unchanged for construction-stage checks.
    This description identifies the final composite form created when participating
    deck concrete acts with that precast profile.
    """

    precast_section_type: str
    final_section_form: str
    flange_width_m: float
    participating_flange_depth_m: float
    web_width_m: float
    precast_depth_m: float
    physical_deck_depth_m: float
    overall_depth_m: float
    slab_width_basis: str
    false_slab_weight_only: bool

    def __post_init__(self) -> None:
        if min(
            self.flange_width_m,
            self.participating_flange_depth_m,
            self.web_width_m,
            self.precast_depth_m,
            self.physical_deck_depth_m,
            self.overall_depth_m,
        ) <= 0.0:
            raise ValueError("Composite section dimensions must be positive.")
        if not self.final_section_form.strip() or not self.slab_width_basis.strip():
            raise ValueError("Composite section description text cannot be empty.")


@dataclass(frozen=True)
class ConcreteSectionLayer:
    """One non-overlapping concrete width band in a longitudinal section."""

    width_m: float
    top_m: float
    bottom_m: float
    label: str

    def __post_init__(self) -> None:
        if self.width_m <= 0.0:
            raise ValueError("Concrete layer width must be positive.")
        if self.top_m < 0.0 or self.bottom_m <= self.top_m:
            raise ValueError("Concrete layer vertical bounds are invalid.")
        if not self.label.strip():
            raise ValueError("Concrete layer label cannot be empty.")

    @property
    def depth_m(self) -> float:
        return self.bottom_m - self.top_m

    @property
    def centroid_from_top_m(self) -> float:
        return 0.5 * (self.top_m + self.bottom_m)

    @property
    def area_m2(self) -> float:
        return self.width_m * self.depth_m


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


def _girder_layers(
    profile: GirderProfile,
    *,
    top_m: float,
) -> tuple[ConcreteSectionLayer, ...]:
    if isinstance(profile, RectangularGirderProfile):
        depth = float(profile.depth_m)
        return (
            ConcreteSectionLayer(
                width_m=float(profile.width_m),
                top_m=top_m,
                bottom_m=top_m + depth,
                label="precast rectangular girder",
            ),
        )
    if isinstance(profile, TGirderProfile):
        flange_depth = float(profile.flange_thickness_m)
        total_depth = float(profile.total_depth_m)
        return (
            ConcreteSectionLayer(
                width_m=float(profile.flange_width_m),
                top_m=top_m,
                bottom_m=top_m + flange_depth,
                label="precast T-girder top flange",
            ),
            ConcreteSectionLayer(
                width_m=float(profile.web_width_m),
                top_m=top_m + flange_depth,
                bottom_m=top_m + total_depth,
                label="precast T-girder web",
            ),
        )
    if isinstance(profile, IGirderProfile):
        top_depth = float(profile.top_flange_thickness_m)
        web_depth = float(profile.web_depth_m)
        bottom_depth = float(profile.bottom_flange_thickness_m)
        z1 = top_m + top_depth
        z2 = z1 + web_depth
        return (
            ConcreteSectionLayer(
                width_m=float(profile.top_flange_width_m),
                top_m=top_m,
                bottom_m=z1,
                label="precast I-girder top flange",
            ),
            ConcreteSectionLayer(
                width_m=float(profile.web_width_m),
                top_m=z1,
                bottom_m=z2,
                label="precast I-girder web",
            ),
            ConcreteSectionLayer(
                width_m=float(profile.bottom_flange_width_m),
                top_m=z2,
                bottom_m=z2 + bottom_depth,
                label="precast I-girder bottom flange",
            ),
        )
    raise TypeError("Unsupported physical girder profile.")


def _girder_rectangles(
    profile: GirderProfile,
    *,
    top_m: float,
) -> tuple[_Rectangle, ...]:
    return tuple(
        _Rectangle(
            width_m=layer.width_m,
            depth_m=layer.depth_m,
            centroid_from_top_m=layer.centroid_from_top_m,
        )
        for layer in _girder_layers(profile, top_m=top_m)
    )

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


def precast_concrete_layers(
    geometry: BridgeGeometry,
) -> tuple[ConcreteSectionLayer, ...]:
    """Return the physical precast-girder concrete layers from its own top face."""

    profile = geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Precast concrete layers require a complete physical girder profile."
        )
    return _girder_layers(profile, top_m=0.0)


def precast_girder_properties(geometry: BridgeGeometry) -> PhysicalSectionProperties:
    """Return gross elastic properties of the precast girder alone."""
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError("Precast girder properties require a complete physical girder profile.")
    return _properties_from_rectangles(
        _girder_rectangles(profile, top_m=0.0),
        basis=(
            f"gross precast {profile.section_type.value} girder; "
            "rectangle-component Saint-Venant J approximation"
        ),
    )


def deck_construction_girder_properties(
    geometry: BridgeGeometry,
    *,
    slab_width_m: float,
    false_slab_participates: bool = False,
) -> PhysicalSectionProperties:
    """Return longitudinal stiffness while the in-situ deck concrete is not hardened.

    The wet in-situ slab is never credited to stiffness in this construction
    state. By default the precast false slab is also weight-only. It may be
    included only when the caller explicitly requests it and the project
    geometry itself declares verified false-slab composite participation.
    """
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Deck-construction properties require a complete physical girder profile."
        )
    width = float(slab_width_m)
    if width <= 0.0:
        raise ValueError("Deck-construction slab strip width must be positive.")
    if not false_slab_participates:
        return precast_girder_properties(geometry)
    if not geometry.deck_construction.false_slab_composite_participation:
        raise ValueError(
            "False-slab construction-stage stiffness was requested, but the project "
            "does not declare false_slab_composite_participation=True."
        )

    false_depth = float(geometry.deck_construction.precast_false_slab_depth_m)
    layers = (
        ConcreteSectionLayer(
            width_m=width,
            top_m=0.0,
            bottom_m=false_depth,
            label="construction-stage composite precast false slab",
        ),
        *_girder_layers(profile, top_m=false_depth),
    )
    return _properties_from_rectangles(
        tuple(
            _Rectangle(
                width_m=layer.width_m,
                depth_m=layer.depth_m,
                centroid_from_top_m=layer.centroid_from_top_m,
            )
            for layer in layers
        ),
        basis=(
            f"deck-construction {profile.section_type.value} girder with explicitly "
            "participating precast false slab; wet in-situ concrete excluded; "
            "rectangle-component Saint-Venant J approximation"
        ),
    )

def composite_concrete_layers(
    geometry: BridgeGeometry,
    *,
    slab_width_m: float,
) -> tuple[ConcreteSectionLayer, ...]:
    """Return participating longitudinal layers in their physical vertical order.

    The in-situ slab is above the precast false slab. A false slab excluded
    from composite action remains permanent weight only. The precast girder
    begins below the complete physical deck build-up.
    """
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Automatic longitudinal properties require a complete physical girder profile."
        )
    width = float(slab_width_m)
    if width <= 0.0:
        raise ValueError("Longitudinal slab strip width must be positive.")
    deck = geometry.deck_construction
    in_situ_depth = float(deck.in_situ_slab_depth_m)
    false_slab_depth = float(deck.precast_false_slab_depth_m)
    physical_deck_depth = in_situ_depth + false_slab_depth
    layers: list[ConcreteSectionLayer] = []
    if deck.in_situ_slab_composite_participation:
        layers.append(
            ConcreteSectionLayer(
                width_m=width,
                top_m=0.0,
                bottom_m=in_situ_depth,
                label="composite in-situ deck slab",
            )
        )
    if deck.false_slab_composite_participation:
        layers.append(
            ConcreteSectionLayer(
                width_m=width,
                top_m=in_situ_depth,
                bottom_m=physical_deck_depth,
                label="composite precast false slab",
            )
        )
    layers.extend(_girder_layers(profile, top_m=physical_deck_depth))
    return tuple(layers)


def composite_section_description(
    geometry: BridgeGeometry,
    *,
    slab_width_m: float | None = None,
    slab_width_basis: str | None = None,
) -> CompositeSectionDescription:
    """Describe the final composite section without changing the precast profile.

    A rectangular precast girder with a participating deck flange is classified
    as a composite T-section. Construction-stage analysis continues to use the
    original rectangular precast section until the deck is structurally active.
    """
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Composite section description requires a complete physical girder profile."
        )
    width = (
        float(geometry.deck_width_m) / int(geometry.girder_count)
        if slab_width_m is None
        else float(slab_width_m)
    )
    if width <= 0.0:
        raise ValueError("Composite flange width must be positive.")
    flange_depth = float(geometry.composite_flange_depth_m)
    if flange_depth <= 0.0:
        raise ValueError("Composite section description requires participating deck concrete.")

    if isinstance(profile, RectangularGirderProfile):
        final_form = "T"
        web_width = float(profile.width_m)
    elif isinstance(profile, TGirderProfile):
        final_form = "deck-flanged T"
        web_width = float(profile.web_width_m)
    elif isinstance(profile, IGirderProfile):
        final_form = "deck-flanged I"
        web_width = float(profile.web_width_m)
    else:
        raise TypeError("Unsupported physical girder profile.")

    source = (
        "mean deck width/girder"
        if slab_width_m is None
        else slab_width_basis or "expert slab-width override"
    )
    return CompositeSectionDescription(
        precast_section_type=profile.section_type.value,
        final_section_form=final_form,
        flange_width_m=width,
        participating_flange_depth_m=flange_depth,
        web_width_m=web_width,
        precast_depth_m=float(profile.total_depth_m),
        physical_deck_depth_m=float(geometry.physical_deck_depth_m),
        overall_depth_m=float(geometry.physical_deck_depth_m + profile.total_depth_m),
        slab_width_basis=source,
        false_slab_weight_only=(
            not geometry.deck_construction.false_slab_composite_participation
        ),
    )


def composite_girder_properties(
    geometry: BridgeGeometry,
    *,
    slab_width_m: float | None = None,
    slab_width_basis: str | None = None,
) -> PhysicalSectionProperties:
    """Derive gross composite longitudinal properties from project geometry."""
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
    if float(geometry.composite_flange_depth_m) <= 0.0:
        raise ValueError("Automatic composite properties require participating deck concrete.")
    layers = composite_concrete_layers(geometry, slab_width_m=width)
    rectangles = tuple(
        _Rectangle(
            width_m=layer.width_m,
            depth_m=layer.depth_m,
            centroid_from_top_m=layer.centroid_from_top_m,
        )
        for layer in layers
    )
    description = composite_section_description(
        geometry,
        slab_width_m=width,
        slab_width_basis=slab_width_basis,
    )
    return _properties_from_rectangles(
        rectangles,
        basis=(
            f"gross composite {description.final_section_form}-section formed from "
            f"{description.precast_section_type} precast girder + participating deck flange; "
            f"{description.slab_width_basis}; participating deck layers positioned by "
            "physical construction order; rectangle-component Saint-Venant J approximation"
        ),
    )


def girder_web_width_m(geometry: BridgeGeometry) -> float:
    """Return the physical vertical-web width used for shear/link design."""
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError("Girder web width requires a complete physical girder profile.")
    if isinstance(profile, RectangularGirderProfile):
        return float(profile.width_m)
    if isinstance(profile, TGirderProfile):
        return float(profile.web_width_m)
    if isinstance(profile, IGirderProfile):
        return float(profile.web_width_m)
    raise TypeError("Unsupported physical girder profile.")


def girder_bottom_width_m(geometry: BridgeGeometry) -> float:
    """Return concrete width available to positive-bending bottom tension bars."""
    profile = geometry.girder_profile
    if profile is None:
        raise ValueError("Girder bottom width requires a complete physical girder profile.")
    if isinstance(profile, RectangularGirderProfile):
        return float(profile.width_m)
    if isinstance(profile, TGirderProfile):
        return float(profile.web_width_m)
    if isinstance(profile, IGirderProfile):
        return float(profile.bottom_flange_width_m)
    raise TypeError("Unsupported physical girder profile.")


def composite_section_total_depth_m(geometry: BridgeGeometry) -> float:
    """Return physical deck-plus-precast depth for positive-bending design."""
    if geometry.girder_profile is None:
        raise ValueError("Composite section depth requires a complete physical girder profile.")
    return float(geometry.physical_deck_depth_m + geometry.girder_profile.total_depth_m)

def transverse_deck_strip_properties(
    geometry: BridgeGeometry,
    *,
    strip_width_m: float,
    strip_width_basis: str = "supplied longitudinal strip width",
) -> PhysicalSectionProperties:
    """Derive gross properties of a solid transverse physical deck strip."""
    width = float(strip_width_m)
    depth = float(geometry.physical_deck_depth_m)
    if width <= 0.0:
        raise ValueError("Transverse deck-strip width must be positive.")
    return _properties_from_rectangles(
        (_Rectangle(width, depth, depth / 2.0),),
        basis=(
            f"gross physical deck strip; {strip_width_basis}; "
            "solid-rectangle Saint-Venant J approximation"
        ),
    )


def girder_tributary_slab_widths_m(geometry: BridgeGeometry) -> tuple[float, ...]:
    """Return edge-aware physical deck strip widths for all girder lines."""
    count = int(geometry.girder_count)
    spacing = float(geometry.girder_spacing_m)
    edge = float(geometry.nominal_edge_overhang_m)
    if count == 1:
        return (float(geometry.deck_width_m),)
    widths = (edge + spacing / 2.0, *((spacing,) * (count - 2)), edge + spacing / 2.0)
    if abs(sum(widths) - float(geometry.deck_width_m)) > 1.0e-9:
        raise ValueError("Girder tributary slab widths do not recover the physical deck width.")
    return widths


def station_tributary_strip_widths_m(
    x_stations_m: tuple[float, ...],
) -> tuple[float, ...]:
    """Return longitudinal tributary widths represented by transverse grid lines."""
    if len(x_stations_m) < 2:
        raise ValueError("At least two longitudinal stations are required.")
    if any(
        x_stations_m[index + 1] <= x_stations_m[index]
        for index in range(len(x_stations_m) - 1)
    ):
        raise ValueError("Longitudinal stations must be strictly increasing.")
    widths = []
    for index, station in enumerate(x_stations_m):
        if index == 0:
            width = (x_stations_m[1] - station) / 2.0
        elif index == len(x_stations_m) - 1:
            width = (station - x_stations_m[index - 1]) / 2.0
        else:
            width = (x_stations_m[index + 1] - x_stations_m[index - 1]) / 2.0
        widths.append(width)
    total_length = x_stations_m[-1] - x_stations_m[0]
    if abs(sum(widths) - total_length) > 1.0e-9:
        raise ValueError("Transverse station tributary widths do not recover bridge length.")
    return tuple(widths)
