from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    ImportedGirderEffect,
    ImportedGrillageEnvelope,
)
from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult
from rc_bridge.codes.common import LoadEffects
from rc_bridge.export.external_results import parse_verification_results_csv
from rc_bridge.export.model_verification_package import (
    ModelVerificationExportPackage,
    build_model_verification_export_package,
)
from rc_bridge.export.verification_model import VerificationBeam, VerificationModel
from rc_bridge.workflow.lm1_grillage_search import (
    LM1SearchCaseResult,
    ProjectNativeLM1GrillageSearchResult,
)


@dataclass(frozen=True)
class GrillageEnvelopeTolerance:
    """Acceptance limits for native-versus-external per-girder envelopes."""

    relative_tolerance: float = 0.02
    absolute_moment_knm: float = 0.1
    absolute_shear_kn: float = 0.1
    absolute_torsion_knm: float = 0.1

    def __post_init__(self) -> None:
        values = (
            self.relative_tolerance,
            self.absolute_moment_knm,
            self.absolute_shear_kn,
            self.absolute_torsion_knm,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("Grillage benchmark tolerances cannot be negative.")


@dataclass(frozen=True)
class GrillageEnvelopeComponentComparison:
    girder_index: int
    component: str
    native_value: float
    external_value: float
    absolute_difference: float
    relative_difference: float | None
    passes: bool


@dataclass(frozen=True)
class LM1ExternalGrillageBenchmarkReport:
    case_id: int
    source_name: str
    comparisons: tuple[GrillageEnvelopeComponentComparison, ...]

    @property
    def passes(self) -> bool:
        return bool(self.comparisons) and all(item.passes for item in self.comparisons)

    @property
    def failed_components(self) -> tuple[str, ...]:
        return tuple(
            f"girder {item.girder_index} {item.component}"
            for item in self.comparisons
            if not item.passes
        )


@dataclass(frozen=True)
class LM1GoverningBenchmarkCasePackage:
    case: LM1SearchCaseResult
    verification_package: ModelVerificationExportPackage
    native_expected_results_csv: str
    native_expected_girder_envelope_csv: str
    governing_usage_csv: str

    @property
    def case_id(self) -> int:
        return self.case.placement.case_id

    def files(self) -> dict[str, str]:
        stem = f"lm1_governing_case_{self.case_id:04d}"
        files = dict(self.verification_package.files(stem))
        files[f"{stem}_native_expected_results.csv"] = self.native_expected_results_csv
        files[f"{stem}_native_expected_girder_envelope.csv"] = (
            self.native_expected_girder_envelope_csv
        )
        files[f"{stem}_governing_usage.csv"] = self.governing_usage_csv
        return files


@dataclass(frozen=True)
class LM1GoverningBenchmarkSuite:
    cases: tuple[LM1GoverningBenchmarkCasePackage, ...]

    def __post_init__(self) -> None:
        if not self.cases:
            raise ValueError("LM1 governing benchmark suite cannot be empty.")
        case_ids = [item.case_id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("LM1 governing benchmark suite contains duplicate case IDs.")

    def files(self) -> dict[str, str]:
        files: dict[str, str] = {}
        for case in self.cases:
            case_files = case.files()
            overlap = set(files) & set(case_files)
            if overlap:
                raise RuntimeError(
                    "LM1 benchmark cases generated duplicate filenames: "
                    + ", ".join(sorted(overlap))
                )
            files.update(case_files)
        return files


def _format_float(value: float) -> str:
    return format(float(value), ".17g")


def native_grillage_results_csv(
    model: VerificationModel,
    analysis: GrillageAnalysisResult,
) -> str:
    """Serialize native grillage results using the external-result normalization schema.

    These detailed signed values are useful for result-axis calibration. Governing
    LM1 acceptance should use the magnitude envelope comparison below until the
    external software member-end sign convention has been confirmed for a project.
    """
    node_results = {item.node_id: item for item in analysis.nodes}
    member_results = {item.member_id: item for item in analysis.members}
    if set(node_results) != {item.node_id for item in model.nodes}:
        raise ValueError("Native node results do not match the verification model.")
    if set(member_results) != {item.member_id for item in model.beams}:
        raise ValueError("Native member results do not match the verification model.")

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
        node = node_results[support.node_id]
        writer.writerow(
            [
                "support_reaction",
                support.node_id,
                "",
                "",
                "FZ",
                _format_float(node.vertical_reaction_kn),
                "kN",
            ]
        )

    for node in model.nodes:
        result = node_results[node.node_id]
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
        result = member_results[beam.member_id]
        values_by_end = {
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
        for end, values in values_by_end.items():
            for component, value, unit in (
                ("V_VERTICAL", values[0], "kN"),
                ("M_VERTICAL", values[1], "kNm"),
                ("T", values[2], "kNm"),
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


def _member_plan_vector(
    model: VerificationModel,
    beam: VerificationBeam,
) -> tuple[float, float, float, float]:
    nodes = {node.node_id: node for node in model.nodes}
    ni = nodes[beam.node_i]
    nj = nodes[beam.node_j]
    return nj.x_m - ni.x_m, nj.y_m - ni.y_m, ni.y_m, nj.y_m


def _longitudinal_groups(
    model: VerificationModel,
    *,
    tolerance: float = 1.0e-9,
) -> tuple[tuple[float, tuple[VerificationBeam, ...]], ...]:
    groups: dict[float, list[VerificationBeam]] = {}
    for beam in model.beams:
        dx, dy, y_i, y_j = _member_plan_vector(model, beam)
        if abs(dy) <= tolerance and abs(dx) > tolerance:
            y = 0.5 * (y_i + y_j)
            matched = next((key for key in groups if abs(key - y) <= tolerance), None)
            key = y if matched is None else matched
            groups.setdefault(key, []).append(beam)
        elif abs(dx) <= tolerance and abs(dy) > tolerance:
            continue
        else:
            raise ValueError(
                "LM1 external envelope comparison requires an orthogonal grillage; "
                f"member {beam.member_id} is diagonal or degenerate."
            )
    if not groups:
        raise ValueError("LM1 external envelope comparison found no longitudinal girders.")
    return tuple((y, tuple(beams)) for y, beams in sorted(groups.items()))


def external_grillage_envelope_from_normalized_results(
    model: VerificationModel,
    external_results_csv: str,
    *,
    source_name: str,
) -> ImportedGrillageEnvelope:
    """Reduce normalized external member-end results to absolute M/V/T by girder."""
    if not source_name.strip():
        raise ValueError("External grillage source_name cannot be empty.")

    records = parse_verification_results_csv(external_results_csv)
    force_records = {
        (int(item.object_id), item.position_m, item.component): item.value
        for item in records
        if item.result_type == "member_end_force"
        and item.component in {"V_VERTICAL", "M_VERTICAL", "T"}
    }
    groups = _longitudinal_groups(model)
    effects: list[ImportedGirderEffect] = []

    for girder_index, (_, beams) in enumerate(groups, start=1):
        moments: list[float] = []
        shears: list[float] = []
        torsions: list[float] = []
        for beam in beams:
            for end in ("I", "J"):
                required = {
                    component: (beam.member_id, end, component)
                    for component in ("V_VERTICAL", "M_VERTICAL", "T")
                }
                missing = [
                    component
                    for component, key in required.items()
                    if key not in force_records
                ]
                if missing:
                    raise ValueError(
                        f"External member {beam.member_id} end {end} is missing components: "
                        + ", ".join(missing)
                    )
                shears.append(abs(force_records[required["V_VERTICAL"]]))
                moments.append(abs(force_records[required["M_VERTICAL"]]))
                torsions.append(abs(force_records[required["T"]]))

        effects.append(
            ImportedGirderEffect(
                girder_index=girder_index,
                effects=LoadEffects(
                    moment_knm=max(moments),
                    shear_kn=max(shears),
                    torsion_knm=max(torsions),
                ),
            )
        )

    return ImportedGrillageEnvelope(
        metadata=GrillageImportMetadata(
            source_software=source_name,
            model_name=model.name,
            load_case=model.load_cases[0].name,
            method="external_normalized_member_end_envelope",
        ),
        girder_effects=tuple(effects),
    )


def _envelope_csv(envelope: ImportedGrillageEnvelope) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["girder_index", "moment_knm", "shear_kn", "torsion_knm"])
    for item in envelope.girder_effects:
        writer.writerow(
            [
                item.girder_index,
                _format_float(item.effects.moment_knm),
                _format_float(item.effects.shear_kn),
                _format_float(item.effects.torsion_knm),
            ]
        )
    return stream.getvalue()


def _governing_usage_csv(
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    case_id: int,
) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["girder_index", "governing_component"])
    for girder in search.girders:
        if girder.moment_knm.case_id == case_id:
            writer.writerow([girder.girder_index, "M"])
        if girder.shear_kn.case_id == case_id:
            writer.writerow([girder.girder_index, "V"])
        if girder.torsion_knm.case_id == case_id:
            writer.writerow([girder.girder_index, "T"])
    return stream.getvalue()


def build_lm1_governing_benchmark_suite(
    search: ProjectNativeLM1GrillageSearchResult,
) -> LM1GoverningBenchmarkSuite:
    """Package each unique governing LM1 case for an identical MIDAS/STAAD run."""
    cases_by_id = {item.placement.case_id: item for item in search.cases}
    packages: list[LM1GoverningBenchmarkCasePackage] = []
    for case_id in search.governing_case_ids:
        case = cases_by_id[case_id]
        packages.append(
            LM1GoverningBenchmarkCasePackage(
                case=case,
                verification_package=build_model_verification_export_package(case.model),
                native_expected_results_csv=native_grillage_results_csv(
                    case.model,
                    case.analysis,
                ),
                native_expected_girder_envelope_csv=_envelope_csv(
                    case.girder_envelope.envelope
                ),
                governing_usage_csv=_governing_usage_csv(search, case_id=case_id),
            )
        )
    return LM1GoverningBenchmarkSuite(cases=tuple(packages))


def compare_lm1_external_grillage_case(
    benchmark_case: LM1GoverningBenchmarkCasePackage,
    *,
    external_results_csv: str,
    source_name: str,
    tolerance: GrillageEnvelopeTolerance | None = None,
) -> LM1ExternalGrillageBenchmarkReport:
    """Compare external normalized results with native M/V/T magnitudes per girder."""
    policy = tolerance or GrillageEnvelopeTolerance()
    native = benchmark_case.case.girder_envelope.envelope
    external = external_grillage_envelope_from_normalized_results(
        benchmark_case.case.model,
        external_results_csv,
        source_name=source_name,
    )
    if native.girder_count != external.girder_count:
        raise ValueError("Native and external grillage envelopes have different girder counts.")

    comparisons: list[GrillageEnvelopeComponentComparison] = []
    component_specs = (
        ("M", "moment_knm", policy.absolute_moment_knm),
        ("V", "shear_kn", policy.absolute_shear_kn),
        ("T", "torsion_knm", policy.absolute_torsion_knm),
    )
    for girder_index in range(1, native.girder_count + 1):
        native_effects = native.effect_for_girder(girder_index)
        external_effects = external.effect_for_girder(girder_index)
        for label, attribute, absolute_tolerance in component_specs:
            native_value = float(getattr(native_effects, attribute))
            external_value = float(getattr(external_effects, attribute))
            difference = abs(native_value - external_value)
            scale = max(abs(native_value), abs(external_value))
            relative = None if scale <= 1.0e-12 else difference / scale
            relative_pass = relative is not None and relative <= policy.relative_tolerance
            comparisons.append(
                GrillageEnvelopeComponentComparison(
                    girder_index=girder_index,
                    component=label,
                    native_value=native_value,
                    external_value=external_value,
                    absolute_difference=difference,
                    relative_difference=relative,
                    passes=difference <= absolute_tolerance or relative_pass,
                )
            )

    return LM1ExternalGrillageBenchmarkReport(
        case_id=benchmark_case.case_id,
        source_name=source_name,
        comparisons=tuple(comparisons),
    )
