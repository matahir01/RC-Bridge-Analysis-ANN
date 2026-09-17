from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
    gamma_g_favourable: float = 1.00

    def __post_init__(self) -> None:
        if self.gamma_g_unfavourable <= 0.0:
            raise ValueError("gamma_g_unfavourable must be positive.")
        if self.gamma_g_favourable < 0.0:
            raise ValueError("gamma_g_favourable cannot be negative.")
        if self.gamma_q_traffic <= 0.0:
            raise ValueError("gamma_q_traffic must be positive.")


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


@dataclass(frozen=True)
class SignedSectionEnvelope:
    """Positive/negative characteristic extrema for one scalar section response."""

    maximum_positive_effect: float
    minimum_negative_effect: float
    response_kind: Literal["moment", "shear"]

    def __post_init__(self) -> None:
        if self.maximum_positive_effect < 0.0:
            raise ValueError("maximum_positive_effect cannot be negative.")
        if self.minimum_negative_effect > 0.0:
            raise ValueError("minimum_negative_effect cannot be positive.")


@dataclass(frozen=True)
class SignedSectionCombinationSet:
    """Directional ULS/SLS combinations retaining positive and negative branches."""

    response_kind: Literal["moment", "shear"]
    permanent_characteristic_effect: float
    traffic_characteristic: SignedSectionEnvelope
    positive_uls_effect: float
    negative_uls_effect: float
    positive_characteristic_sls_effect: float
    negative_characteristic_sls_effect: float
    positive_frequent_sls_effect: float
    negative_frequent_sls_effect: float
    positive_quasi_permanent_sls_effect: float
    negative_quasi_permanent_sls_effect: float
    positive_gamma_g: float
    negative_gamma_g: float
    gamma_q_traffic: float
    psi1_traffic: float
    psi2_traffic: float


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


def _directional_gamma_g(
    permanent_effect: float,
    *,
    direction: Literal["positive", "negative"],
    factors: EurocodeFactors,
) -> float:
    """Choose favourable/unfavourable G factor for the requested response extreme."""
    if permanent_effect == 0.0:
        return factors.gamma_g_unfavourable
    permanent_drives_extreme = (direction == "positive" and permanent_effect > 0.0) or (
        direction == "negative" and permanent_effect < 0.0
    )
    return (
        factors.gamma_g_unfavourable
        if permanent_drives_extreme
        else factors.gamma_g_favourable
    )


def signed_section_combinations(
    *,
    permanent_characteristic_effect: float,
    traffic_characteristic: SignedSectionEnvelope,
    sls_factors: ServiceabilityPsiFactors,
    uls_factors: EurocodeFactors | None = None,
) -> SignedSectionCombinationSet:
    """Combine signed characteristic section effects for continuous bridge regions.

    The positive and negative traffic extrema are separate load arrangements.
    Permanent action is factored as favourable or unfavourable independently for
    each ULS direction. SLS branches retain signed effects and apply the supplied
    traffic representative-value factors without taking absolute values.
    """
    f = uls_factors or EurocodeFactors()
    positive_gamma_g = _directional_gamma_g(
        permanent_characteristic_effect,
        direction="positive",
        factors=f,
    )
    negative_gamma_g = _directional_gamma_g(
        permanent_characteristic_effect,
        direction="negative",
        factors=f,
    )
    q_positive = traffic_characteristic.maximum_positive_effect
    q_negative = traffic_characteristic.minimum_negative_effect

    return SignedSectionCombinationSet(
        response_kind=traffic_characteristic.response_kind,
        permanent_characteristic_effect=permanent_characteristic_effect,
        traffic_characteristic=traffic_characteristic,
        positive_uls_effect=(
            positive_gamma_g * permanent_characteristic_effect
            + f.gamma_q_traffic * q_positive
        ),
        negative_uls_effect=(
            negative_gamma_g * permanent_characteristic_effect
            + f.gamma_q_traffic * q_negative
        ),
        positive_characteristic_sls_effect=permanent_characteristic_effect + q_positive,
        negative_characteristic_sls_effect=permanent_characteristic_effect + q_negative,
        positive_frequent_sls_effect=(
            permanent_characteristic_effect + sls_factors.psi1_traffic * q_positive
        ),
        negative_frequent_sls_effect=(
            permanent_characteristic_effect + sls_factors.psi1_traffic * q_negative
        ),
        positive_quasi_permanent_sls_effect=(
            permanent_characteristic_effect + sls_factors.psi2_traffic * q_positive
        ),
        negative_quasi_permanent_sls_effect=(
            permanent_characteristic_effect + sls_factors.psi2_traffic * q_negative
        ),
        positive_gamma_g=positive_gamma_g,
        negative_gamma_g=negative_gamma_g,
        gamma_q_traffic=f.gamma_q_traffic,
        psi1_traffic=sls_factors.psi1_traffic,
        psi2_traffic=sls_factors.psi2_traffic,
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
