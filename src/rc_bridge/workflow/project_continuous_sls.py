from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rc_bridge.design.eurocode_cracking import CrackWidthResult
from rc_bridge.design.eurocode_hogging_cracking import crack_width_ec2_hogging_section
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeResult,
    ContinuousDesignEnvelopeStation,
)

SLSCombinationKind = Literal["characteristic", "frequent", "quasi_permanent"]


@dataclass(frozen=True)
class HoggingCrackSectionInput:
    bottom_flange_width_m: float
    bottom_flange_thickness_m: float
    web_width_m: float
    total_depth_m: float
    top_tension_flange_width_m: float
    top_tension_flange_thickness_m: float
    top_steel_area_mm2: float
    steel_depth_from_bottom_m: float
    bar_diameter_mm: float
    bar_spacing_mm: float
    cover_mm: float


@dataclass(frozen=True)
class HoggingCrackMaterialInput:
    es_mpa: float
    ecm_mpa: float
    fct_eff_mpa: float


@dataclass(frozen=True)
class ContinuousHoggingCrackResult:
    combination_kind: SLSCombinationKind
    service_moment_knm: float
    signed_service_moment_knm: float
    governing_station: ContinuousDesignEnvelopeStation
    cracking_moment_knm: float
    crack: CrackWidthResult
    status: str


def _negative_sls_effect(
    station: ContinuousDesignEnvelopeStation,
    combination_kind: SLSCombinationKind,
) -> float:
    combinations = station.moment_combinations
    if combination_kind == "characteristic":
        return combinations.negative_characteristic_sls_effect
    if combination_kind == "frequent":
        return combinations.negative_frequent_sls_effect
    if combination_kind == "quasi_permanent":
        return combinations.negative_quasi_permanent_sls_effect
    raise ValueError(
        "combination_kind must be 'characteristic', 'frequent', or 'quasi_permanent'."
    )


def run_continuous_hogging_crack_check(
    envelope: ContinuousDesignEnvelopeResult,
    *,
    section: HoggingCrackSectionInput,
    materials: HoggingCrackMaterialInput,
    cracking_moment_knm: float,
    crack_limit_mm: float,
    combination_kind: SLSCombinationKind = "frequent",
    kt: float = 0.4,
) -> ContinuousHoggingCrackResult:
    """Check EC2 crack width at the SLS-governing negative-moment bridge section.

    The SLS governing station is selected independently of the ULS envelope.
    ``cracking_moment_knm`` is explicit because construction sequence, composite
    participation, restraint and tensile-strength history affect the uncracked
    support section and must not be inferred silently.
    """
    if not envelope.stations:
        raise ValueError("Continuous design envelope contains no stations.")
    if cracking_moment_knm <= 0.0:
        raise ValueError("Cracking moment must be positive.")
    if crack_limit_mm <= 0.0:
        raise ValueError("Crack limit must be positive.")

    negative_effects = tuple(
        _negative_sls_effect(station, combination_kind) for station in envelope.stations
    )
    station_index = min(range(len(envelope.stations)), key=lambda index: negative_effects[index])
    signed_service_moment = negative_effects[station_index]
    service_moment = max(0.0, -signed_service_moment)
    governing_station = envelope.stations[station_index]

    crack = crack_width_ec2_hogging_section(
        bottom_flange_width_m=section.bottom_flange_width_m,
        bottom_flange_thickness_m=section.bottom_flange_thickness_m,
        web_width_m=section.web_width_m,
        total_depth_m=section.total_depth_m,
        top_tension_flange_width_m=section.top_tension_flange_width_m,
        top_tension_flange_thickness_m=section.top_tension_flange_thickness_m,
        steel_area_mm2=section.top_steel_area_mm2,
        steel_depth_from_bottom_m=section.steel_depth_from_bottom_m,
        bar_diameter_mm=section.bar_diameter_mm,
        bar_spacing_mm=section.bar_spacing_mm,
        cover_mm=section.cover_mm,
        service_moment_knm=service_moment,
        cracking_moment_knm=cracking_moment_knm,
        es_mpa=materials.es_mpa,
        ecm_mpa=materials.ecm_mpa,
        fct_eff_mpa=materials.fct_eff_mpa,
        crack_limit_mm=crack_limit_mm,
        kt=kt,
    )
    return ContinuousHoggingCrackResult(
        combination_kind=combination_kind,
        service_moment_knm=service_moment,
        signed_service_moment_knm=signed_service_moment,
        governing_station=governing_station,
        cracking_moment_knm=cracking_moment_knm,
        crack=crack,
        status=(
            "Continuous Eurocode hogging crack check at the independently scanned SLS-governing "
            "negative-moment station; support-section cracking moment remains explicit"
        ),
    )
