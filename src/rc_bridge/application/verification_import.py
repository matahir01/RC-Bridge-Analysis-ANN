from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult
from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
)
from rc_bridge.export.external_results import (
    ExternalResultComparisonReport,
    ExternalResultCoverageReport,
    compare_external_results_csv,
    validate_external_result_coverage,
)
from rc_bridge.export.midas_mct import midas_result_name_map
from rc_bridge.export.model_verification_package import (
    build_model_verification_export_package,
)
from rc_bridge.export.staad_anl import parse_staad_anl_results
from rc_bridge.export.table_mapping import (
    midas_civil_horizontal_grillage_profile,
    normalize_external_result_tables,
)
from rc_bridge.export.verification_model import (
    VerificationLoadCase,
    VerificationLoadCombination,
    VerificationModel,
    VerificationNodalLoad,
    VerificationPointLoad,
    VerificationUniformLoad,
)


@dataclass(frozen=True)
class VerificationImportTolerance:
    relative_tolerance: float = 0.02
    absolute_force_kn: float = 0.10
    absolute_moment_knm: float = 0.10
    absolute_displacement_m: float = 1.0e-5

    def __post_init__(self) -> None:
        if self.relative_tolerance < 0.0:
            raise ValueError("Verification relative tolerance cannot be negative.")
        if min(
            self.absolute_force_kn,
            self.absolute_moment_knm,
            self.absolute_displacement_m,
        ) < 0.0:
            raise ValueError("Verification absolute tolerances cannot be negative.")

    @property
    def absolute_tolerance_by_unit(self) -> dict[str, float]:
        return {
            "kN": self.absolute_force_kn,
            "kNm": self.absolute_moment_knm,
            "m": self.absolute_displacement_m,
        }


@dataclass(frozen=True)
class ImportedVerificationResultSet:
    result_id: int
    result_name: str
    result_kind: str
    source_name: str
    expected_results_csv: str
    external_results_csv: str
    coverage: ExternalResultCoverageReport
    comparison: ExternalResultComparisonReport

    @property
    def passes(self) -> bool:
        return self.coverage.complete and self.comparison.passes

    @property
    def failed_count(self) -> int:
        return sum(not item.passes for item in self.comparison.comparisons)

    @property
    def maximum_relative_error(self) -> float | None:
        values = [
            item.relative_error
            for item in self.comparison.comparisons
            if item.relative_error is not None
        ]
        return max(values) if values else None


@dataclass(frozen=True)
class ApplicationVerificationImportReport:
    source_name: str
    model_name: str
    requested_result_ids: tuple[int, ...]
    result_sets: tuple[ImportedVerificationResultSet, ...]
    missing_result_ids: tuple[int, ...]

    @property
    def imported_result_ids(self) -> tuple[int, ...]:
        return tuple(item.result_id for item in self.result_sets)

    @property
    def passes(self) -> bool:
        return (
            bool(self.result_sets)
            and not self.missing_result_ids
            and all(item.passes for item in self.result_sets)
        )

    @property
    def failed_result_ids(self) -> tuple[int, ...]:
        return tuple(item.result_id for item in self.result_sets if not item.passes)

    @property
    def maximum_relative_error(self) -> float | None:
        values = [
            value
            for item in self.result_sets
            if (value := item.maximum_relative_error) is not None
        ]
        return max(values) if values else None


@dataclass(frozen=True)
class WrittenVerificationImportEvidence:
    directory: Path
    summary_json: Path
    comparisons_csv: Path
    normalized_result_files: tuple[Path, ...]
    expected_result_files: tuple[Path, ...]


def _scale_uniform_load(
    load: VerificationUniformLoad,
    factor: float,
) -> VerificationUniformLoad:
    return replace(load, magnitude_kn_m=load.magnitude_kn_m * factor)


def _scale_point_load(
    load: VerificationPointLoad,
    factor: float,
) -> VerificationPointLoad:
    return replace(load, magnitude_kn=load.magnitude_kn * factor)


def _scale_nodal_load(
    load: VerificationNodalLoad,
    factor: float,
) -> VerificationNodalLoad:
    return VerificationNodalLoad(
        node_id=load.node_id,
        fx_kn=load.fx_kn * factor,
        fy_kn=load.fy_kn * factor,
        fz_kn=load.fz_kn * factor,
        mx_knm=load.mx_knm * factor,
        my_knm=load.my_knm * factor,
        mz_knm=load.mz_knm * factor,
    )


