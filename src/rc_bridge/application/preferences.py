from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from rc_bridge.application.design_checks import ApplicationDesignSettings
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
)
from rc_bridge.workflow.project_bridge import SLSCombinationChoice


class UnitDisplay(str, Enum):
    """Length display convention used by the desktop application.

    The deterministic engine always stores SI metres/kN/MPa.  This setting only
    controls how editable lengths are presented to the user.
    """

    SI_METRES = "si_metres"
    DRAWING_MILLIMETRES = "drawing_millimetres"

    @property
    def length_label(self) -> str:
        return "m" if self is UnitDisplay.SI_METRES else "mm"

    def from_metres(self, value_m: float) -> float:
        return float(value_m) if self is UnitDisplay.SI_METRES else float(value_m) * 1000.0

    def to_metres(self, value: float) -> float:
        return float(value) if self is UnitDisplay.SI_METRES else float(value) / 1000.0


@dataclass(frozen=True)
class EurocodeApplicationBasis:
    """User-visible project design-basis values.

    These are application inputs, not hidden code constants.  They are persisted
    with the project document and can later be passed into benchmark-gated design
    workflows after independent verification is complete.
    """

    gamma_g_unfavourable: float = 1.35
    gamma_g_favourable: float = 1.00
    gamma_q_traffic: float = 1.50
    psi1_traffic: float = 0.75
    psi2_traffic: float = 0.0
    crack_limit_mm: float = 0.30
    deflection_limit_span_ratio: float = 1000.0

    def __post_init__(self) -> None:
        EurocodeFactors(
            gamma_g_unfavourable=self.gamma_g_unfavourable,
            gamma_g_favourable=self.gamma_g_favourable,
            gamma_q_traffic=self.gamma_q_traffic,
        )
        ServiceabilityPsiFactors(
            psi1_traffic=self.psi1_traffic,
            psi2_traffic=self.psi2_traffic,
        )
        if self.crack_limit_mm <= 0.0:
            raise ValueError("crack_limit_mm must be positive.")
        if self.deflection_limit_span_ratio <= 0.0:
            raise ValueError("deflection_limit_span_ratio must be positive.")

    @property
    def uls_factors(self) -> EurocodeFactors:
        return EurocodeFactors(
            gamma_g_unfavourable=self.gamma_g_unfavourable,
            gamma_g_favourable=self.gamma_g_favourable,
            gamma_q_traffic=self.gamma_q_traffic,
        )

    @property
    def sls_factors(self) -> ServiceabilityPsiFactors:
        return ServiceabilityPsiFactors(
            psi1_traffic=self.psi1_traffic,
            psi2_traffic=self.psi2_traffic,
        )


@dataclass(frozen=True)
class AnalysisApplicationSettings:
    grid_spacing_m: float = 1.0
    traffic_step_m: float = 0.5
    max_exhaustive_tandem_combinations: int = 5000

    def __post_init__(self) -> None:
        if self.grid_spacing_m <= 0.0:
            raise ValueError("grid_spacing_m must be positive.")
        if self.traffic_step_m <= 0.0:
            raise ValueError("traffic_step_m must be positive.")
        if self.max_exhaustive_tandem_combinations <= 0:
            raise ValueError("max_exhaustive_tandem_combinations must be positive.")


@dataclass(frozen=True)
class ApplicationPreferences:
    units: UnitDisplay = UnitDisplay.SI_METRES
    eurocode: EurocodeApplicationBasis = EurocodeApplicationBasis()
    analysis: AnalysisApplicationSettings = AnalysisApplicationSettings()
    design: ApplicationDesignSettings = field(default_factory=ApplicationDesignSettings)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["units"] = self.units.value
        data["design"]["crack_combination"] = self.design.crack_combination.value
        data["design"]["deflection_combination"] = (
            self.design.deflection_combination.value
        )
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> ApplicationPreferences:
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise TypeError("application_preferences must be a JSON object.")
        units = UnitDisplay(payload.get("units", UnitDisplay.SI_METRES.value))
        eurocode_payload = payload.get("eurocode", {})
        analysis_payload = payload.get("analysis", {})
        design_payload = payload.get("design", {})
        if not isinstance(eurocode_payload, dict):
            raise TypeError("application_preferences.eurocode must be an object.")
        if not isinstance(analysis_payload, dict):
            raise TypeError("application_preferences.analysis must be an object.")
        if not isinstance(design_payload, dict):
            raise TypeError("application_preferences.design must be an object.")
        design_data = dict(design_payload)
        design_data["crack_combination"] = SLSCombinationChoice(
            design_data.get(
                "crack_combination",
                SLSCombinationChoice.FREQUENT.value,
            )
        )
        design_data["deflection_combination"] = SLSCombinationChoice(
            design_data.get(
                "deflection_combination",
                SLSCombinationChoice.FREQUENT.value,
            )
        )
        return cls(
            units=units,
            eurocode=EurocodeApplicationBasis(**eurocode_payload),
            analysis=AnalysisApplicationSettings(**analysis_payload),
            design=ApplicationDesignSettings(**design_data),
        )
