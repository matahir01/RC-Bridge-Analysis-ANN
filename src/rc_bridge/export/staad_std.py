from __future__ import annotations

import re

from rc_bridge.export.verification_model import VerificationModel, VerificationSupport


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]", "_", value.strip())
    if not text:
        return "ITEM"
    if text[0].isdigit():
        return f"N_{text}"
    return text[:32]


def _staad_id_list(values: list[int]) -> str:
    """Compress sorted positive STAAD entity IDs into compact TO ranges."""
    if not values:
        return ""
    ordered = sorted(set(values))
    tokens: list[str] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value == previous + 1:
            previous = value
            continue
        if start == previous:
            tokens.append(str(start))
        elif previous == start + 1:
            tokens.extend((str(start), str(previous)))
        else:
            tokens.extend((str(start), "TO", str(previous)))
        start = previous = value
    if start == previous:
        tokens.append(str(start))
    elif previous == start + 1:
        tokens.extend((str(start), str(previous)))
    else:
        tokens.extend((str(start), "TO", str(previous)))
    return " ".join(tokens)

def _support_command(support: VerificationSupport) -> str:
    restrained = (support.ux, support.uy, support.uz, support.rx, support.ry, support.rz)
    if all(restrained):
        return f"{support.node_id} FIXED"
    if restrained[:3] == (True, True, True) and restrained[3:] == (False, False, False):
        return f"{support.node_id} PINNED"

    labels = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    released = [
        label
        for label, is_restrained in zip(labels, restrained, strict=True)
        if not is_restrained
    ]
    if not released:
        return f"{support.node_id} FIXED"
    return f"{support.node_id} FIXED BUT {' '.join(released)}"


def _global_member_force_print_commands(
    model: VerificationModel,
    *,
    members_per_command: int = 40,
) -> list[str]:
    if members_per_command < 1:
        raise ValueError("members_per_command must be positive.")
    member_ids = [beam.member_id for beam in model.beams]
    return [
        "PRINT MEMBER FORCES GLOBAL LIST " + " ".join(str(value) for value in chunk)
        for start in range(0, len(member_ids), members_per_command)
        if (chunk := member_ids[start : start + members_per_command])
    ]


def export_staad_std(model: VerificationModel) -> str:
    """Render a STAAD.Pro ``.std`` verification model in kN-m units.

    The exporter intentionally writes numerical prismatic properties (AX/IX/IY/IZ)
    instead of asking STAAD to infer them from nominal dimensions. That keeps the
    external stiffness aligned with the deterministic solver and avoids automatic
    shear-deformation assumptions unless explicit AY/AZ values are supplied.

    The verification model uses global Z as vertical, matching the native grillage
    convention; SET Z UP is therefore emitted before geometry so STAAD displays the
    bridge deck in its horizontal X-Y plane. Post-analysis member-end forces are
    requested in the global coordinate system so the verification return path is not
    forced to infer STAAD member local axes.
    """
    model.validate_load_positions()
    lines: list[str] = [
        f"STAAD SPACE {_safe_name(model.name)}",
        "START JOB INFORMATION",
        "ENGINEER NAME RC_BRIDGE_ANALYSIS_ANN",
        "END JOB INFORMATION",
        "SET Z UP",
        "UNIT METER KNS",
        "JOINT COORDINATES",
    ]
    lines.extend(
        f"{node.node_id} {node.x_m:.9g} {node.y_m:.9g} {node.z_m:.9g};"
        for node in model.nodes
    )

    lines.append("MEMBER INCIDENCES")
    lines.extend(f"{beam.member_id} {beam.node_i} {beam.node_j};" for beam in model.beams)

    lines.append("MEMBER PROPERTY")
    for section in model.sections:
        member_ids = [
            beam.member_id for beam in model.beams if beam.section_id == section.section_id
        ]
        if not member_ids:
            continue
        properties = [
            f"AX {section.area_m2:.12g}",
            f"IX {section.torsion_constant_m4:.12g}",
            f"IY {section.iy_m4:.12g}",
            f"IZ {section.iz_m4:.12g}",
        ]
        if section.shear_area_y_m2 is not None:
            properties.append(f"AY {section.shear_area_y_m2:.12g}")
        if section.shear_area_z_m2 is not None:
            properties.append(f"AZ {section.shear_area_z_m2:.12g}")
        lines.append(f"{_staad_id_list(member_ids)} PRIS {' '.join(properties)}")

    lines.append("DEFINE MATERIAL START")
    for material in model.materials:
        name = _safe_name(material.name)
        lines.extend(
            [
                f"ISOTROPIC {name}",
                f"E {material.elastic_modulus_kn_m2:.12g}",
                f"POISSON {material.poisson_ratio:.12g}",
                f"DENSITY {material.weight_density_kn_m3:.12g}",
                f"ALPHA {material.thermal_expansion_per_c:.12g}",
            ]
        )
    lines.append("END DEFINE MATERIAL")

    lines.append("CONSTANTS")
    for material in model.materials:
        member_ids = [
            beam.member_id for beam in model.beams if beam.material_id == material.material_id
        ]
        if member_ids:
            lines.append(
                f"MATERIAL {_safe_name(material.name)} MEMB {_staad_id_list(member_ids)}"
            )

    if model.supports:
        lines.append("SUPPORTS")
        lines.extend(_support_command(support) for support in model.supports)

    for load_case in model.load_cases:
        lines.append(f"LOAD {load_case.load_case_id} LOADTYPE None TITLE {_safe_name(load_case.name)}")
        if load_case.self_weight_gz_factor != 0.0:
            lines.append(f"SELFWEIGHT Z {load_case.self_weight_gz_factor:.12g}")
        if load_case.uniform_loads or load_case.point_loads:
            lines.append("MEMBER LOAD")
            for load in load_case.uniform_loads:
                suffix = ""
                if load.start_m is not None and load.end_m is not None:
                    suffix = f" {load.start_m:.12g} {load.end_m:.12g}"
                lines.append(
                    f"{load.member_id} UNI {load.direction} {load.magnitude_kn_m:.12g}{suffix}"
                )
            for load in load_case.point_loads:
                lines.append(
                    f"{load.member_id} CON {load.direction} {load.magnitude_kn:.12g} "
                    f"{load.distance_from_i_m:.12g}"
                )
        if load_case.nodal_loads:
            lines.append("JOINT LOAD")
            for load in load_case.nodal_loads:
                terms = (
                    ("FX", load.fx_kn),
                    ("FY", load.fy_kn),
                    ("FZ", load.fz_kn),
                    ("MX", load.mx_knm),
                    ("MY", load.my_knm),
                    ("MZ", load.mz_knm),
                )
                active = " ".join(
                    f"{name} {value:.12g}" for name, value in terms if value != 0.0
                )
                if active:
                    lines.append(f"{load.node_id} {active}")

    lines.extend(["PERFORM ANALYSIS", "PRINT SUPPORT REACTION ALL"])
    lines.extend(_global_member_force_print_commands(model))
    lines.extend(["PRINT JOINT DISPLACEMENTS ALL", "FINISH"])
    return "\n".join(lines) + "\n"
