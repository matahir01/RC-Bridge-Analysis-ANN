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