def combined_load_case(
    model: VerificationModel,
    combination: VerificationLoadCombination,
) -> VerificationLoadCase:
    """Convert one linear external load combination to one native solver load case."""

    by_id = {case.load_case_id: case for case in model.load_cases}
    uniform: list[VerificationUniformLoad] = []
    point: list[VerificationPointLoad] = []
    nodal: list[VerificationNodalLoad] = []
    self_weight = 0.0
    for term in combination.terms:
        case = by_id[term.load_case_id]
        factor = float(term.factor)
        self_weight += case.self_weight_gz_factor * factor
        uniform.extend(_scale_uniform_load(load, factor) for load in case.uniform_loads)
        point.extend(_scale_point_load(load, factor) for load in case.point_loads)
        nodal.extend(_scale_nodal_load(load, factor) for load in case.nodal_loads)

    return VerificationLoadCase(
        load_case_id=combination.combination_id,
        name=combination.name,
        self_weight_gz_factor=self_weight,
        uniform_loads=tuple(uniform),
        point_loads=tuple(point),
        nodal_loads=tuple(nodal),
    )


def verification_result_case(
    model: VerificationModel,
    result_id: int,
) -> tuple[str, VerificationLoadCase]:
    load_case = next(
        (item for item in model.load_cases if item.load_case_id == result_id),
        None,
    )
    if load_case is not None:
        return "load_case", load_case
    combination = next(
        (
            item
            for item in model.load_combinations
            if item.combination_id == result_id
        ),
        None,
    )
    if combination is None:
        raise ValueError(f"Unknown verification result ID {result_id}.")
    return "combination", combined_load_case(model, combination)


def verification_result_ids(model: VerificationModel) -> tuple[int, ...]:
    return tuple(
        [case.load_case_id for case in model.load_cases]
        + [combination.combination_id for combination in model.load_combinations]
    )


def _single_result_model(
    model: VerificationModel,
    *,
    result_id: int,
) -> tuple[str, VerificationModel]:
    kind, case = verification_result_case(model, result_id)
    result_model = replace(
        model,
        name=f"{model.name} - result {result_id} {case.name}",
        load_cases=(case,),
        load_combinations=(),
    )
    result_model.validate_load_positions()
    return kind, result_model


def _format_float(value: float) -> str:
    return format(float(value), ".17g")


def normalized_native_grillage_results_csv(
    model: VerificationModel,
    analysis: GrillageAnalysisResult,
) -> str:
    """Serialize native grillage results in the same normalized schema as imports."""

    nodes = {item.node_id: item for item in analysis.nodes}
    members = {item.member_id: item for item in analysis.members}
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

    for support in model.supports:
        result = nodes[support.node_id]
        writer.writerow(
            [
                "support_reaction",
                support.node_id,
                "",
                "",
                "FZ",
                _format_float(result.vertical_reaction_kn),
                "kN",
            ]
        )

    for node in model.nodes:
        result = nodes[node.node_id]
        writer.writerow(
            [
                "node_displacement",
                node.node_id,
                "",
                "",
                "DZ",
                _format_float(result.vertical_displacement_m),
                "m",
            ]
        )

    for beam in model.beams:
        result = members[beam.member_id]
        values = {
            "I": (
                result.i_vertical_force_kn,
                result.i_vertical_bending_moment_knm,
                result.i_torsion_knm,
            ),
            "J": (
                result.j_vertical_force_kn,
                result.j_vertical_bending_moment_knm,
                result.j_torsion_knm,
            ),
        }
        for end, (shear, moment, torsion) in values.items():
            for component, value, unit in (
                ("V_VERTICAL", shear, "kN"),
                ("M_VERTICAL", moment, "kNm"),
                ("T", torsion, "kNm"),
            ):
                writer.writerow(
                    [
                        "member_end_force",
                        beam.member_id,
                        "",
                        end,
                        component,
                        _format_float(value),
                        unit,
                    ]
                )
    return stream.getvalue()


def native_expected_results_by_id(
    model: VerificationModel,
    result_ids: tuple[int, ...],
) -> dict[int, tuple[str, VerificationModel, str]]:
    if not result_ids:
        raise ValueError("At least one verification result ID is required.")

    single_models = {
        result_id: _single_result_model(model, result_id)
        for result_id in result_ids
    }
    first_id = result_ids[0]
    _, first_model = single_models[first_id]
    prepared = prepare_vertical_grillage(first_model)

    results: dict[int, tuple[str, VerificationModel, str]] = {}
    for result_id in result_ids:
        kind, result_model = single_models[result_id]
        analysis = solve_prepared_vertical_grillage(prepared, result_model)
        results[result_id] = (
            kind,
            result_model,
            normalized_native_grillage_results_csv(result_model, analysis),
        )
    return results


