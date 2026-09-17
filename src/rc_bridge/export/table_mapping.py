from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field

from rc_bridge.export.verification_model import VerificationModel


@dataclass(frozen=True)
class TableFilter:
    """Optional exact-value filters applied before an external row is normalized."""

    values_by_column: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReactionTableMapping:
    node_column: str
    vertical_reaction_column: str
    unit: str = "kN"
    scale_to_output_unit: float = 1.0
    row_filter: TableFilter = field(default_factory=TableFilter)


@dataclass(frozen=True)
class DisplacementTableMapping:
    node_column: str
    vertical_displacement_column: str
    unit: str = "m"
    scale_to_output_unit: float = 1.0
    row_filter: TableFilter = field(default_factory=TableFilter)


@dataclass(frozen=True)
class MemberForceTableMapping:
    member_column: str
    end_column: str
    vertical_shear_column: str
    vertical_bending_column: str
    torsion_column: str
    end_aliases: dict[str, str] = field(default_factory=lambda: {"I": "I", "J": "J"})
    shear_unit: str = "kN"
    moment_unit: str = "kNm"
    scale_force_to_output_unit: float = 1.0
    scale_moment_to_output_unit: float = 1.0
    local_axis_mapping_verified: bool = False
    row_filter: TableFilter = field(default_factory=TableFilter)

    def __post_init__(self) -> None:
        if not self.local_axis_mapping_verified:
            raise ValueError(
                "Member-force mapping requires local_axis_mapping_verified=True after confirming "
                "which external force/moment columns represent the bridge vertical plane."
            )
        normalized = set(self.end_aliases.values())
        if normalized != {"I", "J"}:
            raise ValueError("Member-force end_aliases must map external labels onto I and J ends.")


@dataclass(frozen=True)
class ExternalTableMappingProfile:
    name: str
    reaction: ReactionTableMapping | None = None
    displacement: DisplacementTableMapping | None = None
    member_force: MemberForceTableMapping | None = None
    delimiter: str = ","

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("External table mapping profile name cannot be empty.")
        if len(self.delimiter) != 1:
            raise ValueError("External table delimiter must be exactly one character.")
        if self.reaction is None and self.displacement is None and self.member_force is None:
            raise ValueError("External table mapping profile must define at least one result table.")


def _read_rows(text: str, *, delimiter: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("External result table has no header row.")
    rows = [dict(row) for row in reader]
    if not rows:
        raise ValueError("External result table contains no data rows.")
    return rows


def _require_columns(rows: list[dict[str, str]], columns: tuple[str, ...]) -> None:
    available = set(rows[0])
    missing = [column for column in columns if column not in available]
    if missing:
        raise ValueError("External result table is missing columns: " + ", ".join(missing))


def _matches_filter(row: dict[str, str], row_filter: TableFilter) -> bool:
    return all(
        (row.get(column) or "").strip() == value
        for column, value in row_filter.values_by_column.items()
    )


def _parse_float(row: dict[str, str], column: str, *, context: str) -> float:
    raw = (row.get(column) or "").strip().replace(",", "")
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid numeric value in {context} column {column!r}: {raw!r}."
        ) from exc


def _parse_object_id(row: dict[str, str], column: str, *, context: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"Missing {context} identifier in column {column!r}.")
    return value


def _normalize_member_end_label(raw: str, mapping: MemberForceTableMapping) -> str:
    value = raw.strip()
    if value in mapping.end_aliases:
        return mapping.end_aliases[value]

    # MIDAS result tables/API may decorate an end as I[1] or J[2].  Strip only
    # that documented bracketed output-location suffix; do not guess arbitrary labels.
    bracket_match = None
    if value.startswith("I[") and value.endswith("]"):
        bracket_match = "I"
    elif value.startswith("J[") and value.endswith("]"):
        bracket_match = "J"
    if bracket_match is not None and bracket_match in mapping.end_aliases:
        return mapping.end_aliases[bracket_match]

    raise ValueError(f"Unknown external member-end label {value!r}; update end_aliases.")


def _write_normalized(rows: list[tuple[str, str, str, str, str, float, str]]) -> str:
    identities: set[tuple[str, str, str, str, str, str]] = set()
    for result_type, object_id, span_index, position_m, component, _, unit in rows:
        identity = (result_type, object_id, span_index, position_m, component, unit)
        if identity in identities:
            raise ValueError(
                "External tables produce duplicate normalized result identities. "
                "Apply a load-case/step filter or refine the source mapping."
            )
        identities.add(identity)

    stream = io.StringIO()
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


