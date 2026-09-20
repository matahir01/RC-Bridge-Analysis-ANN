from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from io import StringIO

from rc_bridge.export.midas_mct import export_midas_mct, midas_result_name_map
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.export.verification_model import VerificationModel


@dataclass(frozen=True)
class ModelVerificationExportPackage:
    """External-model package when no independent internal result set exists yet.

    This package intentionally contains model definitions, the exact exported
    loads, and explicit result-return templates. It does not fabricate expected
    structural results for analysis capabilities that the internal deterministic
    solver does not yet provide.
    """

    midas_mct: str
    staad_std: str
    manifest_json: str
    exported_loads_csv: str
    result_requests_csv: str
    external_results_template_csv: str

    def files(self, base_name: str = "bridge_model_verification") -> dict[str, str]:
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", base_name.strip()).strip("_")
        if not stem:
            raise ValueError("Verification package base_name cannot be empty.")
        return {
            f"{stem}.mct": self.midas_mct,
            f"{stem}.std": self.staad_std,
            f"{stem}_manifest.json": self.manifest_json,
            f"{stem}_exported_loads.csv": self.exported_loads_csv,
            f"{stem}_result_requests.csv": self.result_requests_csv,
            f"{stem}_external_results_template.csv": self.external_results_template_csv,
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


def _result_requests_csv(model: VerificationModel) -> str:
    """Describe the external results needed for a later normalized comparison."""
    stream = StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "result_type",
            "object_id",
            "end",
            "node_id",
            "x_m",
            "y_m",
            "z_m",
            "semantic_component",
            "unit",
            "mapping_note",
        ]
    )
    nodes = {node.node_id: node for node in model.nodes}

    for support in model.supports:
        node = nodes[support.node_id]
        writer.writerow(
            [
                "support_reaction",
                support.node_id,
                "",
                support.node_id,
                _format_float(node.x_m),
                _format_float(node.y_m),
                _format_float(node.z_m),
                "global_vertical_reaction_FZ",
                "kN",
                "Use the external program global vertical support reaction.",
            ]
        )

    for node in model.nodes:
        writer.writerow(
            [
                "node_displacement",
                node.node_id,
                "",
                node.node_id,
                _format_float(node.x_m),
                _format_float(node.y_m),
                _format_float(node.z_m),
                "global_vertical_displacement_DZ",
                "m",
                "Use the external program global vertical nodal displacement.",
            ]
        )

    force_requests = (
        ("vertical_plane_shear", "kN"),
        ("vertical_plane_bending_moment", "kNm"),
        ("member_torsion", "kNm"),
    )
    for beam in model.beams:
        for end_label, current_node_id in (("I", beam.node_i), ("J", beam.node_j)):
            node = nodes[current_node_id]
            for component, unit in force_requests:
                writer.writerow(
                    [
                        "member_end_force",
                        beam.member_id,
                        end_label,
                        current_node_id,
                        _format_float(node.x_m),
                        _format_float(node.y_m),
                        _format_float(node.z_m),
                        component,
                        unit,
                        (
                            "STAAD: use GLOBAL member-end vectors and project by member geometry. "
                            "MIDAS: use ECS forces only through the horizontal beta-zero profile."
                        ),
                    ]
                )

    return stream.getvalue()


def _external_results_template_csv(model: VerificationModel) -> str:
    """Return the normalized result table identity rows with blank value cells."""
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

    for support in model.supports:
        writer.writerow(["support_reaction", support.node_id, "", "", "FZ", "", "kN"])

    for node in model.nodes:
        writer.writerow(["node_displacement", node.node_id, "", "", "DZ", "", "m"])

    member_components = (
        ("V_VERTICAL", "kN"),
        ("M_VERTICAL", "kNm"),
        ("T", "kNm"),
    )
    for beam in model.beams:
        for end_label in ("I", "J"):
            for component, unit in member_components:
                writer.writerow(
                    [
                        "member_end_force",
                        beam.member_id,
                        "",
                        end_label,
                        component,
                        "",
                        unit,
                    ]
                )

    return stream.getvalue()


