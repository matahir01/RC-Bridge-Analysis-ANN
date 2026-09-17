from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.girder_effects import GirderEffect
from rc_bridge.analysis.grillage_import import ImportedGrillageEnvelope
from rc_bridge.research.benchmarking import (
    BenchmarkTarget,
    IndependentBenchmarkReport,
    build_independent_benchmark_report,
)
from rc_bridge.research.verification import SolverProfile


@dataclass(frozen=True)
class GrillageBenchmarkTolerances:
    moment_relative_tolerance: float | None = None
    moment_absolute_tolerance_knm: float | None = None
    shear_relative_tolerance: float | None = None
    shear_absolute_tolerance_kn: float | None = None

    def __post_init__(self) -> None:
        moment_supplied = (
            self.moment_relative_tolerance is not None
            or self.moment_absolute_tolerance_knm is not None
        )
        shear_supplied = (
            self.shear_relative_tolerance is not None
            or self.shear_absolute_tolerance_kn is not None
        )
        if not moment_supplied or not shear_supplied:
            raise ValueError("Moment and shear benchmark tolerances are both required.")
        for value in (
            self.moment_relative_tolerance,
            self.moment_absolute_tolerance_knm,
            self.shear_relative_tolerance,
            self.shear_absolute_tolerance_kn,
        ):
            if value is not None and value < 0.0:
                raise ValueError("Grillage benchmark tolerances cannot be negative.")


def benchmark_girder_effects_against_grillage(
    calculated_effects: tuple[GirderEffect, ...] | list[GirderEffect],
    imported: ImportedGrillageEnvelope,
    *,
    solver_profile: SolverProfile,
    tolerances: GrillageBenchmarkTolerances,
) -> IndependentBenchmarkReport:
    """Compare internal per-girder moment/shear magnitudes with imported grillage results.

    The imported grillage file is treated as an external reference, not as an
    automatic verification approval. A passing report may support the separate
    deterministic verification decision after the model/load-case equivalence has
    been reviewed by the engineer.
    """
    if not calculated_effects:
        raise ValueError("Calculated girder effects are required.")
    if len(calculated_effects) != imported.girder_count:
        raise ValueError(
            "Calculated and imported grillage girder counts must match: "
            f"{len(calculated_effects)} != {imported.girder_count}."
        )

    calculated_by_index = {item.girder_index: item for item in calculated_effects}
    if len(calculated_by_index) != len(calculated_effects):
        raise ValueError("Calculated girder effects contain duplicate girder indices.")
    expected_indices = set(range(1, imported.girder_count + 1))
    if set(calculated_by_index) != expected_indices:
        raise ValueError("Calculated girder indices must match the imported complete girder set.")

    observations: list[tuple[BenchmarkTarget, float]] = []
    methods: set[str] = set()
    for imported_effect in imported.girder_effects:
        girder_index = imported_effect.girder_index
        calculated = calculated_by_index[girder_index]
        methods.add(calculated.method)
        observations.extend(
            (
                (
                    BenchmarkTarget(
                        name=f"girder {girder_index} moment",
                        reference_value=imported_effect.effects.moment_knm,
                        unit="kN m",
                        relative_tolerance=tolerances.moment_relative_tolerance,
                        absolute_tolerance=tolerances.moment_absolute_tolerance_knm,
                        location=f"girder {girder_index}",
                    ),
                    calculated.moment_knm,
                ),
                (
                    BenchmarkTarget(
                        name=f"girder {girder_index} shear",
                        reference_value=imported_effect.effects.shear_kn,
                        unit="kN",
                        relative_tolerance=tolerances.shear_relative_tolerance,
                        absolute_tolerance=tolerances.shear_absolute_tolerance_kn,
                        location=f"girder {girder_index}",
                    ),
                    calculated.shear_kn,
                ),
            )
        )

    metadata = imported.metadata
    method_text = ", ".join(sorted(methods))
    return build_independent_benchmark_report(
        solver_profile=solver_profile,
        source_name=f"{metadata.source_software} grillage model",
        source_reference=f"{metadata.model_name} / {metadata.load_case}",
        observations=tuple(observations),
        notes=(
            "Per-girder moment/shear envelope comparison. Internal distribution method(s): "
            f"{method_text}. Imported method: {metadata.method}."
        ),
    )
