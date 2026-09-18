from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt, model_validator

from rc_bridge.core.girder_layout import GirderLayoutEvaluation, evaluate_girder_layout


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


class PermanentLineActionCategory(str, Enum):
    BARRIER = "barrier"
    SERVICES = "services"
    OTHER = "other"


class PermanentActionStage(str, Enum):
    """Construction state at which a permanent action first acts."""

    PRECAST_GIRDER = "precast_girder"
    DECK_CONSTRUCTION = "deck_construction"
    SUPERIMPOSED = "superimposed"


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


class SurfacingLayer(BaseModel):
    """One permanent area layer with transverse and longitudinal bounds."""

    name: str
    thickness_m: PositiveFloat
    density_kn_m3: PositiveFloat
    y_start_m: float
    y_end_m: float
    x_start_m: float = 0.0
    x_end_m: float | None = None
    stage: PermanentActionStage = PermanentActionStage.SUPERIMPOSED

    @model_validator(mode="after")
    def validate_band(self) -> SurfacingLayer:
        if not self.name.strip():
            raise ValueError("Surfacing-layer name cannot be empty.")
        if self.y_end_m <= self.y_start_m:
            raise ValueError("Surfacing-layer transverse bounds must define positive width.")
        if self.x_start_m < 0.0:
            raise ValueError("Surfacing-layer longitudinal start cannot be negative.")
        if self.x_end_m is not None and self.x_end_m <= self.x_start_m:
            raise ValueError("Surfacing-layer longitudinal bounds must define positive length.")
        return self

    @property
    def pressure_kn_m2(self) -> float:
        return float(self.thickness_m * self.density_kn_m3)


class PermanentLineAction(BaseModel):
    """A physical longitudinal line action positioned across the deck."""

    name: str
    magnitude_kn_m: PositiveFloat
    y_m: float
    category: PermanentLineActionCategory
    x_start_m: float = 0.0
    x_end_m: float | None = None
    stage: PermanentActionStage = PermanentActionStage.SUPERIMPOSED

    @model_validator(mode="after")
    def validate_name(self) -> PermanentLineAction:
        if not self.name.strip():
            raise ValueError("Permanent line-action name cannot be empty.")
        if self.x_start_m < 0.0:
            raise ValueError("Permanent line-action longitudinal start cannot be negative.")
        if self.x_end_m is not None and self.x_end_m <= self.x_start_m:
            raise ValueError(
                "Permanent line-action longitudinal bounds must define positive length."
            )
        return self


class PermanentActionModel(BaseModel):
    surfacing_layers: list[SurfacingLayer] = Field(default_factory=list)
    line_actions: list[PermanentLineAction] = Field(default_factory=list)


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
    carriageway_offset_m: float = 0.0
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
        if (
            self.carriageway_left_edge_m < -float(self.deck_width_m) / 2.0 - 1e-9
            or self.carriageway_right_edge_m > float(self.deck_width_m) / 2.0 + 1e-9
        ):
            raise ValueError(
                "Carriageway width and transverse offset place part of the carriageway "
                "outside the physical deck width."
            )
        layout = self.girder_layout
        if not layout.fits_deck:
            max_spacing = layout.maximum_spacing_m_for_current_deck
            spacing_guidance = (
                f"reduce girder_spacing_m to at most {max_spacing:.3f} m"
                if max_spacing is not None
                else "review the girder layout"
            )
            raise ValueError(
                "Girder count and spacing place the exterior girder lines outside the deck width. "
                f"Current {int(self.girder_count)}-girder layout at "
                f"{float(self.girder_spacing_m):.3f} m spacing requires at least "
                f"{layout.minimum_deck_width_m:.3f} m deck width with zero edge overhang. "
                f"Either increase deck_width_m or {spacing_guidance}; deck width, girder count, "
                "and girder spacing are independently editable inputs."
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
    def carriageway_left_edge_m(self) -> float:
        return float(self.carriageway_offset_m) - float(self.carriageway_width_m) / 2.0

    @property
    def carriageway_right_edge_m(self) -> float:
        return float(self.carriageway_offset_m) + float(self.carriageway_width_m) / 2.0

    @property
    def girder_layout(self) -> GirderLayoutEvaluation:
        """Return linked consequences of the three independently editable layout inputs."""
        return evaluate_girder_layout(
            deck_width_m=float(self.deck_width_m),
            girder_count=int(self.girder_count),
            girder_spacing_m=float(self.girder_spacing_m),
        )

    @property
    def girder_line_width_m(self) -> float:
        return self.girder_layout.girder_line_width_m

    @property
    def nominal_edge_overhang_m(self) -> float:
        """Symmetric edge overhang implied by deck width, count, and spacing."""
        return self.girder_layout.implied_edge_overhang_m

    @property
    def maximum_spacing_m_for_current_deck(self) -> float | None:
        return self.girder_layout.maximum_spacing_m_for_current_deck

    @property
    def maximum_girder_count_for_current_spacing(self) -> int:
        return self.girder_layout.maximum_girder_count_for_current_spacing

    @property
    def minimum_deck_width_m_for_current_layout(self) -> float:
        return self.girder_layout.minimum_deck_width_m

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
    permanent_actions: PermanentActionModel = Field(default_factory=PermanentActionModel)

    @model_validator(mode="after")
    def validate_permanent_action_positions(self) -> ProjectInput:
        half_width = float(self.geometry.deck_width_m) / 2.0
        total_length = sum(float(value) for value in self.geometry.span_lengths_m)
        for layer in self.permanent_actions.surfacing_layers:
            if layer.y_start_m < -half_width or layer.y_end_m > half_width:
                raise ValueError("Surfacing layer lies outside the physical deck width.")
            if layer.x_start_m >= total_length or (
                layer.x_end_m is not None and layer.x_end_m > total_length
            ):
                raise ValueError("Surfacing layer lies outside the bridge length.")
        for action in self.permanent_actions.line_actions:
            if action.y_m < -half_width or action.y_m > half_width:
                raise ValueError("Permanent line action lies outside the physical deck width.")
            if action.x_start_m >= total_length or (
                action.x_end_m is not None and action.x_end_m > total_length
            ):
                raise ValueError("Permanent line action lies outside the bridge length.")
        return self
