from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import math
import re

from rc_bridge.export.verification_model import VerificationBeam, VerificationModel


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
class _UnitSystem:
    force_to_kn: float
    length_to_m: float

    @property
    def moment_to_knm(self) -> float:
        return self.force_to_kn * self.length_to_m


_FORCE_TO_KN = {
    "KN": 1.0,
    "KNS": 1.0,
    "KILONEWTON": 1.0,
    "KILONEWTONS": 1.0,
    "N": 0.001,
    "NEWT": 0.001,
    "NEWTON": 0.001,
    "NEWTONS": 0.001,
    "MTON": 9.80665,
    "KG": 0.00980665,
    "KIP": 4.4482216152605,
    "KIPS": 4.4482216152605,
    "POUN": 0.0044482216152605,
    "POUND": 0.0044482216152605,
    "POUNDS": 0.0044482216152605,
}

_LENGTH_TO_M = {
    "M": 1.0,
    "METE": 1.0,
    "METER": 1.0,
    "METERS": 1.0,
    "CM": 0.01,
    "MM": 0.001,
    "FT": 0.3048,
    "FEET": 0.3048,
    "IN": 0.0254,
    "INCH": 0.0254,
    "INCHES": 0.0254,
}

_UNIT_PAIR_RE = re.compile(
    r"(?:-\s*UNIT|ALL\s+UNITS\s+ARE\s*--)\s+([A-Z]+)\s+([A-Z]+)",
    re.IGNORECASE,
)
_DISPLACEMENT_UNIT_RE = re.compile(
    r"JOINT\s+DISPLACEMENT\s*\(\s*([A-Z]+)\s+RADIANS?\s*\)",
    re.IGNORECASE,
)


def _unit_system(force_token: str, length_token: str) -> _UnitSystem:
    force_key = force_token.upper()
    length_key = length_token.upper()
    if force_key not in _FORCE_TO_KN:
        raise ValueError(f"Unsupported STAAD output force unit {force_token!r}.")
    if length_key not in _LENGTH_TO_M:
        raise ValueError(f"Unsupported STAAD output length unit {length_token!r}.")
    return _UnitSystem(
        force_to_kn=_FORCE_TO_KN[force_key],
        length_to_m=_LENGTH_TO_M[length_key],
    )


def _parse_unit_pair(line: str) -> _UnitSystem | None:
    match = _UNIT_PAIR_RE.search(line)
    if match is None:
        return None
    return _unit_system(match.group(1), match.group(2))


def _parse_float(token: str) -> float:
    value = token.strip().replace("D", "E").replace("d", "e")
    return float(value)


def _parse_int(token: str) -> int:
    value = _parse_float(token)
    rounded = round(value)
    if abs(value - rounded) > 1e-9:
        raise ValueError(f"Expected integer STAAD identifier, got {token!r}.")
    return int(rounded)


def _numeric_tokens(line: str) -> list[str] | None:
    tokens = line.replace(",", " ").split()
    if not tokens:
        return None
    try:
        for token in tokens:
            _parse_float(token)
    except ValueError:
        return None
    return tokens


def _selected_load_case_id(model: VerificationModel, load_case_id: int | None) -> int:
    available = {case.load_case_id for case in model.load_cases}
    if load_case_id is None:
        if len(available) != 1:
            raise ValueError(
                "STAAD ANL parsing requires load_case_id when the verification model contains "
                "more than one load case."
            )
        return next(iter(available))
    if load_case_id not in available:
        raise ValueError(f"Unknown verification load case {load_case_id}.")
    return load_case_id


def _horizontal_member_basis(
    model: VerificationModel,
    beam: VerificationBeam,
) -> tuple[float, float, float, float]:
    nodes = {node.node_id: node for node in model.nodes}
    ni = nodes[beam.node_i]
    nj = nodes[beam.node_j]
    dx = nj.x_m - ni.x_m
    dy = nj.y_m - ni.y_m
    dz = nj.z_m - ni.z_m
    if abs(dz) > 1e-9:
        raise ValueError(
            f"STAAD global-force normalization currently requires horizontal members; "
            f"member {beam.member_id} has dz={dz:.6g} m."
        )
    length_xy = math.hypot(dx, dy)
    if length_xy <= 1e-12:
        raise ValueError(f"Member {beam.member_id} has no horizontal projection.")
    ex_x = dx / length_xy
    ex_y = dy / length_xy
    ey_x = -ex_y
    ey_y = ex_x
    return ex_x, ex_y, ey_x, ey_y


