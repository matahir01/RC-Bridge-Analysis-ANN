from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt


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


class BridgeGeometry(BaseModel):
    span_lengths_m: list[PositiveFloat] = Field(default_factory=lambda: [15.0])
    deck_width_m: PositiveFloat = 11.0
    girder_count: PositiveInt = 7
    girder_spacing_m: PositiveFloat = 1.70
    girder_depth_m: PositiveFloat = 0.95
    deck_structural_depth_m: PositiveFloat = 0.25
    support_system: SupportSystem = SupportSystem.SIMPLY_SUPPORTED
    section_type: SectionType = SectionType.T


class ProjectInput(BaseModel):
    name: str = "15 m RC Girder Benchmark"
    design_code: DesignCode = DesignCode.EUROCODE
    geometry: BridgeGeometry = Field(default_factory=BridgeGeometry)
    materials: MaterialProperties = Field(default_factory=MaterialProperties)
