from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import (
    BridgeGeometry,
    DeckConstruction,
    DesignCode,
    IGirderProfile,
    MaterialProperties,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
    TGirderProfile,
)


@dataclass(frozen=True)
class ProjectBasicFields:
    name: str
    design_code: DesignCode
    support_system: SupportSystem
    span_lengths_m: tuple[float, ...]
    deck_width_m: float
    carriageway_width_m: float
    carriageway_offset_m: float
    girder_count: int
    girder_spacing_m: float
    section_type: SectionType
    fck_mpa: float
    fyk_mpa: float
    precast_girder_length_m: float | None = None
    rectangular_width_m: float | None = None
    rectangular_depth_m: float | None = None
    t_flange_width_m: float | None = None
    t_flange_thickness_m: float | None = None
    t_web_width_m: float | None = None
    t_total_depth_m: float | None = None
    i_top_flange_width_m: float | None = None
    i_top_flange_thickness_m: float | None = None
    i_web_width_m: float | None = None
    i_web_depth_m: float | None = None
    i_bottom_flange_width_m: float | None = None
    i_bottom_flange_thickness_m: float | None = None
    precast_false_slab_depth_m: float = 0.075
    in_situ_slab_depth_m: float = 0.175
    false_slab_composite_participation: bool = False
    in_situ_slab_composite_participation: bool = True
    concrete_density_kn_m3: float = 25.0
    elastic_modulus_mpa: float | None = None

    @classmethod
    def from_project(cls, project: ProjectInput) -> ProjectBasicFields:
        geometry = project.geometry
        profile = geometry.girder_profile
        values: dict[str, float | None] = {
            "rectangular_width_m": None,
            "rectangular_depth_m": None,
            "t_flange_width_m": None,
            "t_flange_thickness_m": None,
            "t_web_width_m": None,
            "t_total_depth_m": None,
            "i_top_flange_width_m": None,
            "i_top_flange_thickness_m": None,
            "i_web_width_m": None,
            "i_web_depth_m": None,
            "i_bottom_flange_width_m": None,
            "i_bottom_flange_thickness_m": None,
        }
        if isinstance(profile, RectangularGirderProfile):
            values["rectangular_width_m"] = float(profile.width_m)
            values["rectangular_depth_m"] = float(profile.depth_m)
        elif isinstance(profile, TGirderProfile):
            values["t_flange_width_m"] = float(profile.flange_width_m)
            values["t_flange_thickness_m"] = float(profile.flange_thickness_m)
            values["t_web_width_m"] = float(profile.web_width_m)
            values["t_total_depth_m"] = float(profile.total_depth_m)
        elif isinstance(profile, IGirderProfile):
            values["i_top_flange_width_m"] = float(profile.top_flange_width_m)
            values["i_top_flange_thickness_m"] = float(profile.top_flange_thickness_m)
            values["i_web_width_m"] = float(profile.web_width_m)
            values["i_web_depth_m"] = float(profile.web_depth_m)
            values["i_bottom_flange_width_m"] = float(profile.bottom_flange_width_m)
            values["i_bottom_flange_thickness_m"] = float(
                profile.bottom_flange_thickness_m
            )

        construction = geometry.deck_construction
        return cls(
            name=project.name,
            design_code=project.design_code,
            support_system=geometry.support_system,
            span_lengths_m=tuple(float(value) for value in geometry.span_lengths_m),
            deck_width_m=float(geometry.deck_width_m),
            carriageway_width_m=float(geometry.carriageway_width_m),
            carriageway_offset_m=float(geometry.carriageway_offset_m),
            girder_count=int(geometry.girder_count),
            girder_spacing_m=float(geometry.girder_spacing_m),
            section_type=geometry.section_type,
            fck_mpa=float(project.materials.fck_mpa),
            fyk_mpa=float(project.materials.fyk_mpa),
            precast_girder_length_m=(
                None
                if geometry.precast_girder_length_m is None
                else float(geometry.precast_girder_length_m)
            ),
            precast_false_slab_depth_m=float(
                construction.precast_false_slab_depth_m
            ),
            in_situ_slab_depth_m=float(construction.in_situ_slab_depth_m),
            false_slab_composite_participation=bool(
                construction.false_slab_composite_participation
            ),
            in_situ_slab_composite_participation=bool(
                construction.in_situ_slab_composite_participation
            ),
            concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
            elastic_modulus_mpa=(
                None
                if project.materials.elastic_modulus_mpa is None
                else float(project.materials.elastic_modulus_mpa)
            ),
            **values,
        )

    def _profile(self):
        if self.section_type == SectionType.RECTANGULAR:
            if self.rectangular_width_m is None or self.rectangular_depth_m is None:
                raise ValueError("Rectangular profile requires width and depth.")
            return RectangularGirderProfile(
                width_m=self.rectangular_width_m,
                depth_m=self.rectangular_depth_m,
            )
        if self.section_type == SectionType.T:
            required = (
                self.t_flange_width_m,
                self.t_flange_thickness_m,
                self.t_web_width_m,
                self.t_total_depth_m,
            )
            if any(value is None for value in required):
                raise ValueError("T profile requires flange, web and total-depth values.")
            return TGirderProfile(
                flange_width_m=self.t_flange_width_m,
                flange_thickness_m=self.t_flange_thickness_m,
                web_width_m=self.t_web_width_m,
                total_depth_m=self.t_total_depth_m,
            )

        required_i = (
            self.i_top_flange_width_m,
            self.i_top_flange_thickness_m,
            self.i_web_width_m,
            self.i_web_depth_m,
            self.i_bottom_flange_width_m,
            self.i_bottom_flange_thickness_m,
        )
        if any(value is None for value in required_i):
            raise ValueError("I profile requires both flanges and web dimensions.")
        return IGirderProfile(
            top_flange_width_m=self.i_top_flange_width_m,
            top_flange_thickness_m=self.i_top_flange_thickness_m,
            web_width_m=self.i_web_width_m,
            web_depth_m=self.i_web_depth_m,
            bottom_flange_width_m=self.i_bottom_flange_width_m,
            bottom_flange_thickness_m=self.i_bottom_flange_thickness_m,
        )

    def apply(self, base: ProjectInput | None = None) -> ProjectInput:
        if not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        if not self.span_lengths_m or any(value <= 0.0 for value in self.span_lengths_m):
            raise ValueError("At least one positive span length is required.")
        profile = self._profile()
        deck_construction = DeckConstruction(
            precast_false_slab_depth_m=self.precast_false_slab_depth_m,
            in_situ_slab_depth_m=self.in_situ_slab_depth_m,
            false_slab_composite_participation=self.false_slab_composite_participation,
            in_situ_slab_composite_participation=self.in_situ_slab_composite_participation,
        )

        base_project = base or ProjectInput()
        geometry_data = base_project.geometry.model_dump(mode="python")
        geometry_data.update(
            {
                "span_lengths_m": list(self.span_lengths_m),
                "deck_width_m": self.deck_width_m,
                "carriageway_width_m": self.carriageway_width_m,
                "carriageway_offset_m": self.carriageway_offset_m,
                "girder_count": self.girder_count,
                "girder_spacing_m": self.girder_spacing_m,
                "girder_depth_m": profile.total_depth_m,
                "precast_girder_length_m": self.precast_girder_length_m,
                "deck_structural_depth_m": deck_construction.physical_depth_m,
                "deck_construction": deck_construction.model_dump(mode="python"),
                "support_system": self.support_system,
                "section_type": self.section_type,
                "girder_profile": profile.model_dump(mode="python"),
            }
        )
        material_data = base_project.materials.model_dump(mode="python")
        material_data.update(
            {
                "fck_mpa": self.fck_mpa,
                "fyk_mpa": self.fyk_mpa,
                "concrete_density_kn_m3": self.concrete_density_kn_m3,
                "elastic_modulus_mpa": self.elastic_modulus_mpa,
            }
        )

        project_data = base_project.model_dump(mode="python")
        project_data.update(
            {
                "name": self.name.strip(),
                "design_code": self.design_code,
                "geometry": BridgeGeometry.model_validate(geometry_data),
                "materials": MaterialProperties.model_validate(material_data),
            }
        )
        return ProjectInput.model_validate(project_data)


def application_default_project() -> ProjectInput:
    """Return the 15 m rectangular-precast/composite-T starting project."""

    fields = ProjectBasicFields(
        name="15 m RC Girder Project",
        design_code=DesignCode.EUROCODE,
        support_system=SupportSystem.SIMPLY_SUPPORTED,
        span_lengths_m=(15.0,),
        deck_width_m=11.0,
        carriageway_width_m=7.0,
        carriageway_offset_m=0.0,
        girder_count=7,
        girder_spacing_m=1.70,
        section_type=SectionType.RECTANGULAR,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        precast_girder_length_m=14.95,
        rectangular_width_m=0.40,
        rectangular_depth_m=0.95,
        precast_false_slab_depth_m=0.075,
        in_situ_slab_depth_m=0.175,
        false_slab_composite_participation=False,
        in_situ_slab_composite_participation=True,
        concrete_density_kn_m3=25.0,
    )
    return fields.apply()
