from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.research.verification import SolverProfile


@dataclass(frozen=True)
class BenchmarkTarget:
    name: str
    reference_value: float
    unit: str
    relative_tolerance: float | None = None
    absolute_tolerance: float | None = None
    location: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Benchmark target name cannot be empty.")
        if not self.unit.strip():
            raise ValueError("Benchmark target unit cannot be empty.")
        if self.relative_tolerance is None and self.absolute_tolerance is None:
            raise ValueError("At least one benchmark tolerance must be supplied.")
        if self.relative_tolerance is not None and self.relative_tolerance < 0.0:
            raise ValueError("Relative tolerance cannot be negative.")
        if self.absolute_tolerance is not None and self.absolute_tolerance < 0.0:
            raise ValueError("Absolute tolerance cannot be negative.")


@dataclass(frozen=True)
class BenchmarkComparison:
    target: BenchmarkTarget
    calculated_value: float
    signed_error: float
    absolute_error: float
    relative_error: float | None
    allowable_absolute_error: float
    passes: bool


@dataclass(frozen=True)
class IndependentBenchmarkReport:
    solver_profile: SolverProfile
    source_name: str
    comparisons: tuple[BenchmarkComparison, ...]
    source_reference: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise ValueError("Independent benchmark source name cannot be empty.")
        if not self.comparisons:
            raise ValueError("Independent benchmark report requires at least one comparison.")

    @property
    def passes(self) -> bool:
        return all(item.passes for item in self.comparisons)

    @property
    def failed_target_names(self) -> tuple[str, ...]:
        return tuple(item.target.name for item in self.comparisons if not item.passes)

    @property
    def maximum_relative_error(self) -> float | None:
        values = [
            item.relative_error
            for item in self.comparisons
            if item.relative_error is not None
        ]
        return max(values) if values else None


def compare_benchmark_value(
    target: BenchmarkTarget,
    *,
    calculated_value: float,
) -> BenchmarkComparison:
    """Compare one solver result against an explicit independent reference value.

    Relative tolerance is converted to an absolute allowance using the magnitude
    of the reference value. When both relative and absolute tolerances are given,
    the larger allowance governs. This makes near-zero quantities usable without
    creating meaningless relative-error failures.
    """
    signed_error = calculated_value - target.reference_value
    absolute_error = abs(signed_error)
    relative_error = None
    if target.reference_value != 0.0:
        relative_error = absolute_error / abs(target.reference_value)

    relative_allowance = 0.0
    if target.relative_tolerance is not None:
        relative_allowance = target.relative_tolerance * abs(target.reference_value)
    absolute_allowance = target.absolute_tolerance or 0.0
    allowable = max(relative_allowance, absolute_allowance)

    return BenchmarkComparison(
        target=target,
        calculated_value=calculated_value,
        signed_error=signed_error,
        absolute_error=absolute_error,
        relative_error=relative_error,
        allowable_absolute_error=allowable,
        passes=absolute_error <= allowable,
    )


def build_independent_benchmark_report(
    *,
    solver_profile: SolverProfile,
    source_name: str,
    observations: tuple[tuple[BenchmarkTarget, float], ...],
    source_reference: str = "",
    notes: str = "",
) -> IndependentBenchmarkReport:
    """Build a traceable comparison report without changing verification state.

    A passing report is evidence that may support an independent verification
    decision. It deliberately does not mutate or construct an ANN-ready
    ``DeterministicSolverVerification`` object by itself.
    """
    comparisons = tuple(
        compare_benchmark_value(target, calculated_value=calculated)
        for target, calculated in observations
    )
    return IndependentBenchmarkReport(
        solver_profile=solver_profile,
        source_name=source_name,
        comparisons=comparisons,
        source_reference=source_reference,
        notes=notes,
    )