def normalize_external_result_tables(
    profile: ExternalTableMappingProfile,
    *,
    reaction_table: str | None = None,
    displacement_table: str | None = None,
    member_force_table: str | None = None,
) -> str:
    """Convert software-exported tables into the normalized verification-result schema.

    The function is deliberately table-format agnostic. The profile supplies exact
    source column names and optional row filters. Member force conversion is blocked
    unless the local-axis mapping has been explicitly verified by the caller.
    """
    normalized: list[tuple[str, str, str, str, str, float, str]] = []

    if profile.reaction is not None:
        if reaction_table is None:
            raise ValueError("Reaction table text is required by this mapping profile.")
        mapping = profile.reaction
        rows = _read_rows(reaction_table, delimiter=profile.delimiter)
        _require_columns(
            rows,
            (
                mapping.node_column,
                mapping.vertical_reaction_column,
                *mapping.row_filter.values_by_column,
            ),
        )
        for row in rows:
            if not _matches_filter(row, mapping.row_filter):
                continue
            node_id = _parse_object_id(row, mapping.node_column, context="node")
            value = _parse_float(
                row,
                mapping.vertical_reaction_column,
                context="reaction",
            )
            normalized.append(
                (
                    "support_reaction",
                    node_id,
                    "",
                    "",
                    "FZ",
                    value * mapping.scale_to_output_unit,
                    mapping.unit,
                )
            )

    if profile.displacement is not None:
        if displacement_table is None:
            raise ValueError("Displacement table text is required by this mapping profile.")
        mapping = profile.displacement
        rows = _read_rows(displacement_table, delimiter=profile.delimiter)
        _require_columns(
            rows,
            (
                mapping.node_column,
                mapping.vertical_displacement_column,
                *mapping.row_filter.values_by_column,
            ),
        )
        for row in rows:
            if not _matches_filter(row, mapping.row_filter):
                continue
            node_id = _parse_object_id(row, mapping.node_column, context="node")
            value = _parse_float(
                row,
                mapping.vertical_displacement_column,
                context="displacement",
            )
            normalized.append(
                (
                    "node_displacement",
                    node_id,
                    "",
                    "",
                    "DZ",
                    value * mapping.scale_to_output_unit,
                    mapping.unit,
                )
            )

    if profile.member_force is not None:
        if member_force_table is None:
            raise ValueError("Member-force table text is required by this mapping profile.")
        mapping = profile.member_force
        rows = _read_rows(member_force_table, delimiter=profile.delimiter)
        _require_columns(
            rows,
            (
                mapping.member_column,
                mapping.end_column,
                mapping.vertical_shear_column,
                mapping.vertical_bending_column,
                mapping.torsion_column,
                *mapping.row_filter.values_by_column,
            ),
        )
        for row in rows:
            if not _matches_filter(row, mapping.row_filter):
                continue
            member_id = _parse_object_id(row, mapping.member_column, context="member")
            external_end = (row.get(mapping.end_column) or "").strip()
            end = _normalize_member_end_label(external_end, mapping)
            shear = _parse_float(row, mapping.vertical_shear_column, context="member shear")
            bending = _parse_float(
                row,
                mapping.vertical_bending_column,
                context="member bending",
            )
            torsion = _parse_float(row, mapping.torsion_column, context="member torsion")
            normalized.extend(
                (
                    (
                        "member_end_force",
                        member_id,
                        "",
                        end,
                        "V_VERTICAL",
                        shear * mapping.scale_force_to_output_unit,
                        mapping.shear_unit,
                    ),
                    (
                        "member_end_force",
                        member_id,
                        "",
                        end,
                        "M_VERTICAL",
                        bending * mapping.scale_moment_to_output_unit,
                        mapping.moment_unit,
                    ),
                    (
                        "member_end_force",
                        member_id,
                        "",
                        end,
                        "T",
                        torsion * mapping.scale_moment_to_output_unit,
                        mapping.moment_unit,
                    ),
                )
            )

    if not normalized:
        raise ValueError("No external rows matched the configured table mappings and filters.")
    return _write_normalized(normalized)


