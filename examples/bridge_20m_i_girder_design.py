from __future__ import annotations

"""Preliminary 20 m I-girder bridge design using the agreed 1200 mm section.

Physical target section:
- equal top/bottom flange width = 400 mm
- top rectangular flange = 150 mm
- top haunch = 150 mm
- clear web = 500 mm
- bottom haunch = 200 mm
- bottom rectangular flange = 200 mm
- physical web = 250 mm

The current IGirderProfile is rectangular-component based and has no tapered
haunch primitives. The analysis therefore uses a 400/250/400 mm prismatic
I-profile with the haunch depths absorbed into the 850 mm web zone. This is a
preliminary engine idealisation, not a fabrication drawing.
"""

from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
    EurocodeApplicationBasis,
)
from rc_bridge.application.project_io import save_project
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.core.models import (
    BridgeGeometry,
    DeckConstruction,
    DesignCode,
    IGirderProfile,
    MaterialProperties,
    PermanentActionModel,
    PermanentActionStage,
    PermanentLineAction,
    PermanentLineActionCategory,
    ProjectInput,
    SectionType,
    SupportSystem,
    SurfacingLayer,
)

PROJECT = ProjectInput(
    name="20 m Preliminary RC I-Girder Bridge - 400 mm Equal Flanges",
    design_code=DesignCode.EUROCODE,
    geometry=BridgeGeometry(
        span_lengths_m=[20.0],
        deck_width_m=11.0,
        carriageway_width_m=7.0,
        girder_count=7,
        girder_spacing_m=1.70,
        girder_depth_m=1.20,
        precast_girder_length_m=20.0,
        deck_structural_depth_m=0.25,
        deck_construction=DeckConstruction(
            precast_false_slab_depth_m=0.075,
            in_situ_slab_depth_m=0.175,
            false_slab_composite_participation=False,
            in_situ_slab_composite_participation=True,
        ),
        support_system=SupportSystem.SIMPLY_SUPPORTED,
        section_type=SectionType.I,
        girder_profile=IGirderProfile(
            top_flange_width_m=0.40,
            top_flange_thickness_m=0.15,
            web_width_m=0.25,
            web_depth_m=0.85,
            bottom_flange_width_m=0.40,
            bottom_flange_thickness_m=0.20,
        ),
    ),
    materials=MaterialProperties(
        fck_mpa=35.0,
        fyk_mpa=500.0,
        concrete_density_kn_m3=25.0,
    ),
    permanent_actions=PermanentActionModel(
        surfacing_layers=[
            SurfacingLayer(
                name="80 mm carriageway surfacing - preliminary assumption",
                thickness_m=0.08,
                density_kn_m3=23.0,
                y_start_m=-3.5,
                y_end_m=3.5,
                stage=PermanentActionStage.SUPERIMPOSED,
            )
        ],
        line_actions=[
            PermanentLineAction(
                name="Left barrier - preliminary 10 kN/m",
                magnitude_kn_m=10.0,
                y_m=-5.25,
                category=PermanentLineActionCategory.BARRIER,
            ),
            PermanentLineAction(
                name="Right barrier - preliminary 10 kN/m",
                magnitude_kn_m=10.0,
                y_m=5.25,
                category=PermanentLineActionCategory.BARRIER,
            ),
        ],
    ),
)

PREFERENCES = ApplicationPreferences(
    eurocode=EurocodeApplicationBasis(
        crack_limit_mm=0.30,
        deflection_limit_span_ratio=1000.0,
    ),
    analysis=AnalysisApplicationSettings(
        grid_spacing_m=1.0,
        traffic_step_m=0.5,
        max_exhaustive_tandem_combinations=5000,
    ),
)


def main() -> None:
    out = __import__("pathlib").Path("artifacts/bridge_20m_i_girder")
    out.mkdir(parents=True, exist_ok=True)
    project_file = save_project(PROJECT, out / "project.json", application_preferences=PREFERENCES)
    session = BridgeApplicationSession.open(project_file)
    lm1 = session.run_native_lm1()
    session.run_extended_actions()
    design = session.run_design_interpretation()
    session.write_last_lm1_report(out / "analysis_design_report.html")
    session.write_last_lm1_pdf_report(out / "analysis_design_report.pdf")

    critical = max(design.girders, key=lambda g: g.uls.effects.moment_knm)
    print(f"LM1 cases evaluated: {lm1.evaluated_case_count}")
    print("Detailed output: governing girder only")
    print(f"Critical girder: G{critical.girder_index}")
    print(f"MEd={critical.uls.effects.moment_knm:.3f} kNm")
    print(f"VEd={critical.uls.effects.shear_kn:.3f} kN")
    print(f"As_req={critical.design.uls_design.flexure.required_steel_area_mm2:.1f} mm2")
    print(f"As_prov={critical.selected_bars.provided_area_mm2:.1f} mm2")
    print(f"bars={critical.selected_bars}")
    print(f"links={critical.selected_links}")
    print(f"status={critical.status}")


if __name__ == "__main__":
    main()
