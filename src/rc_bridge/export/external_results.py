from __future__ import annotations

import csv
import dataclasses
import io

from rc_bridge.research.benchmarking import (
    BenchmarkComparison,
    BenchmarkTarget,
    compare_benchmark_value,
)

_RESULT_COLUMNS = (
    "result_type",
    "object_id",
    "span_index",
    "position_m",
    "component",
    "value",
    "unit",
)


@dataclasses.dataclass(frozen=True)
class VerificationResultIdentity:
    result_type: str
    object_id: str
    span_index: str
    position_m: str
    component: str
    unit: str

    @property
    def key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.result_type,
            self.object_id,
            self.span_index,
            self.position_m,
            self.component,
            self.unit,
        )


@dataclasses.dataclass(frozen=True)
class VerificationResultValue:
    result_type: str
    object_id: str
    span_index: str
    position_m: str
    component: str
    value: float
    unit: str

    @property
    def key(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.result_type,
            self.object_id,
            self.span_index,
            self.position_m,
            self.component,
            self.unit,
        )


@dataclasses.dataclass(frozen=True)
class ExternalResultCoverageReport:
    requested_count: int
    provided_count: int
    matched_count: int
    missing_keys: tuple[str, ...]
    unexpected_keys: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_keys and not self.unexpected_keys


@dataclasses.dataclass(frozen=True)
class ExternalResultComparisonReport:
    source_name: str
    comparisons: tuple[BenchmarkComparison, ...]
    missing_external_keys: tuple[str, ...]
    extra_external_keys: tuple[str, ...]

    @property
    def passes(self) -> bool:
        return (
            not self.missing_external_keys
            and not self.extra_external_keys
            and all(item.passes for item in self.comparisons)
        )

    @property
    def failed_target_names(self) -> tuple[str, ...]:
        return tuple(item.target.name for item in self.comparisons if not item.passes)


def _validate_columns(reader: csv.DictReader) -> None:
    if tuple(reader.fieldnames or ()) != _RESULT_COLUMNS:
        raise ValueError(
            "Verification result CSV must use the exact columns: " + ",".join(_RESULT_COLUMNS)
        )


def _identity_from_row(row: dict[str, str], *, row_number: int) -> VerificationResultIdentity:
    identity = VerificationResultIdentity(
        result_type=(row["result_type"] or "").strip(),
        object_id=(row["object_id"] or "").strip(),
        span_index=(row["span_index"] or "").strip(),
        position_m=(row["position_m"] or "").strip(),
        component=(row["component"] or "").strip(),
        unit=(row["unit"] or "").strip(),
    )
    if not identity.result_type or not identity.component or not identity.unit:
        raise ValueError(f"Incomplete verification result identity on row {row_number}.")
    return identity


def parse_verification_result_template_csv(
    text: str,
) -> tuple[VerificationResultIdentity, ...]:
    """Parse normalized result identities while allowing blank result values."""
    reader = csv.DictReader(io.StringIO(text))
    _validate_columns(reader)

    identities: list[VerificationResultIdentity] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        identity = _identity_from_row(row, row_number=row_number)
        if identity.key in seen:
            raise ValueError(f"Duplicate verification result key on row {row_number}.")
        seen.add(identity.key)
        identities.append(identity)
    if not identities:
        raise ValueError("Verification result template CSV is empty.")
    return tuple(identities)


def parse_verification_results_csv(text: str) -> tuple[VerificationResultValue, ...]:
    """Parse the normalized verification-result table used by the export package."""
    reader = csv.DictReader(io.StringIO(text))
    _validate_columns(reader)

    records: list[VerificationResultValue] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        try:
            value = float(row["value"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid verification result value on row {row_number}.") from exc
        identity = _identity_from_row(row, row_number=row_number)
        record = VerificationResultValue(
            result_type=identity.result_type,
            object_id=identity.object_id,
            span_index=identity.span_index,
            position_m=identity.position_m,
            component=identity.component,
            value=value,
            unit=identity.unit,
        )
        if record.key in seen:
            raise ValueError(f"Duplicate verification result key on row {row_number}.")
        seen.add(record.key)
        records.append(record)
    if not records:
        raise ValueError("Verification result CSV is empty.")
    return tuple(records)


def _display_key(key: tuple[str, str, str, str, str, str]) -> str:
    result_type, object_id, span_index, position_m, component, unit = key
    return (
        f"{result_type}|object={object_id}|span={span_index}|position={position_m}|"
        f"{component}|{unit}"
    )


def validate_external_result_coverage(
    *,
    template_csv: str,
    external_csv: str,
) -> ExternalResultCoverageReport:
    """Check that returned external results cover the requested normalized identities exactly."""
    requested = parse_verification_result_template_csv(template_csv)
    provided = parse_verification_results_csv(external_csv)
    requested_keys = {item.key for item in requested}
    provided_keys = {item.key for item in provided}
    missing = tuple(_display_key(key) for key in sorted(requested_keys - provided_keys))
    unexpected = tuple(_display_key(key) for key in sorted(provided_keys - requested_keys))
    return ExternalResultCoverageReport(
        requested_count=len(requested_keys),
        provided_count=len(provided_keys),
        matched_count=len(requested_keys & provided_keys),
        missing_keys=missing,
        unexpected_keys=unexpected,
    )


def compare_external_results_csv(
    *,
    expected_csv: str,
    external_csv: str,
    source_name: str,
    relative_tolerance: float = 0.02,
    absolute_tolerance_by_unit: dict[str, float] | None = None,
) -> ExternalResultComparisonReport:
    """Compare normalized MIDAS/STAAD results against internal expected results.

    The external table must retain the exact result identity columns emitted by
    the verification package. Default relative tolerance is 2%; optional absolute
    tolerances make near-zero reactions/moments/displacements meaningful.
    """
    if not source_name.strip():
        raise ValueError("External result source_name cannot be empty.")
    if relative_tolerance < 0.0:
        raise ValueError("relative_tolerance cannot be negative.")
    absolute_tolerances = absolute_tolerance_by_unit or {}
    if any(value < 0.0 for value in absolute_tolerances.values()):
        raise ValueError("Absolute result tolerances cannot be negative.")

    expected = parse_verification_results_csv(expected_csv)
    external = parse_verification_results_csv(external_csv)
    expected_map = {item.key: item for item in expected}
    external_map = {item.key: item for item in external}

    missing = tuple(
        _display_key(key) for key in sorted(expected_map.keys() - external_map.keys())
    )
    extra = tuple(
        _display_key(key) for key in sorted(external_map.keys() - expected_map.keys())
    )

    comparisons: list[BenchmarkComparison] = []
    for key in sorted(expected_map.keys() & external_map.keys()):
        reference = external_map[key]
        calculated = expected_map[key]
        target = BenchmarkTarget(
            name=_display_key(key),
            reference_value=reference.value,
            unit=reference.unit,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerances.get(reference.unit, 0.0),
            location=(
                f"object {reference.object_id}; span {reference.span_index}; "
                f"position {reference.position_m}"
            ),
        )
        comparisons.append(compare_benchmark_value(target, calculated_value=calculated.value))

    return ExternalResultComparisonReport(
        source_name=source_name,
        comparisons=tuple(comparisons),
        missing_external_keys=missing,
        extra_external_keys=extra,
    )
