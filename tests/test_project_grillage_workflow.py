import pytest

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    parse_grillage_effects_csv,
)
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import SLSCombinationChoice
from rc_bridge.workflow.project_grillage import (
    project_internal_girder_combinations_from_grillage,
    run_project_internal_t_girder_from_grillage,
)

GRILLAGE_CSV = """girder_index,moment_knm,shear_kn,torsion_knm
1,420.0,180.0,22.0
2,510.0,205.0,18.0
3,590.0,225.0,12.0
4,625.0,235.0,8.0
5,590.0,225.0,12.0
6,510.0,205.0,18.0
7,420.0,180.0,22.0
"""


def _grillage():
    return parse_grillage_effects_csv(
        GRILLAGE_CSV,
        metadata=GrillageImportMetadata(
            source_software="Midas Civil",
            model_name="15 m benchmark grillage",
            load_case="LM1 characteristic envelope",
        ),
        expected_girder_count=7,
    )


def _section() -> TGirderDesignInput:
    return TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.20,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )


def test_imported_grillage_effects_feed_en1990_combinations() -> None:
    project = ProjectInput()
    combinations = project_internal_girder_combinations_from_grillage(
        project,
        grillage=_grillage(),
        girder_index=4,
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
    )

    assert combinations.traffic_characteristic.moment_knm == pytest.approx(625.0)
    assert combinations.traffic_characteristic.shear_kn == pytest.approx(235.0)
    assert combinations.traffic_characteristic.torsion_knm == pytest.approx(8.0)
    assert combinations.persistent_uls.effects.torsion_knm == pytest.approx(12.0)
    assert "Midas Civil" in combinations.traffic_distribution_method
    assert "LM1 characteristic envelope" in combinations.traffic_distribution_method


def test_imported_grillage_runs_full_t_girder_path_and_retains_torsion() -> None:
    result = run_project_internal_t_girder_from_grillage(
        ProjectInput(),
        grillage=_grillage(),
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert result.source_metadata.source_software == "Midas Civil"
    assert result.imported_uls_torsion_knm == pytest.approx(12.0)
    assert result.design.uls_combination.effects.torsion_knm == pytest.approx(12.0)
    assert result.design.uls_design.flexure.resistance_knm > 0.0
    assert result.design.uls_design.shear.design_shear_kn > 0.0
    assert result.design.crack.crack_width_mm >= 0.0
    assert result.design.deflection.interpolated_deflection_mm >= 0.0


def test_imported_grillage_path_rejects_edge_girder_internal_load_model() -> None:
    with pytest.raises(ValueError, match="internal girders only"):
        project_internal_girder_combinations_from_grillage(
            ProjectInput(),
            grillage=_grillage(),
            girder_index=1,
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        )