def _member_semantic_components(
    model: VerificationModel,
    beam: VerificationBeam,
    *,
    fz_kn: float,
    mx_knm: float,
    my_knm: float,
) -> tuple[float, float, float]:
    """Project global STAAD end forces onto the horizontal grillage member basis.

    The member x-axis is the I-to-J horizontal direction, local z is global +Z,
    and the semantic vertical-bending axis is z cross x. This is the same beta-zero
    horizontal orientation used by the MIDAS verification profile.
    """
    ex_x, ex_y, ey_x, ey_y = _horizontal_member_basis(model, beam)
    vertical_shear = fz_kn
    vertical_bending = mx_knm * ey_x + my_knm * ey_y
    torsion = mx_knm * ex_x + my_knm * ex_y
    return vertical_shear, vertical_bending, torsion


def _write_normalized(
    rows: list[tuple[str, str, str, str, str, float, str]],
) -> str:
    identities: set[tuple[str, str, str, str, str, str]] = set()
    for result_type, object_id, span_index, position_m, component, _, unit in rows:
        identity = (result_type, object_id, span_index, position_m, component, unit)
        if identity in identities:
            raise ValueError(
                "STAAD ANL parsing produced duplicate normalized result identities. "
                "Check the selected load case and printed result blocks."
            )
        identities.add(identity)

    type_order = {"support_reaction": 0, "node_displacement": 1, "member_end_force": 2}
    component_order = {"FZ": 0, "DZ": 0, "V_VERTICAL": 0, "M_VERTICAL": 1, "T": 2}
    rows.sort(
        key=lambda row: (
            type_order.get(row[0], 99),
            int(row[1]),
            row[3],
            component_order.get(row[4], 99),
        )
    )

    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_RESULT_COLUMNS)
    for result_type, object_id, span_index, position_m, component, value, unit in rows:
        writer.writerow(
            [
                result_type,
                object_id,
                span_index,
                position_m,
                component,
                format(value, ".17g"),
                unit,
            ]
        )
    return stream.getvalue()