def _assemble_result_set(
    *,
    result_id: int,
    result_kind: str,
    result_model: VerificationModel,
    expected_csv: str,
    external_csv: str,
    source_name: str,
    tolerance: VerificationImportTolerance,
) -> ImportedVerificationResultSet:
    template = build_model_verification_export_package(
        result_model
    ).external_results_template_csv
    coverage = validate_external_result_coverage(
        template_csv=template,
        external_csv=external_csv,
    )
    comparison = compare_external_results_csv(
        expected_csv=expected_csv,
        external_csv=external_csv,
        source_name=source_name,
        relative_tolerance=tolerance.relative_tolerance,
        absolute_tolerance_by_unit=tolerance.absolute_tolerance_by_unit,
    )
    return ImportedVerificationResultSet(
        result_id=result_id,
        result_name=result_model.load_cases[0].name,
        result_kind=result_kind,
        source_name=source_name,
        expected_results_csv=expected_csv,
        external_results_csv=external_csv,
        coverage=coverage,
        comparison=comparison,
    )


def import_staad_anl_verification_results(
    model: VerificationModel,
    *,
    staad_anl_text: str,
    result_ids: tuple[int, ...] | None = None,
    source_name: str = "STAAD.Pro",
    tolerance: VerificationImportTolerance | None = None,
) -> ApplicationVerificationImportReport:
    """Import all requested STAAD load-case/combination results from one ANL file."""

    if not source_name.strip():
        raise ValueError("STAAD verification source name cannot be empty.")
    requested = result_ids or verification_result_ids(model)
    if len(requested) != len(set(requested)):
        raise ValueError("Verification result IDs cannot contain duplicates.")
    expected = native_expected_results_by_id(model, requested)
    policy = tolerance or VerificationImportTolerance()

    imported: list[ImportedVerificationResultSet] = []
    missing: list[int] = []
    for result_id in requested:
        kind, result_model, expected_csv = expected[result_id]
        try:
            external_csv = parse_staad_anl_results(
                staad_anl_text,
                model,
                load_case_id=result_id,
            )
        except ValueError as exc:
            if "does not contain selected-load results" in str(exc):
                missing.append(result_id)
                continue
            raise
        imported.append(
            _assemble_result_set(
                result_id=result_id,
                result_kind=kind,
                result_model=result_model,
                expected_csv=expected_csv,
                external_csv=external_csv,
                source_name=source_name,
                tolerance=policy,
            )
        )

    if not imported:
        raise ValueError(
            "The STAAD ANL file contains none of the requested Stage-5 result IDs."
        )
    return ApplicationVerificationImportReport(
        source_name=source_name,
        model_name=model.name,
        requested_result_ids=requested,
        result_sets=tuple(imported),
        missing_result_ids=tuple(missing),
    )


def import_midas_table_verification_results(
    model: VerificationModel,
    *,
    reaction_table: str,
    displacement_table: str,
    member_force_table: str,
    result_ids: tuple[int, ...] | None = None,
    source_name: str = "MIDAS Civil",
    delimiter: str = ",",
    tolerance: VerificationImportTolerance | None = None,
) -> ApplicationVerificationImportReport:
    """Import MIDAS reaction/displacement/member-force tables for Stage-5 results."""

    if not source_name.strip():
        raise ValueError("MIDAS verification source name cannot be empty.")
    requested = result_ids or verification_result_ids(model)
    if len(requested) != len(set(requested)):
        raise ValueError("Verification result IDs cannot contain duplicates.")
    expected = _expected_results_by_id(model, requested)
    policy = tolerance or VerificationImportTolerance()
    name_map = midas_result_name_map(model)

    imported: list[ImportedVerificationResultSet] = []
    missing: list[int] = []
    for result_id in requested:
        kind, result_model, expected_csv = expected[result_id]
        key = ("case", result_id) if kind == "load_case" else ("combination", result_id)
        load_name = name_map[key]
        profile = midas_civil_horizontal_grillage_profile(
            result_model,
            load_case=load_name,
            delimiter=delimiter,
        )
        try:
            external_csv = normalize_external_result_tables(
                profile,
                reaction_table=reaction_table,
                displacement_table=displacement_table,
                member_force_table=member_force_table,
            )
        except ValueError as exc:
            if "No external rows matched" in str(exc):
                missing.append(result_id)
                continue
            raise
        imported.append(
            _assemble_result_set(
                result_id=result_id,
                result_kind=kind,
                result_model=result_model,
                expected_csv=expected_csv,
                external_csv=external_csv,
                source_name=source_name,
                tolerance=policy,
            )
        )

    if not imported:
        raise ValueError(
            "The MIDAS result tables contain none of the requested Stage-5 load names."
        )
    return ApplicationVerificationImportReport(
        source_name=source_name,
        model_name=model.name,
        requested_result_ids=requested,
        result_sets=tuple(imported),
        missing_result_ids=tuple(missing),
    )


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return stem or "verification_import"


