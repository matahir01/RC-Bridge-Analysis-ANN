from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from io import StringIO

from rc_bridge.export.midas_mct import export_midas_mct
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.export.verification_model import VerificationModel


@dataclass(frozen=True)
class ModelVerificationExportPackage:
    """External-model package when no independent internal result set exists yet.

    This package intentionally contains model definitions and the exact exported
    loads only. It does not fabricate expected structural results for analysis
    capabilities that the internal deterministic solver does not yet provide.
    """

    midas_mct: str
    staad_std: str
    manifest_json: str
    exported_loads_csv: str

    def files(self, base_name: str = "bridge_model_verification") -> dict[str, str]:
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", base_name.strip()).strip("_")
        if not stem:
            raise ValueError("Verification package base_name cannot be empty.")
        return {
            f"{stem}.mct": self.midas_mct,
            f"{stem}.std": self.staad_std,
            f"{stem}_manifest.json": self.manifest_json,
            f"{stem}_exported_loads.csv": self.exported_loads_csv,
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _format_float(value: float) -> str:
    return format(float(value), ".17g")


def _exported_loads_csv(model: VerificationModel) -> str:
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "load_case",
            "load_type",
            "object_id",
            "direction",
            "magnitude_1",
            "magnitude_2",
            "position_1_m",
            "position_2_m",
            "fx_kn",
            "fy_kn",
            "fz_kn",
            "mx_knm",
            "my_knm",
            "mz_knm",
        ]
    )

    for case in model.load_cases:
        if case.self_weight_gz_factor != 0.0:
            writer.writerow(
                [
                    case.name,
                    "self_weight",
                    "GLOBAL",
                    "GZ",
                    _format_float(case.self_weight_gz_factor),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

        for load in case.uniform_loads:
            writer.writerow(
                [
                    case.name,
                    "uniform_member_load",
                    load.member_id,
                    load.direction,
                    _format_float(load.magnitude_kn_m),
                    "",
                    "" if load.start_m is None else _format_float(load.start_m),
                    "" if load.end_m is None else _format_float(load.end_m),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

        for load in case.point_loads:
            writer.writerow(
                [
                    case.name,
                    "point_member_load",
                    load.member_id,
                    load.direction,
                    _format_float(load.magnitude_kn),
                    "",
                    _format_float(load.distance_from_i_m),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )

        for load in case.nodal_loads:
            writer.writerow(
                [
                    case.name,
                    "nodal_load",
                    load.node_id,
                    "GLOBAL",
                    "",
                    "",
                    "",
                    "",
                    _format_float(load.fx_kn),
                    _format_float(load.fy_kn),
                    _format_float(load.fz_kn),
                    _format_float(load.mx_knm),
                    _format_float(load.my_knm),
                    _format_float(load.mz_knm),
                ]
            )

    return stream.getvalue()


def build_model_verification_export_package(
    model: VerificationModel,
) -> ModelVerificationExportPackage:
    """Build MIDAS/STAAD model files plus a traceable exported-load manifest."""
    model.validate_load_positions()
    midas = export_midas_mct(model)
    staad = export_staad_std(model)
    loads = _exported_loads_csv(model)
    manifest = {
        "schema_version": 1,
        "package_type": "external_model_verification",
        "model_name": model.name,
        "units": {"length": "m", "force": "kN", "moment": "kNm"},
        "node_count": len(model.nodes),
        "member_count": len(model.beams),
        "section_count": len(model.sections),
        "support_count": len(model.supports),
        "load_cases": [case.name for case in model.load_cases],
        "metadata": model.metadata,
        "files": {
            "midas_mct": {"sha256": _sha256(midas), "extension": ".mct"},
            "staad_std": {"sha256": _sha256(staad), "extension": ".std"},
            "exported_loads_csv": {"sha256": _sha256(loads), "extension": ".csv"},
        },
        "verification_boundary": (
            "This package verifies the exported structural model and loading definition. "
            "It contains no fabricated expected grillage results. External results must be "
            "imported and compared independently before transverse-distribution verification."
        ),
    }
    return ModelVerificationExportPackage(
        midas_mct=midas,
        staad_std=staad,
        manifest_json=json.dumps(manifest, indent=2, sort_keys=True),
        exported_loads_csv=loads,
    )
