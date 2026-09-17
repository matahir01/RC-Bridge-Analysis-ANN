import pytest

from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.core.models import DesignCode, MaterialProperties, ProjectInput
from rc_bridge.workflow.bs5400_girder import BS5400TGirderInput
from rc_bridge.workflow.project_bs5400 import (
    run_project_internal_bs5400_t_girder_verification,
)


def _project() -> ProjectInput:
    return ProjectInput(
        design_code=DesignCode.BS5400,
        materials=MaterialProperties(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            fcu_mpa=40.0,
        ),
    )


def _section() -> BS5400TGirderInput:
    return BS5400TGirderInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
    )


def test_reference_project_bs5400_ha_to_t_girder_path() -> None:
    result = run_project_internal_bs5400_t_girder_verification(
        _project(),
        girder_index=4,
        section=_section(),
        factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
    )

    assert result.permanent_characteristic.moment_knm == pytest.approx(298.828125)
    assert result.permanent_characteristic.shear_kn == pytest.approx(79.6875)
    assert result.traffic_characteristic.moment_knm == pytest.approx(545.191939266)
    assert result.traffic_characteristic.shear_kn == pytest.approx(145.384517138)
    assert result.design.uls_combination.effects.moment_knm == pytest.approx(
        1121.862464973
    )
    assert result.design.uls_combination.effects.shear_kn == pytest.approx(
        299.163323993
    )
    assert result.design.flexure.compression_zone == "flange"
    assert result.design.flexure.g_flexure_knm > 0.0
    assert result.design.shear.governing_asv_per_s_mm2_per_m > 0.0
    assert "equal_share_verification_only" in result.traffic_distribution_method


def test_project_bs5400_verification_rejects_edge_girder() -> None:
    with pytest.raises(ValueError, match="internal girders only"):
        run_project_internal_bs5400_t_girder_verification(
            _project(),
            girder_index=1,
            section=_section(),
            factors=BS5400Factors(gamma_permanent=1.20, gamma_live=1.40),
        )