def midas_civil_global_reaction_mapping(
    *,
    load_case: str | None = None,
) -> ReactionTableMapping:
    """MIDAS Civil reaction-table mapping documented for Node/Load/FZ columns."""
    row_filter = TableFilter({"Load": load_case}) if load_case is not None else TableFilter()
    return ReactionTableMapping(
        node_column="Node",
        vertical_reaction_column="FZ",
        row_filter=row_filter,
    )


def midas_civil_global_displacement_mapping(
    *,
    load_case: str | None = None,
) -> DisplacementTableMapping:
    """MIDAS Civil displacement mapping documented for Node/Load/DZ columns."""
    row_filter = TableFilter({"Load": load_case}) if load_case is not None else TableFilter()
    return DisplacementTableMapping(
        node_column="Node",
        vertical_displacement_column="DZ",
        row_filter=row_filter,
    )


def midas_civil_global_profile(
    *,
    load_case: str | None = None,
    delimiter: str = ",",
) -> ExternalTableMappingProfile:
    """Safe built-in MIDAS profile for global reaction and displacement tables only."""
    return ExternalTableMappingProfile(
        name="MIDAS Civil global reaction/displacement tables",
        reaction=midas_civil_global_reaction_mapping(load_case=load_case),
        displacement=midas_civil_global_displacement_mapping(load_case=load_case),
        delimiter=delimiter,
    )


def _validate_midas_beta_zero_horizontal_model(model: VerificationModel) -> None:
    nodes = {node.node_id: node for node in model.nodes}
    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if abs(nj.z_m - ni.z_m) > 1e-9:
            raise ValueError(
                "Verified MIDAS grillage force mapping requires every beam to be horizontal."
            )
        if math.hypot(nj.x_m - ni.x_m, nj.y_m - ni.y_m) <= 1e-12:
            raise ValueError("Verified MIDAS grillage force mapping found a zero-length plan member.")
        if abs(beam.beta_angle_deg) > 1e-9:
            raise ValueError(
                "Verified MIDAS grillage force mapping requires beta_angle_deg=0 for every beam."
            )


def midas_civil_horizontal_member_force_mapping(
    model: VerificationModel,
    *,
    load_case: str | None = None,
    vertical_shear_column: str = "Shear-z",
    vertical_bending_column: str = "Moment-y",
    torsion_column: str = "Torsion",
) -> MemberForceTableMapping:
    """Verified MIDAS beam-force mapping for horizontal beta-zero grillage members.

    MIDAS defines the beam ECS x-axis from N1 to N2. For horizontal elements at
    beta zero, ECS z follows global vertical Z and ECS y is the horizontal bending
    axis. Therefore Shear-z, Moment-y and Torsion map directly to the package's
    vertical shear, vertical-plane bending and member torsion semantics.
    """
    _validate_midas_beta_zero_horizontal_model(model)
    row_filter = TableFilter({"Load": load_case}) if load_case is not None else TableFilter()
    return MemberForceTableMapping(
        member_column="Elem",
        end_column="Part",
        vertical_shear_column=vertical_shear_column,
        vertical_bending_column=vertical_bending_column,
        torsion_column=torsion_column,
        end_aliases={"I": "I", "J": "J", "PartI": "I", "PartJ": "J"},
        local_axis_mapping_verified=True,
        row_filter=row_filter,
    )


def midas_civil_horizontal_grillage_profile(
    model: VerificationModel,
    *,
    load_case: str | None = None,
    delimiter: str = ",",
    vertical_shear_column: str = "Shear-z",
    vertical_bending_column: str = "Moment-y",
    torsion_column: str = "Torsion",
) -> ExternalTableMappingProfile:
    """Full MIDAS profile for the exported horizontal beta-zero verification grillage."""
    return ExternalTableMappingProfile(
        name="MIDAS Civil horizontal beta-zero grillage results",
        reaction=midas_civil_global_reaction_mapping(load_case=load_case),
        displacement=midas_civil_global_displacement_mapping(load_case=load_case),
        member_force=midas_civil_horizontal_member_force_mapping(
            model,
            load_case=load_case,
            vertical_shear_column=vertical_shear_column,
            vertical_bending_column=vertical_bending_column,
            torsion_column=torsion_column,
        ),
        delimiter=delimiter,
    )
