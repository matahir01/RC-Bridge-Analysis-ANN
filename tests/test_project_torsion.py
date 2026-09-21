import pytest

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    parse_grillage_effects_csv,
)
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import project_internal_girder_combinations_verification
from rc_bridge.workflow.project_grillage import project_internal_girder_combinations_from_grillage
from rc_bridge.workflow.project_torsion import TorsionCellInput, check_project_shear_torsion

GRILLAGE_CSV = """girder_index,moment_knm,shear_kn,torsion_knm
1,420.0,180.0,22.0
2,510.0,205.0,18.0
3,590.0,225.0,12.0
4,625.0,235.0,8.0
5,590.0,225.0,12.0
6,510.0,205.0,18.0
7,420.0,180.0,22.0
"""


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


def _sls_factors() -> ServiceabilityPsiFactors:
    return ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)


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


def test_imported_grillage_torsion_is_checked_with_explicit_cell_geometry() -> None:
    project = ProjectInput()
    combinations = project_internal_girder_combinations_from_grillage(
        project,
        grillage=_grillage(),
        girder_index=4,
        sls_factors=_sls_factors(),
    )
    result = check_project_shear_torsion(
        project,
        combinations=combinations,
        section=_section(),
        torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
        cot_theta=2.0,
    )

    assert result.torsion.design_torsion_knm == pytest.approx(10.8)
    assert result.torsion.transverse_asw_per_s_mm2_per_m > 0.0
    assert result.torsion.longitudinal_asl_mm2 > 0.0
    assert result.torsion.trdmax_knm > 0.0
    assert result.shear_strut.vrdmax_kn > 0.0
    assert result.interaction.utilization == pytest.approx(
        result.torsion.design_torsion_knm / result.torsion.trdmax_knm
        + combinations.persistent_uls.effects.shear_kn / result.shear_strut.vrdmax_kn
    )


def test_equal_share_verification_has_zero_torsion_demand() -> None:
    project = ProjectInput()
    combinations = project_internal_girder_combinations_verification(
        project,
        girder_index=4,
        sls_factors=_sls_factors(),
        movement_steps=11,
        section_stations=21,
    )
    result = check_project_shear_torsion(
        project,
        combinations=combinations,
        section=_section(),
        torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
    )
    assert result.torsion.design_torsion_knm == pytest.approx(0.0)
    assert result.torsion.transverse_asw_per_s_mm2_per_m == pytest.approx(0.0)
    assert result.torsion.longitudinal_asl_mm2 == pytest.approx(0.0)
    assert result.interaction.torsion_ratio == pytest.approx(0.0)


def test_torsion_cell_geometry_must_be_explicitly_positive() -> None:
    with pytest.raises(ValueError, match="Ak, uk and tef"):
        TorsionCellInput(ak_m2=0.0, uk_m=1.40, tef_m=0.15)
