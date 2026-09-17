from __future__ import annotations

from enum import Enum
from typing import Literal

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


class RectangularGirderProfile(BaseModel):
    shape: Literal["rectangular"] = "rectangular"
    width_m: PositiveFloat
    depth_m: PositiveFloat

    @property
    def area_m2(self) -> float:
        return float(self.width_m * self.depth_m)

    @property
    def total_depth_m(self) -> float:
        return float(self.depth_m)

    @property
    def section_type(self) -> SectionType:
        return SectionType.RECTANGULAR


class TGirderProfile(BaseModel):
    shape: Literal["t"] = "t"
    flange_width_m: PositiveFloat
    flange_thickness_m: PositiveFloat
    web_width_m: PositiveFloat
    total_depth_m: PositiveFloat

    @model_validator(mode="after")
    def validate_t_profile(self) -> TGirderProfile:
        if self.flange_thickness_m >= self.total_depth_m:
            raise ValueError("T-girder flange thickness must be less than total depth.")
        if self.web_width_m > self.flange_width_m:
            raise ValueError("T-girder web width cannot exceed flange width.")
        return self

    @property
    def area_m2(self) -> float:
        web_depth_m = float(self.total_depth_m - self.flange_thickness_m)
        return float(
            self.flange_width_m * self.flange_thickness_m
            + self.web_width_m * web_depth_m
        )

    @property
    def section_type(self) -> SectionType:
        return SectionType.T


class IGirderProfile(BaseModel):
    shape: Literal["i"] = "i"
    top_flange_width_m: PositiveFloat
    top_flange_thickness_m: PositiveFloat
    web_width_m: PositiveFloat
    web_depth_m: PositiveFloat
    bottom_flange_width_m: PositiveFloat
    bottom_flange_thickness_m: PositiveFloat

    @model_validator(mode="after")
    def validate_i_profile(self) -> IGirderProfile:
        if self.web_width_m > max(self.top_flange_width_m, self.bottom_flange_width_m):
            raise ValueError("I-girder web width is inconsistent with flange widths.")
        return self

    @property
    def total_depth_m(self) -> float:
        return float(
            self.top_flange_thickness_m
            + self.web_depth_m
            + self.bottom_flange_thickness_m
        )

    @property
    def area_m2(self) -> float:
        return float(
            self.top_flange_width_m * self.top_flange_thickness_m
            + self.web_width_m * self.web_depth_m
            + self.bottom_flange_width_m * self.bottom_flange_thickness_m
        )

    @property
    def section_type(self) -> SectionType:
        return SectionType.I


GirderProfile = RectangularGirderProfile | TGirderProfile | IGirderProfile


class MaterialProperties(BaseModel):
    fck_mpa: PositiveFloat = 35.0
    fyk_mpa: PositiveFloat = 500.0
    fcu_mpa: PositiveFloat | None = None
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
    girder_profile: GirderProfile | None = None

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
        if self.girder_profile is not None:
            if self.girder_profile.section_type != self.section_type:
                raise ValueError("Physical girder profile shape must match section_type.")
            if abs(self.girder_profile.total_depth_m - float(self.girder_depth_m)) > 1e-9:
                raise ValueError(
                    "Physical girder profile depth must match girder_depth_m."
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

    @property
    def girder_profile_area_m2(self) -> float | None:
        if self.girder_profile is None:
            return None
        return self.girder_profile.area_m2


class ProjectInput(BaseModel):
    name: str = "15 m RC Girder Benchmark"
    design_code: DesignCode = DesignCode.EUROCODE
    geometry: BridgeGeometry = Field(default_factory=BridgeGeometry)
    materials: MaterialProperties = Field(default_factory=MaterialProperties)
