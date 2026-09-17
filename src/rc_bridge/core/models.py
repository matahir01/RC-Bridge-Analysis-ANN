from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, model_validator


class DesignCode(str, Enum):
    EUROCODE = "eurocode"
    BS5400 = "bs5400"


class SectionType(str, Enum):
    RECTANGULAR = "rectangular"
    T = "t"
    I = "i"


class SupportSystem(str, Enum):
    SIMPLY_SUPPORTED = "simply_supported"
    CONTINUOUS = "continuous"


class MaterialProperties(BaseModel):
    fck_mpa: PositiveFloat = 35.0
    fyk_mpa: PositiveFloat = 500.0
    concrete_density_kn_m3: PositiveFloat = 25.0
    elastic_modulus_mpa: PositiveFloat | None = None


class DeckConstruction(BaseModel):
    """Physical deck build-up and structural participation.

    The precast false slab always contributes permanent weight when present,
    but it is excluded from the composite compression flange by default. It may
    only be included when the project detailing and verification justify
    composite participation.
    """

    precast_false_slab_depth_m: PositiveFloat = 0.075
    in_situ_slab_depth_m: PositiveFloat = 0.175
    false_slab_composite_participation: bool = False
    in_situ_slab_composite_participation: bool = True

    @property
    def physical_depth_m(self) -> float:
        return float(self.precast_false_slab_depth_m + self.in_situ_slab_depth_m)

    @property
    def composite_flange_depth_m(self) -> float:
        depth = 0.0
        if self.false_slab_composite_participation:
            depth += float(self.precast_false_slab_depth_m)
        if self.in_situ_slab_composite_participation:
            depth += float(self.in_situ_slab_depth_m)
        return depth


class BridgeGeometry(BaseModel):
    span_lengths_m: list[PositiveFloat] = Field(default_factory=lambda: [15.0])
    deck_width_m: PositiveFloat = 11.0
    carriageway_width_m: PositiveFloat = 7.0
    girder_count: PositiveInt = 7
    girder_spacing_m: PositiveFloat = 1.70
    girder_depth_m: PositiveFloat = 0.95
    deck_structural_depth_m: PositiveFloat = 0.25
    deck_construction: DeckConstruction = Field(default_factory=DeckConstruction)
    support_system: SupportSystem = SupportSystem.SIMPLY_SUPPORTED
    section_type: SectionType = SectionType.T

    @model_validator(mode="after")
    def validate_bridge_widths_and_deck_build_up(self) -> BridgeGeometry:
        if self.carriageway_width_m > self.deck_width_m:
            raise ValueError("Carriageway width cannot exceed total deck width.")
        if self.girder_line_width_m > float(self.deck_width_m) + 1e-9:
            raise ValueError(
                "Girder count and spacing place the exterior girder lines outside the deck width."
            )
        if abs(float(self.deck_structural_depth_m) - self.deck_construction.physical_depth_m) > 1e-9:
            raise ValueError(
                "deck_structural_depth_m must equal the physical deck build-up; "
                "edit the deck-construction component depths explicitly."
            )
        return self

    @property
    def physical_deck_depth_m(self) -> float:
        return self.deck_construction.physical_depth_m

    @property
    def composite_flange_depth_m(self) -> float:
        return self.deck_construction.composite_flange_depth_m

    @property
    def girder_line_width_m(self) -> float:
        return (int(self.girder_count) - 1) * float(self.girder_spacing_m)

    @property
    def nominal_edge_overhang_m(self) -> float:
        """Symmetric edge overhang implied by deck width, count, and spacing."""
        return (float(self.deck_width_m) - self.girder_line_width_m) / 2.0


class ProjectInput(BaseModel):
    name: str = "15 m RC Girder Benchmark"
    design_code: DesignCode = DesignCode.EUROCODE
    geometry: BridgeGeometry = Field(default_factory=BridgeGeometry)
    materials: MaterialProperties = Field(default_factory=MaterialProperties)
