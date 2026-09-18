from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING

from rc_bridge.export.midas_mct import export_midas_mct
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.export.verification_model import VerificationModel

if TYPE_CHECKING:
    from rc_bridge.workflow.project_continuous import ProjectContinuousAnalysisResult


@dataclass(frozen=True)
class VerificationExportPackage:
    midas_mct: str
    staad_std: str
    manifest_json: str
    expected_results_csv: str

    def files(self, base_name: str = "bridge_verification") -> dict[str, str]:
        """Return user-facing filenames and UTF-8 file contents for one export action."""
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", base_name.strip()).strip("_")
        if not stem:
            raise ValueError("Verification package base_name cannot be empty.")
        return {
            f"{stem}.mct": self.midas_mct,
            f"{stem}.std": self.staad_std,
            f"{stem}_manifest.json": self.manifest_json,
            f"{stem}_expected_results.csv": self.expected_results_csv,
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_float(value: float) -> str:
    """Serialize a Python float with enough significant digits for exact round-trip recovery."""
    return format(float(value), ".17g")


def _expected_results_csv(analysis: ProjectContinuousAnalysisResult) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "result_type",
            "object_id",
            "span_index",
            "position_m",
            "component",
            "value",
            "unit",
        ]
    )

    for node in analysis.solution.nodes:
        writer.writerow(
            [
                "support_reaction",
                node.node_index + 1,
                "",
                "",
                "FZ",
                _format_float(node.vertical_reaction_kn),
                "kN",
            ]
        )
        writer.writerow(
            [
                "support_rotation",
                node.node_index + 1,
                "",
                "",
                "RY",
                _format_float(node.rotation_rad),
                "rad",
            ]
        )

    for member in analysis.solution.members:
        member_id = member.span_index + 1
        member_rows = (
            (0.0, "V_i", member.left_shear_kn, "kN"),
            (0.0, "M_i", member.left_moment_knm, "kNm"),
            ("J", "V_j", member.right_shear_kn, "kN"),
            ("J", "M_j", member.right_moment_knm, "kNm"),
        )
        for position, component, value, unit in member_rows:
            writer.writerow(
                [
                    "member_end_force",
                    member_id,
                    member.span_index,
                    position,
                    component,
                    _format_float(value),
                    unit,
                ]
            )

    for envelope in analysis.span_envelopes:
        member_id = envelope.span_index + 1
        writer.writerow(
            [
                "span_envelope",
                member_id,
                envelope.span_index,
                _format_float(envelope.max_sagging_position_m),
                "M_max_sagging",
                _format_float(envelope.max_sagging_moment_knm),
                "kNm",
            ]
        )
        writer.writerow(
            [
                "span_envelope",
                member_id,
                envelope.span_index,
                _format_float(envelope.min_hogging_position_m),
                "M_min_hogging",
                _format_float(envelope.min_hogging_moment_knm),
                "kNm",
            ]
        )
        writer.writerow(
            [
                "span_envelope",
                member_id,
                envelope.span_index,
                _format_float(envelope.max_abs_shear_position_m),
                "V_max_abs",
                _format_float(envelope.max_abs_shear_kn),
                "kN",
            ]
        )

    for envelope in analysis.span_deflection_envelopes:
        member_id = envelope.span_index + 1
        writer.writerow(
            [
                "span_deflection",
                member_id,
                envelope.span_index,
                _format_float(envelope.maximum_upward_position_m),
                "DZ_max_upward",
                _format_float(envelope.maximum_upward_displacement_m),
                "m",
            ]
        )
        writer.writerow(
            [
                "span_deflection",
                member_id,
                envelope.span_index,
                _format_float(envelope.minimum_downward_position_m),
                "DZ_min_downward",
                _format_float(envelope.minimum_downward_displacement_m),
                "m",
            ]
        )
        writer.writerow(
            [
                "span_deflection",
                member_id,
                envelope.span_index,
                _format_float(envelope.max_abs_position_m),
                "DZ_max_abs",
                _format_float(envelope.max_abs_displacement_m),
                "m",
            ]
        )

    return stream.getvalue()


def build_verification_export_package(
    model: VerificationModel,
    analysis: ProjectContinuousAnalysisResult,
) -> VerificationExportPackage:
    """Build model files plus traceable expected results for independent checking."""
    if len(model.load_cases) == 1 and model.load_cases[0].name != analysis.load_case_name:
        raise ValueError(
            "Verification model and expected analysis must refer to the same load-case name."
        )

    midas = export_midas_mct(model)
    staad = export_staad_std(model)
    expected = _expected_results_csv(analysis)
    manifest = {
        "schema_version": 1,
        "model_name": model.name,
        "units": {"length": "m", "force": "kN", "moment": "kNm"},
        "node_count": len(model.nodes),
        "member_count": len(model.beams),
        "load_cases": [case.name for case in model.load_cases],
        "metadata": model.metadata,
        "files": {
            "midas_mct": {"sha256": _sha256(midas), "extension": ".mct"},
            "staad_std": {"sha256": _sha256(staad), "extension": ".std"},
            "expected_results_csv": {
                "sha256": _sha256(expected),
                "extension": ".csv",
            },
        },
        "comparison_note": (
            "Expected results come from the internal deterministic solver. External software "
            "results remain independent evidence and must be compared before verification "
            "status is changed."
        ),
    }
    return VerificationExportPackage(
        midas_mct=midas,
        staad_std=staad,
        manifest_json=json.dumps(manifest, indent=2, sort_keys=True),
        expected_results_csv=expected,
    )
