from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from rc_bridge.core.models import ProjectInput
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.export.verification_package import (
    VerificationExportPackage,
    build_verification_export_package,
)
from rc_bridge.research.verification import SolverProfile
from rc_bridge.research.verification_campaign import (
    BenchmarkCaseSpec,
    VerificationCampaignSpec,
)
from rc_bridge.workflow.project_continuous import (
    ProjectContinuousAnalysisResult,
    ProjectContinuousLoadCase,
    run_project_continuous_load_case,
)
from rc_bridge.workflow.verification_export import build_project_continuous_verification_model

CONTINUOUS_LINE_BENCHMARK_CASE_IDS = (
    "continuous-2span-equal-udl",
    "continuous-2span-asymmetric-udl",
    "continuous-2span-point-load",
    "continuous-2span-mixed-load",
)

_FIRST_STAGE_COMPONENTS = ("FZ", "DZ", "RY")
_RESULT_COLUMNS = (
    "result_type",
    "object_id",
    "span_index",
    "position_m",
    "component",
    "value",
    "unit",
)


@dataclass(frozen=True)
class ContinuousLineBenchmarkPackage:
    case_spec: BenchmarkCaseSpec
    verification_model: VerificationModel
    verification_package: VerificationExportPackage
    external_expected_results_csv: str

    def files(self, base_name: str | None = None) -> dict[str, str]:
        stem = base_name or self.case_spec.case_id
        files = dict(self.verification_package.files(stem))
        normalized_stem = next(iter(files)).rsplit(".", 1)[0]
        files[f"{normalized_stem}_external_expected_results.csv"] = (
            self.external_expected_results_csv
        )
        return files


def continuous_line_benchmark_case_specs() -> tuple[BenchmarkCaseSpec, ...]:
    """Return stable first-stage external benchmark case identities.

    These cases deliberately require only globally unambiguous result components.
    Member-end force components will be added after sign convention calibration
    against at least one real MIDAS/STAAD round trip.
    """
    descriptions = {
        "continuous-2span-equal-udl": "Equal two-span continuous beam under symmetric UDL.",
        "continuous-2span-asymmetric-udl": "Two-span continuous beam under asymmetric UDL.",
        "continuous-2span-point-load": "Two-span continuous beam under an isolated point load.",
        "continuous-2span-mixed-load": "Two-span continuous beam under combined UDL and point loads.",
    }
    return tuple(
        BenchmarkCaseSpec(
            case_id=case_id,
            solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
            required_components=_FIRST_STAGE_COMPONENTS,
            description=descriptions[case_id],
        )
        for case_id in CONTINUOUS_LINE_BENCHMARK_CASE_IDS
    )


def default_continuous_line_campaign_spec() -> VerificationCampaignSpec:
    return VerificationCampaignSpec(
        name="Eurocode continuous longitudinal solver external benchmark campaign",
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        required_case_ids=CONTINUOUS_LINE_BENCHMARK_CASE_IDS,
    )


def _write_external_expected_results(
    analysis: ProjectContinuousAnalysisResult,
) -> str:
    """Write quantities whose global sign conventions are already explicit.

    The internal beam solver uses an upward-positive transverse displacement and
    stores ``theta = dz/dx``. For a member running in +global X, a positive global
    rotation about +Y rotates +X toward -Z by the right-hand rule. Therefore the
    external global rotation expected from MIDAS/STAAD is ``RY = -theta``.
    """
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_RESULT_COLUMNS)
    for node in analysis.solution.nodes:
        node_id = node.node_index + 1
        writer.writerow(
            [
                "support_reaction",
                node_id,
                "",
                "",
                "FZ",
                format(node.vertical_reaction_kn, ".17g"),
                "kN",
            ]
        )
        writer.writerow(
            [
                "node_displacement",
                node_id,
                "",
                "",
                "DZ",
                format(node.vertical_displacement_m, ".17g"),
                "m",
            ]
        )
        writer.writerow(
            [
                "node_rotation",
                node_id,
                "",
                "",
                "RY",
                format(-node.rotation_rad, ".17g"),
                "rad",
            ]
        )
    return stream.getvalue()


def build_continuous_line_benchmark_package(
    project: ProjectInput,
    load_case: ProjectContinuousLoadCase,
    *,
    case_spec: BenchmarkCaseSpec,
    analysis_area_m2_by_span: tuple[float, ...] | None = None,
    torsion_constant_m4_by_span: tuple[float, ...] | None = None,
) -> ContinuousLineBenchmarkPackage:
    """Build one controlled longitudinal benchmark package from the internal solver."""
    if case_spec.solver_profile != SolverProfile.EUROCODE_CONTINUOUS:
        raise ValueError(
            "Continuous line benchmark package requires the EUROCODE_CONTINUOUS solver profile."
        )
    unsupported = set(case_spec.required_components) - set(_FIRST_STAGE_COMPONENTS)
    if unsupported:
        raise ValueError(
            "First-stage line benchmark cannot require uncalibrated components: "
            + ", ".join(sorted(unsupported))
        )

    analysis = run_project_continuous_load_case(project, load_case)
    model = build_project_continuous_verification_model(
        project,
        load_case,
        analysis_area_m2_by_span=analysis_area_m2_by_span,
        torsion_constant_m4_by_span=torsion_constant_m4_by_span,
    )
    verification_package = build_verification_export_package(model, analysis)
    return ContinuousLineBenchmarkPackage(
        case_spec=case_spec,
        verification_model=model,
        verification_package=verification_package,
        external_expected_results_csv=_write_external_expected_results(analysis),
    )
