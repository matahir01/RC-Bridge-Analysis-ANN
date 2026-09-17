from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.common import FactoredCombination, LoadEffects


@dataclass(frozen=True)
class EurocodeFactors:
    """Configurable factors for the initial bridge ULS implementation.

    Defaults represent a common STR/GEO persistent-design starting point and
    MUST be checked against the applicable National Annex and project basis.
    They are deliberately exposed so that no National Annex value is buried
    inside the solver.
    """

    gamma_g_unfavourable: float = 1.35
    gamma_q_traffic: float = 1.50


@dataclass(frozen=True)
class ServiceabilityPsiFactors:
    """Representative-value factors for a single leading traffic action.

    The values are deliberately required from the caller because bridge traffic
    psi factors are National-Annex/project parameters. This initial object
    covers one leading traffic action; accompanying variable actions will be
    added when thermal, wind, construction, and other bridge actions are wired.
    """

    psi1_traffic: float
    psi2_traffic: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.psi1_traffic <= 1.0:
            raise ValueError("psi1_traffic must lie between 0 and 1.")
        if not 0.0 <= self.psi2_traffic <= 1.0:
            raise ValueError("psi2_traffic must lie between 0 and 1.")


def persistent_uls(
    permanent: LoadEffects,
    traffic: LoadEffects,
    factors: EurocodeFactors | None = None,
) -> FactoredCombination:
    f = factors or EurocodeFactors()
    effects = permanent.scaled(f.gamma_g_unfavourable) + traffic.scaled(f.gamma_q_traffic)
    return FactoredCombination(
        name="EN 1990 persistent ULS (configurable)",
        effects=effects,
        factors={"G": f.gamma_g_unfavourable, "Q_traffic": f.gamma_q_traffic},
    )


def characteristic_sls(
    permanent: LoadEffects,
    traffic: LoadEffects,
) -> FactoredCombination:
    """EN 1990 characteristic SLS combination for one leading traffic action."""
    return FactoredCombination(
        name="EN 1990 characteristic SLS",
        effects=permanent + traffic,
        factors={"G": 1.0, "Q_traffic": 1.0},
    )


def frequent_sls(
    permanent: LoadEffects,
    traffic: LoadEffects,
    factors: ServiceabilityPsiFactors,
) -> FactoredCombination:
    """EN 1990 frequent SLS combination for one leading traffic action."""
    return FactoredCombination(
        name="EN 1990 frequent SLS",
        effects=permanent + traffic.scaled(factors.psi1_traffic),
        factors={"G": 1.0, "Q_traffic": factors.psi1_traffic},
    )


def quasi_permanent_sls(
    permanent: LoadEffects,
    traffic: LoadEffects,
    factors: ServiceabilityPsiFactors,
) -> FactoredCombination:
    """EN 1990 quasi-permanent SLS combination for long-term effects."""
    return FactoredCombination(
        name="EN 1990 quasi-permanent SLS",
        effects=permanent + traffic.scaled(factors.psi2_traffic),
        factors={"G": 1.0, "Q_traffic": factors.psi2_traffic},
    )
