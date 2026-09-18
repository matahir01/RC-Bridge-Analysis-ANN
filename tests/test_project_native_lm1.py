import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import (
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkSuite,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.lm1_grillage_search import (
    LM1GirderGoverningEnvelope,
    LM1GoverningComponent,
    ProjectNativeLM1GrillageSearchResult,
)
from rc_bridge.workflow.project_bridge import SLSCombinationChoice
from rc_bridge.workflow.project_native_lm1 import (
    native_lm1_characteristic_envelope,
    project_girder_combinations_from_native_lm1,
    require_native_lm1_external_benchmark,
    run_project_all_t_girders_from_native_lm1,
    run_project_t_girder_from_native_lm1,
)


class _Placement:
    def __init__(self, case_id: int):
        self.case_id = case_id


class _Case:
    def __init__(self, case_id: int, label: str):
        self.placement = _Placement(case_id)
        self.label = label

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, _Case)
            and self.placement.case_id == other.placement.case_id
            and self.label == other.label
        )


class _SuiteCase:
    def __init__(self, case):
        self.case = case
        self.case_id = case.placement.case_id


def _search() -> ProjectNativeLM1GrillageSearchResult:
    cases = tuple(_Case(case_id, f"case-{case_id}") for case_id in (1, 2, 3))
    girders = tuple(
        LM1GirderGoverningEnvelope(
            girder_index=girder_index,
            y_m=-5.1 + (girder_index - 1) * 1.7,
            moment_knm=LM1GoverningComponent(
                value=180.0 + 15.0 * girder_index,
                case_id=1,
                member_id=10 + girder_index,
            ),
            shear_kn=LM1GoverningComponent(
                value=80.0 + 8.0 * girder_index,
                case_id=2,
                member_id=20 + girder_index,
            ),
            torsion_knm=LM1GoverningComponent(
                value=4.0 + 2.0 * girder_index,
                case_id=3,
                member_id=30 + girder_index,
            ),
        )
        for girder_index in range(1, 8)
    )
    return ProjectNativeLM1GrillageSearchResult(
        cases=cases,
        girders=girders,
        longitudinal_step_m=0.5,
        search_strategy="exhaustive-independent-tandem+full-length-udl",
        tandem_combinations_exhaustive=True,
        theoretical_tandem_combinations_per_transverse_layout=100,
        udl_pattern_count=1,
    )


def _benchmark(search, *, passes: bool = True):
    suite = LM1GoverningBenchmarkSuite(
        cases=tuple(_SuiteCase(case) for case in search.cases)
    )
    reports = tuple(
        LM1ExternalGrillageBenchmarkReport(
            case_id=case_id,
            source_name="MIDAS Civil",
            comparisons=(type("Comparison", (), {"passes": passes})(),),
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


def _sls() -> ServiceabilityPsiFactors:
    return ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)


def test_native_lm1_design_gate_requires_passing_exact_external_benchmark() -> None:
    search = _search()
    suite, failed = _benchmark(search, passes=False)

    with pytest.raises(RuntimeError, match="remains locked"):
        require_native_lm1_external_benchmark(
            search,
            benchmark_suite=suite,
            benchmark_report=failed,
        )

    passing_suite, passing = _benchmark(search)
    wrong_search = _search()
    wrong_search.cases[0].label = "different"
    with pytest.raises(RuntimeError, match="different native search case"):
        require_native_lm1_external_benchmark(
            wrong_search,
            benchmark_suite=passing_suite,
            benchmark_report=passing,
        )


def test_native_lm1_envelope_retains_independent_m_v_t_governing_values() -> None:
    search = _search()
    suite, report = _benchmark(search)

    envelope = native_lm1_characteristic_envelope(
        search,
        benchmark_suite=suite,
        benchmark_report=report,
    )

    effects = envelope.effect_for_girder(4)
    trace = search.girders[3]
    assert effects.moment_knm == pytest.approx(trace.moment_knm.value)
    assert effects.shear_kn == pytest.approx(trace.shear_kn.value)
    assert effects.torsion_knm == pytest.approx(trace.torsion_knm.value)
    assert envelope.metadata.source_software == "RC-Bridge native vertical grillage"
    assert "MIDAS Civil" in envelope.metadata.method


def test_native_lm1_combinations_support_edge_girders_with_edge_tributary_width() -> None:
    project = ProjectInput()
    search = _search()
    suite, report = _benchmark(search)

    combinations = project_girder_combinations_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=1,
        sls_factors=_sls(),
    )

    assert combinations.permanent_characteristic.moment_knm == pytest.approx(219.7265625)
    assert combinations.traffic_characteristic.moment_knm == pytest.approx(195.0)
    assert combinations.traffic_characteristic.shear_kn == pytest.approx(88.0)
    assert combinations.traffic_characteristic.torsion_knm == pytest.approx(6.0)
    assert combinations.persistent_uls.effects.torsion_knm == pytest.approx(9.0)
    assert "externally_benchmarked_native_lm1" in combinations.traffic_distribution_method


def test_native_lm1_runs_full_simple_span_t_girder_design_path() -> None:
    project = ProjectInput()
    search = _search()
    suite, report = _benchmark(search)

    result = run_project_t_girder_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        girder_index=4,
        section=_section(),
        sls_factors=_sls(),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert result.benchmark_source == "MIDAS Civil"
    assert result.traffic_trace.moment_knm.case_id == 1
    assert result.traffic_trace.shear_kn.case_id == 2
    assert result.traffic_trace.torsion_knm.case_id == 3
    assert result.design.uls_design.flexure.resistance_knm > 0.0
    assert result.design.uls_design.shear.design_shear_kn > 0.0
    assert result.design.crack.crack_width_mm >= 0.0
    assert result.design.deflection.interpolated_deflection_mm >= 0.0
    assert result.uls_torsion_knm == pytest.approx(
        result.combinations.persistent_uls.effects.torsion_knm
    )


def test_native_lm1_can_design_all_girders_and_identify_governing_lines() -> None:
    project = ProjectInput()
    search = _search()
    suite, report = _benchmark(search)
    sections = {index: _section() for index in range(1, 8)}

    result = run_project_all_t_girders_from_native_lm1(
        project,
        search=search,
        benchmark_suite=suite,
        benchmark_report=report,
        sections_by_girder=sections,
        sls_factors=_sls(),
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert len(result.girders) == 7
    assert result.governing_moment_girder_index == 7
    assert result.governing_shear_girder_index == 7
    assert result.governing_torsion_girder_index == 7
    assert result.search_strategy == search.search_strategy
