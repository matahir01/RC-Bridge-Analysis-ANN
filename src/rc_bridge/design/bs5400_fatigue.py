from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BS5400FatigueScopeResult:
    welded_reinforcement: bool
    requires_part10_check: bool
    status: str


@dataclass(frozen=True)
class BS5400FatigueResult:
    maximum_stress_mpa: float
    minimum_stress_mpa: float
    effective_stress_range_mpa: float
    allowable_stress_range_mpa: float
    utilization: float
    g_fatigue_mpa: float
    passes: bool
    status: str


def assess_reinforcement_fatigue_scope_bs5400(
    *,
    welded_reinforcement: bool,
) -> BS5400FatigueScopeResult:
    """Assess base BS 5400-4:1990 reinforcement fatigue scope.

    The base Part 4 fatigue clause specifically directs welded reinforcing bars
    to Part 10. Highway/rail authority amendments may impose additional checks
    on unwelded bars; those must be selected explicitly by the project profile.
    """
    if welded_reinforcement:
        return BS5400FatigueScopeResult(
            welded_reinforcement=True,
            requires_part10_check=True,
            status=(
                "Welded reinforcing bar: BS 5400 Part 10 fatigue assessment required "
                "under the base BS 5400-4 fatigue clause."
            ),
        )
    return BS5400FatigueScopeResult(
        welded_reinforcement=False,
        requires_part10_check=False,
        status=(
            "Unwelded reinforcing bar: base BS 5400-4:1990 Part 4 fatigue clause does "
            "not itself require the welded-bar Part 10 check; project/authority amendments "
            "must still be reviewed explicitly."
        ),
    )


def effective_stress_range_nonwelded_part10(
    *,
    maximum_stress_mpa: float,
    minimum_stress_mpa: float,
) -> float:
    """Return Part 10 effective stress range for a non-welded detail.

    Tension is positive and compression negative. Compression-only cycles are
    ignored. For stress reversal, the tensile part is combined with 60% of the
    compression excursion, matching the Part 10 non-welded-detail rule.
    """
    if maximum_stress_mpa < minimum_stress_mpa:
        raise ValueError("maximum_stress_mpa cannot be less than minimum_stress_mpa.")
    if maximum_stress_mpa <= 0.0:
        return 0.0
    if minimum_stress_mpa >= 0.0:
        return maximum_stress_mpa - minimum_stress_mpa
    return maximum_stress_mpa + 0.60 * abs(minimum_stress_mpa)


def part10_permissible_stress_range_mpa(
    *,
    design_cycles: float,
    sn_exponent_m: float,
    sn_constant_k2: float,
) -> float:
    """Return stress range from the generic Part 10 relation N*(sigma_r)^m = K2."""
    if min(design_cycles, sn_exponent_m, sn_constant_k2) <= 0.0:
        raise ValueError("S-N cycle count, exponent and constant must be positive.")
    return (sn_constant_k2 / design_cycles) ** (1.0 / sn_exponent_m)


def check_reinforcement_fatigue_bs5400(
    *,
    maximum_stress_mpa: float,
    minimum_stress_mpa: float,
    allowable_stress_range_mpa: float | None = None,
    design_cycles: float | None = None,
    sn_exponent_m: float | None = None,
    sn_constant_k2: float | None = None,
    nonwelded_effective_range: bool = False,
) -> BS5400FatigueResult:
    """Check a reinforcement stress range against an explicit BS 5400 fatigue basis.

    The allowable range may be supplied directly from the governing authority/
    detail classification, or derived from supplied Part 10 S-N parameters. The
    function deliberately does not choose a detail class or authority amendment.
    """
    if maximum_stress_mpa < minimum_stress_mpa:
        raise ValueError("maximum_stress_mpa cannot be less than minimum_stress_mpa.")

    sn_values = (design_cycles, sn_exponent_m, sn_constant_k2)
    sn_supplied = all(value is not None for value in sn_values)
    sn_partial = any(value is not None for value in sn_values) and not sn_supplied
    if sn_partial:
        raise ValueError("design_cycles, sn_exponent_m and sn_constant_k2 must be supplied together.")
    if allowable_stress_range_mpa is not None and allowable_stress_range_mpa <= 0.0:
        raise ValueError("allowable_stress_range_mpa must be positive when supplied.")
    if allowable_stress_range_mpa is None and not sn_supplied:
        raise ValueError(
            "Supply either allowable_stress_range_mpa or a complete Part 10 S-N parameter set."
        )
    if allowable_stress_range_mpa is not None and sn_supplied:
        raise ValueError("Supply either a direct allowable range or S-N parameters, not both.")

    if nonwelded_effective_range:
        stress_range = effective_stress_range_nonwelded_part10(
            maximum_stress_mpa=maximum_stress_mpa,
            minimum_stress_mpa=minimum_stress_mpa,
        )
    else:
        stress_range = maximum_stress_mpa - minimum_stress_mpa

    allowable = (
        allowable_stress_range_mpa
        if allowable_stress_range_mpa is not None
        else part10_permissible_stress_range_mpa(
            design_cycles=float(design_cycles),
            sn_exponent_m=float(sn_exponent_m),
            sn_constant_k2=float(sn_constant_k2),
        )
    )
    utilization = stress_range / allowable if allowable > 0.0 else float("inf")
    margin = allowable - stress_range
    return BS5400FatigueResult(
        maximum_stress_mpa=maximum_stress_mpa,
        minimum_stress_mpa=minimum_stress_mpa,
        effective_stress_range_mpa=stress_range,
        allowable_stress_range_mpa=allowable,
        utilization=utilization,
        g_fatigue_mpa=margin,
        passes=margin >= 0.0,
        status=(
            "BS 5400 fatigue stress-range check using an explicit governing detail/authority "
            "basis; no fatigue detail class or authority amendment is selected implicitly."
        ),
    )
