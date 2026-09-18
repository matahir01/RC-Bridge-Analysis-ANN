from types import SimpleNamespace

import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import run_project_native_lm1_grillage_search
from rc_bridge.workflow.project_bridge import SLSCombinationChoice
from rc_bridge.workflow.project_native_lm1 import run_project_t_girder_from_native_lm1
from rc_bridge.workflow.project_native_lm1_torsion import (
    check_project_native_lm1_matched_shear_torsion,
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
    cases_by_id = {case.placement.case_id: case for case in search.cases}
    all_case_ids = tuple(sorted(cases_by_id))
    suite = LM1GoverningBenchmarkSuite(
        cases=tuple(
            SimpleNamespace(case_id=case_id, case=cases_by_id[case_id])
            for case_id in all_case_ids
        )
    )
    reports = tuple(
        LM1ExternalGrillageBenchmarkReport(
            case_id=case_id,
            source_name="MIDAS Civil",
            comparisons=(SimpleNamespace(passes=True),),
        )
        for case_id in all_case_ids
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
    assert result.shear_torsion.governing_torsion.design_torsion_knm == pytest.approx(
        1.50 * search.girders[3].torsion_knm.value
    )
    assert result.shear_torsion.governing_interaction.interaction.utilization >= 0.0
    assert "matched co-located V-T interaction" in result.status
