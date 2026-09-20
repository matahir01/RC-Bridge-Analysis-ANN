from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationImportTolerance:
    """Shared numerical-tolerance policy for same-model external verification.

    The v1 defaults are evidence-based from the accepted Stage-5 STAAD benchmark:
    STAAD prints reactions/member forces to 0.01 kN or kNm and joint translations
    to 0.0001 cm (= 0.001 mm). The absolute floors therefore equal one external
    print increment. A 0.1% relative allowance governs larger responses and remains
    roughly four times the largest meaningful governing-envelope relative difference
    observed in the accepted benchmark (~0.026%).

    Relative and absolute tolerances are evaluated together. The larger allowable
    absolute error governs, which keeps near-zero quantities meaningful instead of
    treating an undefined percentage difference as an automatic pass.
    """

    relative_tolerance: float = 0.001
    absolute_force_kn: float = 0.01
    absolute_moment_knm: float = 0.01
    absolute_displacement_m: float = 1.0e-6

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
            "mm": self.absolute_displacement_m * 1000.0,
        }

    def absolute_tolerance_for_unit(self, unit: str) -> float:
        return self.absolute_tolerance_by_unit.get(unit, 0.0)

    def allowable_absolute_error(
        self,
        *,
        reference_value: float,
        unit: str,
        relative_tolerance: float | None = None,
    ) -> float:
        relative = (
            self.relative_tolerance
            if relative_tolerance is None
            else float(relative_tolerance)
        )
        if relative < 0.0:
            raise ValueError("Verification relative tolerance cannot be negative.")
        return max(
            relative * abs(float(reference_value)),
            self.absolute_tolerance_for_unit(unit),
        )

    def passes(
        self,
        *,
        reference_value: float,
        comparison_value: float,
        unit: str,
        relative_tolerance: float | None = None,
    ) -> bool:
        allowable = self.allowable_absolute_error(
            reference_value=reference_value,
            unit=unit,
            relative_tolerance=relative_tolerance,
        )
        return abs(float(comparison_value) - float(reference_value)) <= allowable + 1.0e-12
