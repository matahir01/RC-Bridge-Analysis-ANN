from rc_bridge.core.models import BridgeGeometry, DesignCode, MaterialProperties, ProjectInput, SectionType, SupportSystem


REFERENCE_BRIDGE_15M = ProjectInput(
    name="15 m RC Girder Benchmark",
    design_code=DesignCode.EUROCODE,
    geometry=BridgeGeometry(
        span_lengths_m=[15.0],
        deck_width_m=11.0,
        girder_count=7,
        girder_spacing_m=1.70,
        girder_depth_m=0.95,
        deck_structural_depth_m=0.25,
        support_system=SupportSystem.SIMPLY_SUPPORTED,
        section_type=SectionType.T,
    ),
    materials=MaterialProperties(
        fck_mpa=35.0,
        fyk_mpa=500.0,
        concrete_density_kn_m3=25.0,
    ),
)


if __name__ == "__main__":
    print(REFERENCE_BRIDGE_15M.model_dump_json(indent=2))
