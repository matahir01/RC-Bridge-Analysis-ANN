import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import (
    BridgeGeometry,
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
)
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.lm1_grillage_search import (
    LM1GirderGoverningEnvelope,
    LM1GoverningComponent,
    ProjectNativeLM1GrillageSearchResult,
)
from rc_bridge.workflow.project_bridge import SLSCombinationChoice
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3FatigueDesignInput,
    NativeFLM3GirderMomentRange,
    ProjectNativeFLM3GrillageSearchResult,
)
from rc_bridge.workflow.project_native_sections import (
    run_project_all_layered_girders_from_native_lm1,
    run_project_layered_girder_from_native_lm1,
)


class _Placement:
    def __init__(self, case_id: int):
        self.case_id = case_id


class _Case:
    def __init__(self, case_id: int):
        self.placement = _Placement(case_id)

    def __eq__(self, other) -> bool:
        return isinstance(other, _Case) and self.placement.case_id == other.placement.case_id


class _SuiteCase:
    def __init__(self, case):
        self.case = case
        self.case_id = case.placement.case_id


def _search() -> ProjectNativeLM1GrillageSearchResult:
    cases = tuple(_Case(case_id) for case_id in (1, 2, 3))
    girders = tuple(
        LM1GirderGoverningEnvelope(
            girder_index=index,
            y_m=-5.1 + (index - 1) * 1.7,
            moment_knm=LM1GoverningComponent(180.0 + 15.0 * index, 1, 10 + index),
            shear_kn=LM1GoverningComponent(80.0 + 8.0 * index, 2, 20 + index),
            torsion_knm=LM1GoverningComponent(4.0 + 2.0 * index, 3, 30 + index),
        )
        for index in range(1, 8)
    )
    return ProjectNativeLM1GrillageSearchResult(
        cases=cases,
        girders=girders,
        longitudinal_step_m=0.5,
        search_strategy="test-native-search",
        tandem_combinations_exhaustive=True,
        theoretical_tandem_combinations_per_transverse_layout=100,
        udl_pattern_count=1,
    )


def _benchmark(search):
    suite = LM1GoverningBenchmarkSuite(
        cases=tuple(_SuiteCase(case) for case in search.cases)
    )
    reports = tuple(
        LM1ExternalGrillageBenchmarkReport(
            case_id=case_id,
            source_name="MIDAS Civil",
            comparisons=(type("Comparison", (), {"passes": True})(),),
        )
        for case_id in search.governing_case_ids
    )
    report = LM1ExternalBenchmarkSuiteReport(
        source_name="MIDAS Civil",
        case_reports=reports,
        missing_case_ids=(),
        unexpected_case_ids=(),
    )
    return suite, report


def _section() -> LayeredGirderDesignInput:
    return LayeredGirderDesignInput(
        composite_slab_width_m=1.70,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
        provided_shear_asw_per_s_mm2_per_m=1800.0,
    )


def _profiles():
    return (
        (SectionType.RECTANGULAR, RectangularGirderProfile(width_m=0.45, depth_m=0.95)),
        (
            SectionType.T,
            TGirderProfile(
                flange_width_m=0.70, flange_thickness_m=0.15,
                web_width_m=0.30, total_depth_m=0.95,
            ),
        ),
        (
            SectionType.I,
            IGirderProfile(
                top_flange_width_m=0.60, top_flange_thickness_m=0.15,
                web_width_m=0.25, web_depth_m=0.60,
                bottom_flange_width_m=0.55, bottom_flange_thickness_m=0.20,
            ),
        ),
    )


@pytest.mark.parametrize("section_type,profile", _profiles())
def test_native_layered_adapter_runs_all_supported_physical_profiles(
    section_type, profile
) -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(section_type=section_type, girder_profile=profile)
    )
    search = _search()
    suite, report = _benchmark(search)
    result = run_project_layered_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert result.section_type == section_type
    assert result.benchmark_source == "MIDAS Civil"
    assert result.design.uls_design.flexure.resistance_knm > 0.0
    assert result.design.crack.crack_width_mm >= 0.0
    assert result.detailing.selected_longitudinal_bars.provided_area_mm2 > 0.0
    assert result.traffic_trace.moment_knm.case_id == 1


def test_native_layered_adapter_designs_all_girders_and_reports_governing_lines() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70, flange_thickness_m=0.15,
                web_width_m=0.30, total_depth_m=0.95,
            ),
        )
    )
    search = _search()
    suite, report = _benchmark(search)
    result = run_project_all_layered_girders_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        sections_by_girder={index: _section() for index in range(1, 8)},
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert len(result.girders) == 7
    assert result.governing_moment_girder_index == max(
        result.girders,
        key=lambda item: item.combinations.persistent_uls.effects.moment_knm,
    ).combinations.girder_index
    assert result.governing_shear_girder_index == max(
        result.girders,
        key=lambda item: abs(item.combinations.persistent_uls.effects.shear_kn),
    ).combinations.girder_index
    assert result.governing_torsion_girder_index == max(
        result.girders,
        key=lambda item: abs(item.combinations.persistent_uls.effects.torsion_knm),
    ).combinations.girder_index



def _fatigue_search() -> ProjectNativeFLM3GrillageSearchResult:
    ranges = tuple(
        NativeFLM3GirderMomentRange(
            girder_index=index,
            y_m=-5.1 + (index - 1) * 1.7,
            section_position_m=7.5,
            minimum_moment_knm=0.0,
            maximum_moment_knm=120.0 + 10.0 * index,
            moment_range_knm=120.0 + 10.0 * index,
            minimum_case_id=None,
            maximum_case_id=index,
            minimum_lead_position_m=None,
            maximum_lead_position_m=7.5,
            minimum_member_id=None,
            maximum_member_id=100 + index,
        )
        for index in range(1, 8)
    )
    return ProjectNativeFLM3GrillageSearchResult(
        cases=(),
        girders=ranges,
        span_m=15.0,
        vehicle_centre_y_m=0.0,
        axle_load_factor=1.0,
        movement_step_m=0.5,
        section_step_m=0.5,
        status="synthetic fatigue-range fixture",
    )


@pytest.mark.parametrize("section_type,profile", _profiles())
def test_native_layered_adapter_can_carry_flm3_fatigue_for_all_profiles(
    section_type, profile
) -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(section_type=section_type, girder_profile=profile)
    )
    search = _search()
    suite, report = _benchmark(search)
    result = run_project_layered_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        fatigue_search=_fatigue_search(),
        fatigue_design=NativeFLM3FatigueDesignInput(
            lambda_s=0.90,
            characteristic_fatigue_strength_mpa=162.5,
        ),
    )

    assert result.fatigue is not None
    assert result.fatigue.reference_steel_stress_range_mpa > 0.0
    assert "FLM3" in result.fatigue.fatigue.source_description
    assert project.geometry.section_type.value in result.fatigue.fatigue.source_description