def build_model_verification_export_package(
    model: VerificationModel,
) -> ModelVerificationExportPackage:
    """Build MIDAS/STAAD model files plus traceable load/result-return manifests."""
    model.validate_load_positions()
    midas = export_midas_mct(model)
    staad = export_staad_std(model)
    midas_names = midas_result_name_map(model)
    loads = _exported_loads_csv(model)
    requests = _result_requests_csv(model)
    external_template = _external_results_template_csv(model)
    manifest = {
        "schema_version": 1,
        "package_type": "external_model_verification",
        "model_name": model.name,
        "units": {"length": "m", "force": "kN", "moment": "kNm"},
        "node_count": len(model.nodes),
        "member_count": len(model.beams),
        "section_count": len(model.sections),
        "support_count": len(model.supports),
        "model_audit": {
            "nodes": [
                {
                    "node_id": node.node_id,
                    "x_m": node.x_m,
                    "y_m": node.y_m,
                    "z_m": node.z_m,
                }
                for node in model.nodes
            ],
            "members": [
                {
                    "member_id": beam.member_id,
                    "node_i": beam.node_i,
                    "node_j": beam.node_j,
                    "material_id": beam.material_id,
                    "section_id": beam.section_id,
                    "beta_angle_deg": beam.beta_angle_deg,
                }
                for beam in model.beams
            ],
            "materials": [
                {
                    "material_id": material.material_id,
                    "name": material.name,
                    "elastic_modulus_kn_m2": material.elastic_modulus_kn_m2,
                    "poisson_ratio": material.poisson_ratio,
                    "weight_density_kn_m3": material.weight_density_kn_m3,
                    "thermal_expansion_per_c": material.thermal_expansion_per_c,
                }
                for material in model.materials
            ],
            "sections": [
                {
                    "section_id": section.section_id,
                    "name": section.name,
                    "area_m2": section.area_m2,
                    "torsion_constant_m4": section.torsion_constant_m4,
                    "iy_m4": section.iy_m4,
                    "iz_m4": section.iz_m4,
                    "shear_area_y_m2": section.shear_area_y_m2,
                    "shear_area_z_m2": section.shear_area_z_m2,
                }
                for section in model.sections
            ],
            "supports": [
                {
                    "node_id": support.node_id,
                    "restraint_code": support.restraint_code,
                }
                for support in model.supports
            ],
        },
        "acceptance_review_requirements": [
            "confirm the analysed external model is the exported model without unreviewed edits",
            "confirm node coordinates, member connectivity and bridge geometry",
            "confirm member section properties and assignments",
            "confirm analysis material properties",
            "confirm supports/releases/restraints",
            "confirm primary load magnitudes, directions and positions",
            "confirm load-combination membership and factors",
            "confirm result axes/sign conventions and semantic component mapping",
            "record external solver version and source/run reference",
        ],
        "load_cases": [case.name for case in model.load_cases],
        "load_combinations": [
            {
                "combination_id": combination.combination_id,
                "name": combination.name,
                "category": combination.category,
                "description": combination.description,
                "terms": [
                    {
                        "load_case_id": term.load_case_id,
                        "factor": term.factor,
                    }
                    for term in combination.terms
                ],
            }
            for combination in model.load_combinations
        ],
        "external_result_identity": {
            "staad": [
                {
                    "result_id": case.load_case_id,
                    "kind": "load_case",
                    "name": case.name,
                }
                for case in model.load_cases
            ]
            + [
                {
                    "result_id": combination.combination_id,
                    "kind": "combination",
                    "name": combination.name,
                }
                for combination in model.load_combinations
            ],
            "midas": [
                {
                    "result_id": case.load_case_id,
                    "kind": "load_case",
                    "export_name": midas_names[("case", case.load_case_id)],
                    "source_name": case.name,
                }
                for case in model.load_cases
            ]
            + [
                {
                    "result_id": combination.combination_id,
                    "kind": "combination",
                    "export_name": midas_names[
                        ("combination", combination.combination_id)
                    ],
                    "source_name": combination.name,
                }
                for combination in model.load_combinations
            ],
        },
        "metadata": model.metadata,
        "files": {
            "midas_mct": {"sha256": _sha256(midas), "extension": ".mct"},
            "staad_std": {"sha256": _sha256(staad), "extension": ".std"},
            "exported_loads_csv": {"sha256": _sha256(loads), "extension": ".csv"},
            "result_requests_csv": {"sha256": _sha256(requests), "extension": ".csv"},
            "external_results_template_csv": {
                "sha256": _sha256(external_template),
                "extension": ".csv",
            },
        },
        "verification_boundary": (
            "This package verifies the exported structural model and loading definition. "
            "It contains no fabricated expected grillage results. External results must be "
            "imported and compared independently before transverse-distribution verification."
        ),
        "result_mapping_note": (
            "STAAD .std files request GLOBAL member forces; the ANL adapter projects those "
            "global vectors onto each horizontal member basis. MIDAS beam forces remain ECS "
            "results and are mapped automatically only for horizontal beta-zero members."
        ),
    }
    return ModelVerificationExportPackage(
        midas_mct=midas,
        staad_std=staad,
        manifest_json=json.dumps(manifest, indent=2, sort_keys=True),
        exported_loads_csv=loads,
        result_requests_csv=requests,
        external_results_template_csv=external_template,
    )