def parse_staad_anl_results(
    text: str,
    model: VerificationModel,
    *,
    load_case_id: int | None = None,
) -> str:
    """Parse STAAD ``.ANL`` reactions, displacements and GLOBAL member-end forces.

    The parser targets the result blocks requested by :func:`export_staad_std`:
    ``PRINT SUPPORT REACTION``, ``PRINT JOINT DISPLACEMENTS`` and
    ``PRINT MEMBER FORCES GLOBAL``. Member forces are accepted only from output
    explicitly labelled ``(GLOBAL)``. Reported units are read from the ANL headings
    and converted to the package convention of kN, m and kNm.
    """
    if not text.strip():
        raise ValueError("STAAD ANL text is empty.")
    selected_load = _selected_load_case_id(model, load_case_id)
    beams = {beam.member_id: beam for beam in model.beams}
    node_ids = {node.node_id for node in model.nodes}
    support_ids = {support.node_id for support in model.supports}

    rows: list[tuple[str, str, str, str, str, float, str]] = []
    mode: str | None = None
    in_rows = False
    displacement_to_m: float | None = None
    section_units: _UnitSystem | None = None
    member_global_confirmed = False
    current_joint: int | None = None
    current_member: int | None = None
    current_load: int | None = None

    found_displacement = False
    found_reaction = False
    found_member_force = False

    for raw_line in text.replace("\x0c", "\n").splitlines():
        line = raw_line.strip()
        upper = line.upper()

        displacement_match = _DISPLACEMENT_UNIT_RE.search(line)
        if displacement_match is not None:
            unit_token = displacement_match.group(1).upper()
            if unit_token not in _LENGTH_TO_M:
                raise ValueError(f"Unsupported STAAD displacement unit {unit_token!r}.")
            mode = "displacement"
            in_rows = False
            displacement_to_m = _LENGTH_TO_M[unit_token]
            section_units = None
            current_joint = None
            continue

        if "SUPPORT REACTIONS" in upper:
            mode = "reaction"
            in_rows = False
            section_units = _parse_unit_pair(line)
            current_joint = None
            continue

        if "MEMBER END FORCES" in upper:
            mode = "member"
            in_rows = False
            section_units = _parse_unit_pair(line)
            member_global_confirmed = "(GLOBAL)" in upper
            current_member = None
            current_load = None
            continue

        if "END OF LATEST ANALYSIS RESULT" in upper:
            mode = None
            in_rows = False
            section_units = None
            continue

        if mode in {"reaction", "member"}:
            units = _parse_unit_pair(line)
            if units is not None:
                section_units = units
                if mode == "member" and "(GLOBAL)" in upper:
                    member_global_confirmed = True
                continue

        if mode == "displacement" and all(
            token in upper for token in ("JOINT", "LOAD", "X-TRANS", "Z-TRANS")
        ):
            in_rows = True
            continue
        if mode == "reaction" and all(
            token in upper for token in ("JOINT", "LOAD", "FORCE-X", "FORCE-Z")
        ):
            in_rows = True
            continue
        if mode == "member" and all(
            token in upper for token in ("MEMBER", "LOAD", "JT", "FX", "FZ", "MX")
        ):
            in_rows = True
            continue

        if not in_rows or mode is None:
            continue
        tokens = _numeric_tokens(line)
        if tokens is None:
            continue

        if mode == "displacement":
            if displacement_to_m is None:
                raise ValueError("STAAD displacement block does not declare a length unit.")
            if len(tokens) == 8:
                current_joint = _parse_int(tokens[0])
                row_load = _parse_int(tokens[1])
                values = tokens[2:]
            elif len(tokens) == 7 and current_joint is not None:
                row_load = _parse_int(tokens[0])
                values = tokens[1:]
            else:
                continue
            if row_load != selected_load:
                continue
            if current_joint not in node_ids:
                raise ValueError(f"STAAD displacement references unknown node {current_joint}.")
            z_trans = _parse_float(values[2]) * displacement_to_m
            rows.append(
                ("node_displacement", str(current_joint), "", "", "DZ", z_trans, "m")
            )
            found_displacement = True
            continue

        if mode == "reaction":
            if section_units is None:
                raise ValueError("STAAD support-reaction block does not declare force units.")
            if len(tokens) == 8:
                current_joint = _parse_int(tokens[0])
                row_load = _parse_int(tokens[1])
                values = tokens[2:]
            elif len(tokens) == 7 and current_joint is not None:
                row_load = _parse_int(tokens[0])
                values = tokens[1:]
            else:
                continue
            if row_load != selected_load:
                continue
            if current_joint not in support_ids:
                raise ValueError(f"STAAD reaction references unknown support node {current_joint}.")
            fz_kn = _parse_float(values[2]) * section_units.force_to_kn
            rows.append(("support_reaction", str(current_joint), "", "", "FZ", fz_kn, "kN"))
            found_reaction = True
            continue

        if mode == "member":
            if not member_global_confirmed:
                raise ValueError(
                    "STAAD member-end forces must be printed in GLOBAL axes before normalization."
                )
            if section_units is None:
                raise ValueError("STAAD member-force block does not declare force/length units.")
            if len(tokens) == 9:
                current_member = _parse_int(tokens[0])
                current_load = _parse_int(tokens[1])
                joint_id = _parse_int(tokens[2])
                values = tokens[3:]
            elif len(tokens) == 8 and current_member is not None:
                current_load = _parse_int(tokens[0])
                joint_id = _parse_int(tokens[1])
                values = tokens[2:]
            elif len(tokens) == 7 and current_member is not None and current_load is not None:
                joint_id = _parse_int(tokens[0])
                values = tokens[1:]
            else:
                continue
            if current_load != selected_load:
                continue
            if current_member not in beams:
                raise ValueError(f"STAAD member force references unknown member {current_member}.")
            beam = beams[current_member]
            if joint_id == beam.node_i:
                end = "I"
            elif joint_id == beam.node_j:
                end = "J"
            else:
                raise ValueError(
                    f"STAAD member {current_member} result references joint {joint_id}, which is "
                    "not an end node of that verification member."
                )
            fz_kn = _parse_float(values[2]) * section_units.force_to_kn
            mx_knm = _parse_float(values[3]) * section_units.moment_to_knm
            my_knm = _parse_float(values[4]) * section_units.moment_to_knm
            vertical_shear, vertical_bending, torsion = _member_semantic_components(
                model,
                beam,
                fz_kn=fz_kn,
                mx_knm=mx_knm,
                my_knm=my_knm,
            )
            rows.extend(
                [
                    (
                        "member_end_force",
                        str(current_member),
                        "",
                        end,
                        "V_VERTICAL",
                        vertical_shear,
                        "kN",
                    ),
                    (
                        "member_end_force",
                        str(current_member),
                        "",
                        end,
                        "M_VERTICAL",
                        vertical_bending,
                        "kNm",
                    ),
                    (
                        "member_end_force",
                        str(current_member),
                        "",
                        end,
                        "T",
                        torsion,
                        "kNm",
                    ),
                ]
            )
            found_member_force = True

    missing_blocks = []
    if model.nodes and not found_displacement:
        missing_blocks.append("joint displacement")
    if model.supports and not found_reaction:
        missing_blocks.append("support reaction")
    if model.beams and not found_member_force:
        missing_blocks.append("global member-end force")
    if missing_blocks:
        raise ValueError(
            "STAAD ANL does not contain selected-load results for: " + ", ".join(missing_blocks)
        )
    return _write_normalized(rows)
