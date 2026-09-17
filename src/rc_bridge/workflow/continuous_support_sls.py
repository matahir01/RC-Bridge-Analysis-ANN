from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from rc_bridge.codes.eurocode.combinations import SignedSectionCombinationSet
from rc_bridge.design.eurocode_cracking import CrackWidthResult
from rc_bridge.design.eurocode_layered_cracking import (
    HorizontalSectionLayer,
    crack_width_ec2_layered_section,
)

ServiceCombinationKind = Literal["characteristic", "frequent", "quasi_permanent"]


@dataclass(frozen=True)
class ContinuousSupportCrackInput:
    layers_from_compression_face: tuple[HorizontalSectionLayer, ...]
    total_depth_m: float
    top_tension_steel_area_mm2: float
    steel_depth_from_compression_face_m: float
    bar_diameter_mm: float
    bar_spacing_mm: float
    cover_mm: float
    es_mpa: float
    ecm_mpa: float
    fct_eff_mpa: float
    crack_limit_mm: float
    kt: float = 0.4

    def __post_init__(self) -> None:
        if not self.layers_from_compression_face:
            raise ValueError("Support cracking input requires concrete section layers.")
        positive = (
            self.total_depth_m,
            self.top_tension_steel_area_mm2,
            self.steel_depth_from_compression_face_m,
            self.bar_diameter_mm,
            self.bar_spacing_mm,
            self.cover_mm,
            self.es_mpa,
            self.ecm_mpa,
            self.fct_eff_mpa,
            self.crack_limit_mm,
        )
        if any(value <= 0.0 for value in positive):
            raise ValueError("Support crack-control geometry, reinforcement and material inputs must be positive.")
        if self.steel_depth_from_compression_face_m >= self.total_depth_m:
            raise ValueError("Top tension steel depth must lie inside the support section.")
        if not 0.0 < self.kt <= 1.0:
            raise ValueError("kt must lie between zero and one.")


@dataclass(frozen=True)
class ContinuousSupportCrackCheck:
    service_combination: ServiceCombinationKind
    signed_service_moment_knm: float
    service_moment_magnitude_knm: float
    crack: CrackWidthResult
    status: str


def _negative_service_effect(
    combinations: SignedSectionCombinationSet,
    service_combination: ServiceCombinationKind,
) -> float:
    if service_combination == "characteristic":
        return combinations.negative_characteristic_sls_effect
    if service_combination == "frequent":
        return combinations.negative_frequent_sls_effect
    if service_combination == "quasi_permanent":
        return combinations.negative_quasi_permanent_sls_effect
    raise ValueError(
        "service_combination must be 'characteristic', 'frequent', or 'quasi_permanent'."
    )


def check_continuous_support_cracking(
    combinations: SignedSectionCombinationSet,
    input_data: ContinuousSupportCrackInput,
    *,
    service_combination: ServiceCombinationKind,
) -> ContinuousSupportCrackCheck:
    """Check crack width for the negative-bending support region of a continuous girder.

    Section layers are defined from the actual compression face for hogging
    bending (normally the bottom face). This allows a bottom flange, web and deck
    tension zone to be represented without crediting the deck as a compression
    flange. The SLS combination is explicit rather than hard-coded.
    """
    if combinations.response_kind != "moment":
        raise ValueError("Support crack-width design requires moment combinations.")

    signed_moment = _negative_service_effect(combinations, service_combination)
    if signed_moment >= 0.0:
        raise ValueError(
            "The selected negative SLS branch is not hogging; no support top-face crack check applies."
        )
    magnitude = abs(signed_moment)
    crack = crack_width_ec2_layered_section(
        layers=input_data.layers_from_compression_face,
        total_depth_m=input_data.total_depth_m,
        steel_area_mm2=input_data.top_tension_steel_area_mm2,
        steel_depth_from_compression_face_m=input_data.steel_depth_from_compression_face_m,
        bar_diameter_mm=input_data.bar_diameter_mm,
        bar_spacing_mm=input_data.bar_spacing_mm,
        cover_mm=input_data.cover_mm,
        service_moment_knm=magnitude,
        es_mpa=input_data.es_mpa,
        ecm_mpa=input_data.ecm_mpa,
        fct_eff_mpa=input_data.fct_eff_mpa,
        crack_limit_mm=input_data.crack_limit_mm,
        kt=input_data.kt,
    )
    return ContinuousSupportCrackCheck(
        service_combination=service_combination,
        signed_service_moment_knm=signed_moment,
        service_moment_magnitude_knm=magnitude,
        crack=crack,
        status=(
            "Continuous support negative-bending crack width checked using explicit layered section "
            "geometry and caller-selected EN 1990 service combination"
        ),
    )
