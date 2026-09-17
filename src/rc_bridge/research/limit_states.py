def flexural_limit_state(moment_resistance_knm: float, moment_effect_knm: float) -> float:
    """g_M(X) = M_R(X) - M_E(X). Positive values indicate reserve capacity."""
    return moment_resistance_knm - moment_effect_knm


def shear_limit_state(shear_resistance_kn: float, shear_effect_kn: float) -> float:
    """g_V(X) = V_R(X) - V_E(X). Positive values indicate reserve capacity."""
    return shear_resistance_kn - shear_effect_kn


def deflection_limit_state(allowable_mm: float, calculated_mm: float) -> float:
    """Serviceability reserve. Positive values satisfy the selected deflection criterion."""
    return allowable_mm - calculated_mm
