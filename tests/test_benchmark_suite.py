import json

import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.research.benchmark_suite import (
    ControlledLineBenchmarkParameters,
    build_standard_continuous_line_benchmark_suite,
)
from rc_bridge.research.line_benchmark import CONTINUOUS_LINE_BENCHMARK_CASE_IDS


def _project() -> ProjectInput:
    return ProjectInput(
        name="External verification suite",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 12.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )


def test_standard_suite_builds_all_four_controlled_cases_and_files() -> None:
    suite = build_standard_continuous_line_benchmark_suite(
        _project(),
        ei_kn_m2_by_span=(1.0e6, 1.2e6),
        analysis_area_m2_by_span=(0.45, 0.50),
    )

    assert tuple(package.case_spec.case_id for package in suite.packages) == (
        CONTINUOUS_LINE_BENCHMARK_CASE_IDS
    )
    files = suite.files()
    assert len(files) == 4 * 5
    for case_id in CONTINUOUS_LINE_BENCHMARK_CASE_IDS:
        assert f"{case_id}.mct" in files
        assert f"{case_id}.std" in files
        assert f"{case_id}_manifest.json" in files
        assert f"{case_id}_expected_results.csv" in files
        assert f"{case_id}_external_expected_results.csv" in files


def test_standard_suite_load_cases_are_traceable_and_synthetic() -> None:
    params = ControlledLineBenchmarkParameters(
        equal_udl_kn_m=21.0,
        asymmetric_udl_kn_m=22.0,
        point_load_kn=110.0,
        mixed_udl_span_1_kn_m=16.0,
        mixed_udl_span_2_kn_m=11.0,
        mixed_point_load_kn=90.0,
    )
    suite = build_standard_continuous_line_benchmark_suite(
        _project(),
        ei_kn_m2_by_span=(1.0e6, 1.2e6),
        analysis_area_m2_by_span=(0.45, 0.50),
        parameters=params,
    )

    equal_manifest = json.loads(suite.packages[0].verification_package.manifest_json)
    point_model = suite.packages[2].verification_package.midas_mct
    mixed_model = suite.packages[3].verification_package.midas_mct

    assert equal_manifest["load_cases"] == ["continuous-2span-equal-udl"]
    assert "21" in suite.packages[0].verification_package.midas_mct
    assert "110" in point_model
    # Second-span midspan = 10 + 12/2 = 16 m globally, i.e. 6 m from span-2 I end.
    assert "6, -90" in mixed_model


def test_standard_suite_rejects_non_two_span_project() -> None:
    project = ProjectInput(
        name="Three span",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )
    with pytest.raises(ValueError, match="exactly two spans"):
        build_standard_continuous_line_benchmark_suite(
            project,
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            analysis_area_m2_by_span=(0.45, 0.45),
        )
