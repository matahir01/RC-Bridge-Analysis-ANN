from types import SimpleNamespace

import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import (
    BridgeGeometry,
    ProjectInput,
    SectionType,
    TGirderProfile,
)
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    LM1ExternalGrillageBenchmarkReport,
    build_lm1_benchmark_suite_for_case_ids,
    compare_lm1_external_grillage_case,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import run_project_native_lm1_grillage_search
from rc_bridge.workflow.project_bridge import SLSCombinationChoice
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3FatigueDesignInput,
    run_project_native_flm3_grillage_search,
)
from rc_bridge.workflow.project_native_lm1 import run_project_t_girder_from_native_lm1
from rc_bridge.workflow.project_native_lm1_torsion import (
    check_project_native_lm1_matched_shear_torsion,
)
from rc_bridge.workflow.project_native_sections import (
    run_project_layered_girder_from_native_lm1,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput


def _longitudinal() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.025,
        iy_m4=0.05,
        iz_m4=0.08,
    )


def _transverse() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.012,
        iy_m4=0.018,
        iz_m4=0.025,
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


@pytest.fixture(scope="module")
def native_benchmark_case():
    project = ProjectInput()
    search = run_project_native_lm1_grillage_search(
        project,
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=15.0,
    )
    all_case_ids = tuple(sorted(case.placement.case_id for case in search.cases))
    suite = build_lm1_benchmark_suite_for_case_ids(search, all_case_ids)
    reports = tuple(
        compare_lm1_external_grillage_case(
            case,
            external_results_csv=case.native_expected_results_csv,
            source_name="MIDAS-format native round trip",
        )
        for case in suite.cases
    )
    report = LM1ExternalBenchmarkSuiteReport(
        source_name="MIDAS Civil",
        case_reports=reports,
        missing_case_ids=(),
        unexpected_case_ids=(),
    )
    return project, search, suite, report


def test_matched_native_lm1_torsion_uses_same_case_and_member_end(
    native_benchmark_case,
) -> None:
    project, search, suite, report = native_benchmark_case
    result = check_project_native_lm1_matched_shear_torsion(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
    )

    assert result.evaluated_points
    assert result.benchmark_source == "MIDAS Civil"
    assert result.governing_torsion.design_torsion_knm == pytest.approx(
        max(point.design_torsion_knm for point in result.evaluated_points)
    )
    assert result.governing_interaction.interaction.utilization == pytest.approx(
        max(point.interaction.utilization for point in result.evaluated_points)
    )
    assert result.governing_torsion.design_torsion_knm == pytest.approx(
        1.50 * search.girders[3].torsion_knm.value
    )
    assert result.governing_interaction.case_id in {
        case.placement.case_id for case in search.cases
    }
    assert result.governing_interaction.member_end in {"I", "J"}
    assert result.governing_interaction.design_shear_kn == pytest.approx(
        1.35 * result.governing_interaction.permanent_shear_kn
        + 1.50 * result.governing_interaction.traffic_shear_kn
    )
    assert result.governing_interaction.design_torsion_knm == pytest.approx(
        1.50 * result.governing_interaction.traffic_torsion_knm
    )


def test_matched_native_lm1_torsion_remains_benchmark_gated(
    native_benchmark_case,
) -> None:
    project, search, suite, report = native_benchmark_case
    failed_reports = tuple(
        LM1ExternalGrillageBenchmarkReport(
            case_id=item.case_id,
            source_name=item.source_name,
            comparisons=(SimpleNamespace(passes=False),),
            member_end_comparisons=item.member_end_comparisons,
        )
        for item in report.case_reports
    )
    failed = LM1ExternalBenchmarkSuiteReport(
        source_name=report.source_name,
        case_reports=failed_reports,
        missing_case_ids=(),
        unexpected_case_ids=(),
    )

    with pytest.raises(RuntimeError, match="remains locked"):
        check_project_native_lm1_matched_shear_torsion(
            project,
            search=search,
            benchmark_suite=suite,
            benchmark_report=failed,
            girder_index=4,
            section=_section(),
            torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
        )


def test_native_lm1_girder_design_can_include_matched_shear_torsion(
    native_benchmark_case,
) -> None:
    project, search, suite, report = native_benchmark_case
    result = run_project_t_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.30,
        ),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
    )

    assert result.shear_torsion is not None
    assert result.envelope_detailing is not None
    assert result.envelope_detailing.longitudinal_zones
    assert result.envelope_detailing.link_zones
    assert result.shear_torsion.governing_torsion.design_torsion_knm == pytest.approx(
        1.50 * search.girders[3].torsion_knm.value
    )
    assert result.shear_torsion.governing_interaction.interaction.utilization >= 0.0
    assert "matched co-located V-T interaction" in result.status



def test_native_lm1_production_result_can_carry_dedicated_flm3_fatigue(
    native_benchmark_case,
) -> None:
    project, search, suite, report = native_benchmark_case
    fatigue_search = run_project_native_flm3_grillage_search(
        project,
        vehicle_centre_y_m=0.0,
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        movement_step_m=15.0,
        section_step_m=5.0,
    )

    result = run_project_t_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.30,
        ),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        fatigue_search=fatigue_search,
        fatigue_design=NativeFLM3FatigueDesignInput(
            lambda_s=0.90,
            characteristic_fatigue_strength_mpa=162.5,
        ),
    )

    assert result.fatigue is not None
    assert result.fatigue.reference_steel_stress_range_mpa > 0.0
    assert "FLM3" in result.fatigue.fatigue.source_description
    assert "without reusing LM1" in result.status



def test_matched_native_lm1_torsion_accepts_physical_layered_section(
    native_benchmark_case,
) -> None:
    _, search, suite, report = native_benchmark_case
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        )
    )
    section = LayeredGirderDesignInput(
        composite_slab_width_m=1.70,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )
    result = check_project_native_lm1_matched_shear_torsion(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=section,
        torsion_cell=TorsionCellInput(ak_m2=0.10, uk_m=1.40, tef_m=0.15),
    )

    assert result.evaluated_points
    assert result.governing_interaction.interaction.utilization >= 0.0
    assert "physical rectangular/T/I profile" in result.status



def test_native_layered_production_builds_envelope_detailing_from_physical_search(
    native_benchmark_case,
) -> None:
    _, search, suite, report = native_benchmark_case
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        )
    )
    section = LayeredGirderDesignInput(
        composite_slab_width_m=1.70,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )
    result = run_project_layered_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=section,
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert result.envelope_detailing is not None
    assert result.envelope_detailing.longitudinal_zones
    assert result.envelope_detailing.link_zones
    assert result.envelope_detailing.stations[0].x_m == pytest.approx(0.0)
    assert result.envelope_detailing.stations[-1].x_m == pytest.approx(15.0)
