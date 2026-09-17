from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.common import FactoredCombination, LoadEffects


@dataclass(frozen=True)
class BS5400Factors:
    """Project-configurable BS 5400 combination factors.

    BS 5400 is retained as a legacy/comparison design mode. Defaults are not
    embedded here because the applicable combinations depend on load type,
    limit state, and the project specification. Callers must supply factors
    explicitly until each combination is implemented and independently
    verified against the relevant clauses.
    """

    gamma_permanent: float
    gamma_live: float


def factored_uls(
    permanent: LoadEffects,
    live: LoadEffects,
    factors: BS5400Factors,
    name: str = "BS 5400 ULS (project-defined factors)",
) -> FactoredCombination:
    effects = permanent.scaled(factors.gamma_permanent) + live.scaled(factors.gamma_live)
    return FactoredCombination(
        name=name,
        effects=effects,
        factors={"permanent": factors.gamma_permanent, "live": factors.gamma_live},
    )
