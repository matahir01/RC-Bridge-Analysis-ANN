from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReinforcementFatigueResult:
    reference_stress_range_mpa: float
    lambda_s: float
    phi_fat: float
    equivalent_stress_range_mpa: float
    design_fatigue_resistance_mpa: float
    utilization: float
    g_fatigue_mpa: float
    passes: bool
    status: str


@dataclass(frozen=True)
class ConcreteCompressionFatigueResult:
    sigma_c_max_mpa: float
    sigma_c_min_mpa: float
    fcd_fat_mpa: float
    demand_ratio: float
    allowable_ratio: float
    utilization: float
    g_fatigue_ratio: float
    passes: bool
    status: str


def reinforcement_fatigue_check(
    *,
    reference_stress_range_mpa: float,
    lambda_s: float,
    characteristic_fatigue_strength_mpa: float,
    gamma_s_fat: float = 1.15,
    phi_fat: float = 1.0,
) -> ReinforcementFatigueResult:
    """Check reinforcing-steel fatigue using an equivalent stress range.

    ``reference_stress_range_mpa`` is the reinforcement stress range already
    obtained from the selected fatigue load model and structural analysis. The
    bridge damage-equivalence factor ``lambda_s`` and local dynamic factor
    ``phi_fat`` remain explicit. The verification is

        lambda_s * phi_fat * delta_sigma_s,Ec <= delta_sigma_Rsk / gamma_s,fat

    The fatigue-strength value depends on reinforcement/detail category and must
    therefore be supplied explicitly rather than inferred by this kernel.
    """
    if reference_stress_range_mpa < 0.0:
        raise ValueError("reference_stress_range_mpa cannot be negative.")
    if lambda_s <= 0.0 or phi_fat <= 0.0:
        raise ValueError("lambda_s and phi_fat must be positive.")
    if characteristic_fatigue_strength_mpa <= 0.0 or gamma_s_fat <= 0.0:
        raise ValueError("Fatigue strength and gamma_s_fat must be positive.")

    equivalent = reference_stress_range_mpa * lambda_s * phi_fat
    resistance = characteristic_fatigue_strength_mpa / gamma_s_fat
    utilization = equivalent / resistance
    margin = resistance - equivalent
    return ReinforcementFatigueResult(
        reference_stress_range_mpa=reference_stress_range_mpa,
        lambda_s=lambda_s,
        phi_fat=phi_fat,
        equivalent_stress_range_mpa=equivalent,
        design_fatigue_resistance_mpa=resistance,
        utilization=utilization,
        g_fatigue_mpa=margin,
        passes=margin >= 0.0,
        status=(
            "EN 1992-2 reinforcement fatigue equivalent-stress-range check; "
            "fatigue load model, lambda factors and fatigue category must be verified"
        ),
    )


def concrete_design_fatigue_strength_mpa(
    *,
    fck_mpa: float,
    gamma_c: float = 1.50,
    alpha_cc: float = 1.0,
    k1: float = 0.85,
    beta_cc_t0: float = 1.0,
) -> float:
    """Return first-generation EN 1992-2 concrete fatigue design strength.

    Implements f_cd,fat = k1 * beta_cc(t0) * f_cd * (1 - f_ck / 250).
    National Annex and project values remain explicit.
    """
    if not 0.0 < fck_mpa < 250.0:
        raise ValueError("fck_mpa must lie between 0 and 250 MPa.")
    if min(gamma_c, alpha_cc, k1, beta_cc_t0) <= 0.0:
        raise ValueError("Concrete fatigue factors must be positive.")

    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    return k1 * beta_cc_t0 * fcd_mpa * (1.0 - fck_mpa / 250.0)


def concrete_compression_fatigue_check(
    *,
    sigma_c_max_mpa: float,
    sigma_c_min_mpa: float,
    fck_mpa: float,
    gamma_c: float = 1.50,
    alpha_cc: float = 1.0,
    k1: float = 0.85,
    beta_cc_t0: float = 1.0,
) -> ConcreteCompressionFatigueResult:
    """Check concrete compression fatigue using EN 1992-2 Expression 6.77.

    Compressive stresses are supplied as positive magnitudes and must satisfy
    sigma_c,max >= sigma_c,min >= 0.
    """
    if sigma_c_min_mpa < 0.0 or sigma_c_max_mpa < 0.0:
        raise ValueError("Concrete compressive stresses must be non-negative magnitudes.")
    if sigma_c_max_mpa < sigma_c_min_mpa:
        raise ValueError("sigma_c_max_mpa must be at least sigma_c_min_mpa.")

    fcd_fat = concrete_design_fatigue_strength_mpa(
        fck_mpa=fck_mpa,
        gamma_c=gamma_c,
        alpha_cc=alpha_cc,
        k1=k1,
        beta_cc_t0=beta_cc_t0,
    )
    demand_ratio = sigma_c_max_mpa / fcd_fat
    allowable_ratio = 0.5 + 0.45 * sigma_c_min_mpa / fcd_fat
    utilization = demand_ratio / allowable_ratio
    margin = allowable_ratio - demand_ratio
    return ConcreteCompressionFatigueResult(
        sigma_c_max_mpa=sigma_c_max_mpa,
        sigma_c_min_mpa=sigma_c_min_mpa,
        fcd_fat_mpa=fcd_fat,
        demand_ratio=demand_ratio,
        allowable_ratio=allowable_ratio,
        utilization=utilization,
        g_fatigue_ratio=margin,
        passes=margin >= 0.0,
        status=(
            "EN 1992-2 concrete compression fatigue check; beta_cc(t0), alpha_cc "
            "and National Annex values must be verified for the project"
        ),
    )
