import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import (
    BridgeGeometry,
    PermanentActionStage,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
)
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.project_construction import PermanentGrillageStageInput
from rc_bridge.workflow.project_continuous_design import (
    ContinuousShearDesignInput,
    NegativeSupportRectangularDesignInput,
    PositiveCompositeTSectionDesignInput,
    run_continuous_eurocode_uls_design,
)
from rc_bridge.workflow.project_continuous_native import (
    run_project_continuous_native_lm1_envelope,
)
from rc_bridge.workflow.project_continuous_native_deflection import (
    run_project_continuous_native_service_deflection,
)
from rc_bridge.workflow.project_continuous_native_torsion import (
    check_project_continuous_native_matched_shear_torsion,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput


def _project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.40, depth_m=0.95),
        )
    )


def _crossbeam() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="verified construction crossbeam",
        area_m2=0.25,
        torsion_constant_m4=0.01,
        iy_m4=0.02,
        iz_m4=0.03,
    )


def _stages() -> tuple[PermanentGrillageStageInput, ...]:
    return (
        PermanentGrillageStageInput(
            stage=PermanentActionStage.PRECAST_GIRDER,
            basis="unpropped precast girders with verified crossbeams",
            transverse_section=_crossbeam(),
        ),
        PermanentGrillageStageInput(
            stage=PermanentActionStage.DECK_CONSTRUCTION,
            basis="wet deck on unchanged continuity with verified crossbeams",
            transverse_section=_crossbeam(),
        ),
        PermanentGrillageStageInput(
            stage=PermanentActionStage.SUPERIMPOSED,
            basis="final composite bridge",
        ),
    )


def _run(girder_index: int = 2):
    return run_project_continuous_native_lm1_envelope(
        _project(),
        girder_index=girder_index,
        construction_stages=_stages(),
        unchanged_supports_and_continuity_basis=(
            "two-span continuity and supports active throughout the analysed sequence"
        ),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        ),
        stations_per_span=3,
        longitudinal_step_m=10.0,
        max_exhaustive_tandem_combinations=20,
    )


def test_native_continuous_envelope_integrates_staged_g_and_full_width_lm1() -> None:
    result = _run()

    assert result.construction.final_response.total_applied_vertical_load_kn < 0.0
    assert result.traffic.cases
    assert result.envelope.max_positive_uls_moment_knm > 0.0
    assert result.envelope.min_negative_uls_moment_knm < 0.0
    assert result.envelope.max_abs_uls_shear_kn > 0.0
    assert "native full-width" in result.envelope.traffic_distribution_method
    assert any(abs(trace.global_position_m - 10.0) <= 1.0e-9 for trace in result.trace)
    assert any(trace.traffic_minimum_moment_knm < 0.0 for trace in result.trace)


def test_native_continuous_envelope_retains_both_internal_support_sides() -> None:
    result = _run()
    support = [
        station
        for station in result.envelope.stations
        if abs(station.global_position_m - 10.0) <= 1.0e-9
    ]
    assert len(support) == 2
    assert {item.section_side for item in support} == {"left", "right"}
    assert support[0].permanent_moment_knm == pytest.approx(
        support[1].permanent_moment_knm, rel=1.0e-8
    )


def test_existing_continuous_uls_design_accepts_native_envelope() -> None:
    result = run_continuous_eurocode_uls_design(
        _run().envelope,
        positive_section=PositiveCompositeTSectionDesignInput(
            effective_flange_width_m=1.50,
            flange_thickness_m=0.175,
            web_width_m=0.40,
            effective_depth_from_top_m=1.10,
            provided_bottom_steel_area_mm2=7000.0,
        ),
        negative_section=NegativeSupportRectangularDesignInput(
            compression_width_m=0.40,
            effective_depth_from_bottom_m=1.10,
            provided_top_steel_area_mm2=6500.0,
        ),
        shear_section=ContinuousShearDesignInput(
            web_width_m=0.40,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
            provided_asw_per_s_mm2_per_m=1600.0,
        ),
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert result.positive_design_moment_knm > 0.0
    assert result.negative_design_moment_knm > 0.0
    assert result.design_shear_kn > 0.0



def test_native_continuous_service_deflection_combines_staged_g_and_lm1() -> None:
    production = _run()
    result = run_project_continuous_native_service_deflection(
        _project(),
        construction=production.construction,
        traffic=production.traffic,
        girder_index=2,
        traffic_factor=0.75,
        allowable_deflection_mm=40.0,
    )

    assert result.calculated_max_abs_deflection_mm > 0.0
    assert result.calculated_max_abs_deflection_mm >= (
        result.permanent_only_max_abs_deflection_mm
    )
    assert 0.0 < result.governing_global_position_m < 20.0
    assert result.utilization == pytest.approx(
        result.calculated_max_abs_deflection_mm / 40.0
    )
    assert result.g_deflection_mm == pytest.approx(
        40.0 - result.calculated_max_abs_deflection_mm
    )
    assert "interior displacement extrema" in result.status


def test_native_continuous_zero_traffic_factor_returns_permanent_only() -> None:
    production = _run()
    result = run_project_continuous_native_service_deflection(
        _project(),
        construction=production.construction,
        traffic=production.traffic,
        girder_index=2,
        traffic_factor=0.0,
        allowable_deflection_mm=40.0,
    )

    assert result.governing_case_id is None
    assert result.calculated_max_abs_deflection_mm == pytest.approx(
        result.permanent_only_max_abs_deflection_mm,
        rel=1.0e-12,
        abs=1.0e-12,
    )



def test_continuous_native_shear_torsion_keeps_v_and_t_colocated() -> None:
    production = _run(girder_index=1)
    result = check_project_continuous_native_matched_shear_torsion(
        _project(),
        production=production,
        section=ContinuousShearDesignInput(
            web_width_m=0.40,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
            provided_asw_per_s_mm2_per_m=1600.0,
        ),
        torsion_cell=TorsionCellInput(
            ak_m2=0.10,
            uk_m=1.40,
            tef_m=0.15,
        ),
    )

    assert result.evaluated_points
    assert result.governing_torsion.design_torsion_knm >= 0.0
    assert result.governing_interaction.interaction.utilization >= 0.0
    point = result.governing_interaction
    assert point.member_end in {"I", "J"}
    assert point.side in {"left", "right"}
    assert point.gamma_g in {1.0, 1.35}
    assert "same section" in result.status
