import csv
import io

import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.research.line_benchmark import (
    CONTINUOUS_LINE_BENCHMARK_CASE_IDS,
    build_continuous_line_benchmark_package,
    continuous_line_benchmark_case_specs,
    default_continuous_line_campaign_spec,
)
from rc_bridge.research.verification import SolverProfile
from rc_bridge.research.verification_campaign import BenchmarkCaseSpec
from rc_bridge.workflow.project_continuous import ProjectContinuousLoadCase


def _project() -> ProjectInput:
    return ProjectInput(
        name="Controlled benchmark bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )


def _case() -> ProjectContinuousLoadCase:
    return ProjectContinuousLoadCase(
        ei_kn_m2_by_span=(1.0e6, 1.0e6),
        udl_kn_m_by_span=(20.0, 20.0),
        name="equal UDL benchmark",
    )


def test_default_line_campaign_has_stable_case_ids_and_global_components_only() -> None:
    specs = continuous_line_benchmark_case_specs()
    campaign = default_continuous_line_campaign_spec()

    assert tuple(spec.case_id for spec in specs) == CONTINUOUS_LINE_BENCHMARK_CASE_IDS
    assert campaign.required_case_ids == CONTINUOUS_LINE_BENCHMARK_CASE_IDS
    assert campaign.solver_profile == SolverProfile.EUROCODE_CONTINUOUS
    assert all(spec.required_components == ("FZ", "DZ", "RY") for spec in specs)


def test_line_benchmark_package_contains_like_for_like_external_expected_results() -> None:
    spec = continuous_line_benchmark_case_specs()[0]
    package = build_continuous_line_benchmark_package(
        _project(),
        _case(),
        case_spec=spec,
        analysis_area_m2_by_span=(0.45, 0.45),
    )

    rows = list(csv.DictReader(io.StringIO(package.external_expected_results_csv)))
    assert len(rows) == 9
    assert {row["component"] for row in rows} == {"FZ", "DZ", "RY"}
    assert {row["result_type"] for row in rows} == {
        "support_reaction",
        "node_displacement",
        "node_rotation",
    }

    # Classical two equal spans under equal UDL: outer reactions = 3wL/8,
    # centre reaction = 5wL/4.
    reactions = {
        int(row["object_id"]): float(row["value"])
        for row in rows
        if row["component"] == "FZ"
    }
    assert reactions[1] == pytest.approx(75.0)
    assert reactions[2] == pytest.approx(250.0)
    assert reactions[3] == pytest.approx(75.0)

    internal_nodes = package.verification_package.expected_results_csv
    assert "M_max_sagging" in internal_nodes
    assert "V_i" in internal_nodes

    files = package.files()
    assert f"{spec.case_id}_external_expected_results.csv" in files
    assert f"{spec.case_id}.mct" in files
    assert f"{spec.case_id}.std" in files


def test_line_external_ry_is_opposite_internal_upward_slope_theta() -> None:
    spec = continuous_line_benchmark_case_specs()[0]
    package = build_continuous_line_benchmark_package(
        _project(),
        _case(),
        case_spec=spec,
        analysis_area_m2_by_span=(0.45, 0.45),
    )
    rows = list(csv.DictReader(io.StringIO(package.external_expected_results_csv)))
    rotations = {
        int(row["object_id"]): float(row["value"])
        for row in rows
        if row["component"] == "RY"
    }
    rich_rows = list(
        csv.DictReader(io.StringIO(package.verification_package.expected_results_csv))
    )
    internal_theta = {
        int(row["object_id"]): float(row["value"])
        for row in rich_rows
        if row["result_type"] == "support_rotation"
    }
    assert rotations.keys() == internal_theta.keys()
    for node_id, rotation in rotations.items():
        assert rotation == pytest.approx(-internal_theta[node_id])


def test_first_stage_line_package_rejects_uncalibrated_member_force_requirement() -> None:
    spec = BenchmarkCaseSpec(
        case_id="premature-member-force-case",
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        required_components=("FZ", "M_VERTICAL"),
    )
    with pytest.raises(ValueError, match="uncalibrated components"):
        build_continuous_line_benchmark_package(
            _project(),
            _case(),
            case_spec=spec,
            analysis_area_m2_by_span=(0.45, 0.45),
        )
