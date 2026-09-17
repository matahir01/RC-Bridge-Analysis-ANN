from __future__ import annotations

from rc_bridge.export.staad_anl import parse_staad_anl_results
from rc_bridge.export.table_mapping import (
    ExternalTableMappingProfile,
    midas_civil_horizontal_member_force_mapping,
    normalize_external_result_tables,
)
from rc_bridge.research.lm1_grillage_benchmark import (
    GrillageEnvelopeTolerance,
    LM1ExternalGrillageBenchmarkReport,
    LM1GoverningBenchmarkCasePackage,
    compare_lm1_external_grillage_case,
)


def compare_lm1_staad_anl_case(
    benchmark_case: LM1GoverningBenchmarkCasePackage,
    *,
    staad_anl_text: str,
    tolerance: GrillageEnvelopeTolerance | None = None,
    source_name: str = "STAAD.Pro",
) -> LM1ExternalGrillageBenchmarkReport:
    """Parse a STAAD ANL file and compare its girder M/V/T envelope to the native case."""
    normalized = parse_staad_anl_results(
        staad_anl_text,
        benchmark_case.case.model,
    )
    return compare_lm1_external_grillage_case(
        benchmark_case,
        external_results_csv=normalized,
        source_name=source_name,
        tolerance=tolerance,
    )


def compare_lm1_midas_member_force_table_case(
    benchmark_case: LM1GoverningBenchmarkCasePackage,
    *,
    member_force_table: str,
    tolerance: GrillageEnvelopeTolerance | None = None,
    source_name: str = "MIDAS Civil",
    load_case: str | None = None,
    delimiter: str = ",",
    vertical_shear_column: str = "Shear-z",
    vertical_bending_column: str = "Moment-y",
    torsion_column: str = "Torsion",
) -> LM1ExternalGrillageBenchmarkReport:
    """Normalize a MIDAS beam-force table and compare per-girder M/V/T magnitudes."""
    model = benchmark_case.case.model
    selected_load_case = load_case or model.load_cases[0].name
    member_mapping = midas_civil_horizontal_member_force_mapping(
        model,
        load_case=selected_load_case,
        vertical_shear_column=vertical_shear_column,
        vertical_bending_column=vertical_bending_column,
        torsion_column=torsion_column,
    )
    profile = ExternalTableMappingProfile(
        name="MIDAS Civil LM1 member-force benchmark",
        member_force=member_mapping,
        delimiter=delimiter,
    )
    normalized = normalize_external_result_tables(
        profile,
        member_force_table=member_force_table,
    )
    return compare_lm1_external_grillage_case(
        benchmark_case,
        external_results_csv=normalized,
        source_name=source_name,
        tolerance=tolerance,
    )
