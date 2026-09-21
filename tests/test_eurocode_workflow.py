import pytest

from rc_bridge.codes.common import LoadEffects
from rc_bridge.design.eurocode_deflection import SimpleSpanMomentDiagram
from rc_bridge.workflow.eurocode_girder import (
    EurocodeMaterialInput,
    EurocodeServiceabilityInput,
    TGirderDesignInput,
    run_eurocode_t_girder_case,
)


def test_integrated_eurocode_t_girder_workflow_returns_all_limit_states() -> None:
    result = run_eurocode_t_girder_case(
        girder_index=4,
        span_m=15.0,
        permanent_effects=LoadEffects(moment_knm=650.0, shear_kn=180.0),
        traffic_effects=LoadEffects(moment_knm=550.0, shear_kn=220.0),
        section=TGirderDesignInput(
            effective_flange_width_m=1.70,
            flange_thickness_m=0.25,
            web_width_m=0.30,
            total_depth_m=1.20,
            effective_depth_m=1.10,
            steel_area_mm2=6500.0,
            bar_diameter_mm=32.0,
            bar_spacing_mm=150.0,
            cover_mm=50.0,
        ),
        materials=EurocodeMaterialInput(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            ecm_mpa=34000.0,
            fct_eff_mpa=3.2,
        ),
        serviceability=EurocodeServiceabilityInput(
            service_moment_knm=1050.0,
            equivalent_full_span_udl_kn_m=25.0,
            crack_limit_mm=0.30,
            allowable_deflection_mm=30.0,
        ),
    )

    assert result.uls_combination.effects.moment_knm == pytest.approx(
        1.35 * 650.0 + 1.35 * 550.0
    )
    assert result.uls_design.flexure.resistance_knm > 0.0
    assert result.uls_design.shear.design_shear_kn > 0.0
    assert result.uncracked_sls.cracking_moment_knm > 0.0
    assert result.cracked_sls.second_moment_mm4 > 0.0
    assert result.crack.crack_width_mm >= 0.0
    assert result.deflection.interpolated_deflection_mm >= 0.0
    assert result.g_flexure_knm == pytest.approx(
        result.uls_design.flexure.resistance_knm
        - result.uls_combination.effects.moment_knm
    )
    assert result.g_crack_mm == pytest.approx(
        result.crack.crack_limit_mm - result.crack.crack_width_mm
    )
    assert result.g_deflection_mm == pytest.approx(
        result.deflection.allowable_deflection_mm
        - result.deflection.interpolated_deflection_mm
    )


def test_eurocode_workflow_prefers_traceable_moment_diagram_for_deflection() -> None:
    result = run_eurocode_t_girder_case(
        girder_index=4,
        span_m=15.0,
        permanent_effects=LoadEffects(moment_knm=650.0, shear_kn=180.0),
        traffic_effects=LoadEffects(moment_knm=550.0, shear_kn=220.0),
        section=TGirderDesignInput(
            effective_flange_width_m=1.70,
            flange_thickness_m=0.25,
            web_width_m=0.30,
            total_depth_m=1.20,
            effective_depth_m=1.10,
            steel_area_mm2=6500.0,
            bar_diameter_mm=32.0,
            bar_spacing_mm=150.0,
            cover_mm=50.0,
        ),
        materials=EurocodeMaterialInput(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            ecm_mpa=34000.0,
            fct_eff_mpa=3.2,
        ),
        serviceability=EurocodeServiceabilityInput(
            service_moment_knm=1050.0,
            equivalent_full_span_udl_kn_m=0.0,
            crack_limit_mm=0.30,
            allowable_deflection_mm=30.0,
            deflection_moment_diagram=SimpleSpanMomentDiagram(
                stations_m=(0.0, 7.5, 15.0),
                moments_knm=(0.0, 820.0, 0.0),
                source="unit-test co-located response",
            ),
            deflection_service_moment_knm=820.0,
        ),
    )

    assert result.deflection.interpolated_deflection_mm > 0.0
    assert "signed M/EI curvature integration" in result.deflection.status
    assert "unit-test co-located response" in result.deflection.status



def test_eurocode_workflow_uses_explicit_provided_shear_links() -> None:
    result = run_eurocode_t_girder_case(
        girder_index=4,
        span_m=15.0,
        permanent_effects=LoadEffects(moment_knm=650.0, shear_kn=180.0),
        traffic_effects=LoadEffects(moment_knm=550.0, shear_kn=220.0),
        section=TGirderDesignInput(
            effective_flange_width_m=1.70,
            flange_thickness_m=0.25,
            web_width_m=0.30,
            total_depth_m=1.20,
            effective_depth_m=1.10,
            steel_area_mm2=6500.0,
            bar_diameter_mm=32.0,
            bar_spacing_mm=150.0,
            cover_mm=50.0,
            provided_shear_asw_per_s_mm2_per_m=1600.0,
        ),
        materials=EurocodeMaterialInput(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            ecm_mpa=34000.0,
            fct_eff_mpa=3.2,
        ),
        serviceability=EurocodeServiceabilityInput(
            service_moment_knm=1050.0,
            equivalent_full_span_udl_kn_m=25.0,
            crack_limit_mm=0.30,
            allowable_deflection_mm=30.0,
        ),
    )

    assert result.provided_shear is not None
    assert result.provided_shear.provided_asw_per_s_mm2_per_m == pytest.approx(1600.0)
    ved_kn = abs(result.uls_design.design_effects.shear_kn)
    if ved_kn > result.uls_design.shear.concrete_resistance_kn:
        assert result.g_shear_kn == pytest.approx(
            result.provided_shear.governing_resistance_kn - ved_kn
        )
        assert result.shear_utilization == pytest.approx(
            ved_kn / result.provided_shear.governing_resistance_kn
        )
    else:
        assert result.g_shear_kn == pytest.approx(
            result.uls_design.shear.g_shear_concrete_kn
        )
        assert result.shear_utilization == pytest.approx(
            result.uls_design.shear.utilization_concrete_only
        )


def test_eurocode_workflow_rejects_negative_provided_shear_links() -> None:
    with pytest.raises(ValueError, match="Provided shear A_sw/s"):
        run_eurocode_t_girder_case(
            girder_index=4,
            span_m=15.0,
            permanent_effects=LoadEffects(moment_knm=100.0, shear_kn=30.0),
            traffic_effects=LoadEffects(moment_knm=100.0, shear_kn=30.0),
            section=TGirderDesignInput(
                effective_flange_width_m=1.70,
                flange_thickness_m=0.25,
                web_width_m=0.30,
                total_depth_m=1.20,
                effective_depth_m=1.10,
                steel_area_mm2=6500.0,
                bar_diameter_mm=32.0,
                bar_spacing_mm=150.0,
                cover_mm=50.0,
                provided_shear_asw_per_s_mm2_per_m=-1.0,
            ),
            materials=EurocodeMaterialInput(
                fck_mpa=35.0,
                fyk_mpa=500.0,
                ecm_mpa=34000.0,
                fct_eff_mpa=3.2,
            ),
            serviceability=EurocodeServiceabilityInput(
                service_moment_knm=150.0,
                equivalent_full_span_udl_kn_m=10.0,
                crack_limit_mm=0.30,
                allowable_deflection_mm=30.0,
            ),
        )
