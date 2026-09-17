from __future__ import annotations

import csv
import io
import re

from rc_bridge.export.external_results import parse_verification_results_csv
from rc_bridge.export.staad_anl import parse_staad_anl_results
from rc_bridge.export.verification_model import VerificationModel

_RESULT_COLUMNS = (
    "result_type",
    "object_id",
    "span_index",
    "position_m",
    "component",
    "value",
    "unit",
)

_DISPLACEMENT_HEADER_RE = re.compile(
    r"JOINT\s+DISPLACEMENT\s*\(\s*([A-Z]+)\s+RADIANS?\s*\)",
    re.IGNORECASE,
)


def _selected_load_case_id(model: VerificationModel, load_case_id: int | None) -> int:
    available = {case.load_case_id for case in model.load_cases}
    if load_case_id is None:
        if len(available) != 1:
            raise ValueError(
                "Line benchmark parsing requires load_case_id when the verification model "
                "contains more than one load case."
            )
        return next(iter(available))
    if load_case_id not in available:
        raise ValueError(f"Unknown verification load case {load_case_id}.")
    return load_case_id


def _parse_number(token: str) -> float:
    return float(token.strip().replace("D", "E").replace("d", "e"))


def _numeric_tokens(line: str) -> list[str] | None:
    tokens = line.replace(",", " ").split()
    if not tokens:
        return None
    try:
        for token in tokens:
            _parse_number(token)
    except ValueError:
        return None
    return tokens


def _parse_int(token: str) -> int:
    value = _parse_number(token)
    rounded = round(value)
    if abs(value - rounded) > 1.0e-9:
        raise ValueError(f"Expected integer result identifier, got {token!r}.")
    return int(rounded)


def _write_normalized(
    rows: list[tuple[str, str, str, str, str, float, str]],
) -> str:
    identities: set[tuple[str, str, str, str, str, str]] = set()
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(_RESULT_COLUMNS)
    for row in rows:
        result_type, object_id, span_index, position_m, component, value, unit = row
        key = (result_type, object_id, span_index, position_m, component, unit)
        if key in identities:
            raise ValueError(
                "Line benchmark results contain duplicate normalized identities; "
                "select a single load case/step."
            )
        identities.add(key)
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
    if not identities:
        raise ValueError("Line benchmark result set is empty.")
    return stream.getvalue()


def _staad_y_rotations(
    text: str,
    model: VerificationModel,
    *,
    load_case_id: int,
) -> list[tuple[str, str, str, str, str, float, str]]:
    node_ids = {node.node_id for node in model.nodes}
    in_displacement_block = False
    in_rows = False
    current_joint: int | None = None
    rotations: list[tuple[str, str, str, str, str, float, str]] = []

    for raw_line in text.replace("\x0c", "\n").splitlines():
        line = raw_line.strip()
        upper = line.upper()
        if _DISPLACEMENT_HEADER_RE.search(line):
            in_displacement_block = True
            in_rows = False
            current_joint = None
            continue
        if in_displacement_block and "END OF LATEST ANALYSIS RESULT" in upper:
            in_displacement_block = False
            in_rows = False
            continue
        if in_displacement_block and all(
            token in upper for token in ("JOINT", "LOAD", "X-TRANS", "Y-ROTAN")
        ):
            in_rows = True
            continue
        if not in_rows:
            continue

        tokens = _numeric_tokens(line)
        if tokens is None:
            continue
        if len(tokens) == 8:
            current_joint = _parse_int(tokens[0])
            row_load = _parse_int(tokens[1])
            values = tokens[2:]
        elif len(tokens) == 7 and current_joint is not None:
            row_load = _parse_int(tokens[0])
            values = tokens[1:]
        else:
            continue
        if row_load != load_case_id:
            continue
        if current_joint not in node_ids:
            raise ValueError(f"STAAD rotation references unknown node {current_joint}.")
        y_rotation_rad = _parse_number(values[4])
        rotations.append(
            (
                "node_rotation",
                str(current_joint),
                "",
                "",
                "RY",
                y_rotation_rad,
                "rad",
            )
        )

    if len(rotations) != len(model.nodes):
        raise ValueError(
            "STAAD line benchmark requires one selected-load Y rotation for every model node."
        )
    return rotations