def write_verification_import_evidence(
    report: ApplicationVerificationImportReport,
    directory: str | Path,
    *,
    base_name: str = "verification_import",
) -> WrittenVerificationImportEvidence:
    """Persist imported evidence, native expectations and detailed comparisons."""

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(base_name)

    normalized_files: list[Path] = []
    expected_files: list[Path] = []
    for item in report.result_sets:
        item_stem = f"{stem}_{item.result_id:05d}_{_safe_stem(item.result_name)}"
        external_path = root / f"{item_stem}_external_normalized.csv"
        expected_path = root / f"{item_stem}_native_expected.csv"
        external_path.write_text(item.external_results_csv, encoding="utf-8")
        expected_path.write_text(item.expected_results_csv, encoding="utf-8")
        normalized_files.append(external_path)
        expected_files.append(expected_path)

    comparison_stream = io.StringIO()
    writer = csv.writer(comparison_stream, lineterminator="\n")
    writer.writerow(
        [
            "result_id",
            "result_name",
            "result_kind",
            "result_key",
            "native_value",
            "external_value",
            "unit",
            "signed_error_native_minus_external",
            "absolute_error",
            "relative_error",
            "allowable_absolute_error",
            "passes",
        ]
    )
    for item in report.result_sets:
        for comparison in item.comparison.comparisons:
            writer.writerow(
                [
                    item.result_id,
                    item.result_name,
                    item.result_kind,
                    comparison.target.name,
                    _format_float(comparison.calculated_value),
                    _format_float(comparison.target.reference_value),
                    comparison.target.unit,
                    _format_float(comparison.signed_error),
                    _format_float(comparison.absolute_error),
                    ""
                    if comparison.relative_error is None
                    else _format_float(comparison.relative_error),
                    _format_float(comparison.allowable_absolute_error),
                    "PASS" if comparison.passes else "FAIL",
                ]
            )
    comparisons_path = root / f"{stem}_comparisons.csv"
    comparisons_path.write_text(comparison_stream.getvalue(), encoding="utf-8")

    summary = {
        "schema_version": 1,
        "source_name": report.source_name,
        "model_name": report.model_name,
        "passes": report.passes,
        "requested_result_ids": list(report.requested_result_ids),
        "imported_result_ids": list(report.imported_result_ids),
        "missing_result_ids": list(report.missing_result_ids),
        "failed_result_ids": list(report.failed_result_ids),
        "maximum_relative_error": report.maximum_relative_error,
        "result_sets": [
            {
                "result_id": item.result_id,
                "result_name": item.result_name,
                "result_kind": item.result_kind,
                "passes": item.passes,
                "requested_count": item.coverage.requested_count,
                "matched_count": item.coverage.matched_count,
                "missing_keys": list(item.coverage.missing_keys),
                "unexpected_keys": list(item.coverage.unexpected_keys),
                "failed_target_names": list(item.comparison.failed_target_names),
                "maximum_relative_error": item.maximum_relative_error,
            }
            for item in report.result_sets
        ],
        "verification_boundary": (
            "A numerical PASS confirms the imported external results match the native "
            "vertical-grillage model within the configured tolerances. Engineering "
            "acceptance still requires confirmation that the externally run file was "
            "the exported model and that software/version/model assumptions are equivalent."
        ),
    }
    summary_path = root / f"{stem}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return WrittenVerificationImportEvidence(
        directory=root,
        summary_json=summary_path,
        comparisons_csv=comparisons_path,
        normalized_result_files=tuple(normalized_files),
        expected_result_files=tuple(expected_files),
    )
