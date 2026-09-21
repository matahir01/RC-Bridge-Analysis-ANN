from rc_bridge.core.models import (
    BridgeGeometry,
    DeckConstruction,
    DesignCode,
    MaterialProperties,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
)

REFERENCE_BRIDGE_15M = ProjectInput(
    name="15 m RC Girder Benchmark",
    design_code=DesignCode.EUROCODE,
    geometry=BridgeGeometry(
        span_lengths_m=[15.0],
        deck_width_m=11.0,
        carriageway_width_m=7.0,
        girder_count=7,
        girder_spacing_m=1.70,
        girder_depth_m=0.95,
        precast_girder_length_m=14.95,
        deck_structural_depth_m=0.25,
        deck_construction=DeckConstruction(
            precast_false_slab_depth_m=0.075,
            in_situ_slab_depth_m=0.175,
            false_slab_composite_participation=False,
            in_situ_slab_composite_participation=True,
        ),
        support_system=SupportSystem.SIMPLY_SUPPORTED,
        section_type=SectionType.RECTANGULAR,
        girder_profile=RectangularGirderProfile(
            width_m=0.40,
            depth_m=0.95,
        ),
    ),
    materials=MaterialProperties(
        fck_mpa=35.0,
        fyk_mpa=500.0,
        concrete_density_kn_m3=25.0,
    ),
)


if __name__ == "__main__":
    print(REFERENCE_BRIDGE_15M.model_dump_json(indent=2))