def parse_staad_line_benchmark_results(
    text: str,
    model: VerificationModel,
    *,
    load_case_id: int | None = None,
) -> str:
    """Return the sign-calibrated line-benchmark subset from a STAAD ``.ANL`` file.

    Member-end forces are intentionally excluded until a real software round trip
    has calibrated their element-end sign convention. The accepted first-stage
    line benchmark uses global support FZ, global node DZ and global node RY only.
    """
    selected_load = _selected_load_case_id(model, load_case_id)
    base_csv = parse_staad_anl_results(text, model, load_case_id=selected_load)
    base_records = parse_verification_results_csv(base_csv)
    rows = [
        (
            record.result_type,
            record.object_id,
            record.span_index,
            record.position_m,
            record.component,
            record.value,
            record.unit,
        )
        for record in base_records
        if record.result_type in {"support_reaction", "node_displacement"}
    ]
    rows.extend(_staad_y_rotations(text, model, load_case_id=selected_load))
    return _write_normalized(rows)


def _read_table(text: str, *, delimiter: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("MIDAS line benchmark table has no header row.")
    rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("MIDAS line benchmark table contains no data rows.")
    return rows


def _midas_filtered_rows(
    text: str,
    *,
    required_columns: tuple[str, ...],
    load_case: str | None,
    delimiter: str,
) -> list[dict[str, str]]:
    rows = _read_table(text, delimiter=delimiter)
    available = set(rows[0])
    needed = set(required_columns)
    if load_case is not None:
        needed.add("Load")
    missing = sorted(needed - available)
    if missing:
        raise ValueError("MIDAS line benchmark table is missing columns: " + ", ".join(missing))
    if load_case is None:
        return rows
    filtered = [row for row in rows if (row.get("Load") or "").strip() == load_case]
    if not filtered:
        raise ValueError(f"MIDAS line benchmark table has no rows for load case {load_case!r}.")
    return filtered


def normalize_midas_line_benchmark_tables(
    *,
    reaction_table: str,
    displacement_table: str,
    load_case: str | None = None,
    delimiter: str = ",",
) -> str:
    """Normalize MIDAS global reaction/displacement results for the line benchmark.

    The expected table columns are ``Node, FZ`` for reactions and ``Node, DZ, RY``
    for global displacements/rotations, with an optional ``Load`` filter column.
    Member-force tables remain outside this first-stage acceptance subset.
    """
    reaction_rows = _midas_filtered_rows(
        reaction_table,
        required_columns=("Node", "FZ"),
        load_case=load_case,
        delimiter=delimiter,
    )
    displacement_rows = _midas_filtered_rows(
        displacement_table,
        required_columns=("Node", "DZ", "RY"),
        load_case=load_case,
        delimiter=delimiter,
    )

    rows: list[tuple[str, str, str, str, str, float, str]] = []
    for row in reaction_rows:
        node_id = (row.get("Node") or "").strip()
        if not node_id:
            raise ValueError("MIDAS line benchmark reaction row is missing Node.")
        rows.append(
            (
                "support_reaction",
                node_id,
                "",
                "",
                "FZ",
                _parse_number((row.get("FZ") or "").replace(",", "")),
                "kN",
            )
        )
    for row in displacement_rows:
        node_id = (row.get("Node") or "").strip()
        if not node_id:
            raise ValueError("MIDAS line benchmark displacement row is missing Node.")
        rows.extend(
            [
                (
                    "node_displacement",
                    node_id,
                    "",
                    "",
                    "DZ",
                    _parse_number((row.get("DZ") or "").replace(",", "")),
                    "m",
                ),
                (
                    "node_rotation",
                    node_id,
                    "",
                    "",
                    "RY",
                    _parse_number((row.get("RY") or "").replace(",", "")),
                    "rad",
                ),
            ]
        )
    return _write_normalized(rows)
