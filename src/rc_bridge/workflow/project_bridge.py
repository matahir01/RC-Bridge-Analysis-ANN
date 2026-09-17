from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import (
    equal_lane_distribution,
    equal_remaining_area_distribution,
)
from rc_bridge.analysis.loads import deck_self_weight_per_girder_kn_m
from rc_bridge.analysis.simple_span import udl_simple_span
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.eurocode_bridge_traffic import (
    BridgeLM1TrafficResult,
    run_simple_span_lm1_bridge_traffic,
)
from rc_bridge.workflow.eurocode_girder import EurocodeMaterialInput


@dataclass(frozen=True)
class UniformPermanentLoadInput:
    """Explicit additional characteristic permanent line loads on one girder."""

    girder_self_weight_kn_m: float = 0.0
    surfacing_and_finishes_kn_m: float = 0.0
    assigned_barrier_and_services_kn_m: float = 0.0
    other_kn_m: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.girder_self_weight_kn_m,
            self.surfacing_and_finishes_kn_m,
            self.assigned_barrier_and_services_kn_m,
            self.other_kn_m,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("Permanent line-load components cannot be negative.")

    @property
    def total_additional_kn_m(self) -> float:
        return (
            self.girder_self_weight_kn_m
            + self.surfacing_and_finishes_kn_m
            + self.assigned_barrier_and_services_kn_m
            + self.other_kn_m
        )


def project_eurocode_material_input(
    project: ProjectInput,
    *,
    fct_eff_mpa: float | None = None,
    es_mpa: float = 200000.0,
) -> EurocodeMaterialInput:
    """Build the girder-workflow material input from project properties.

    Ecm and the default fct,eff are derived from first-generation EC2 concrete
    properties. Supply ``fct_eff_mpa`` explicitly for early-age cracking or any
    other stage where the effective tensile strength differs from 28-day fctm.
    A project elastic-modulus override takes precedence over the EC2 estimate.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Eurocode material derivation requires a Eurocode project.")
    if fct_eff_mpa is not None and fct_eff_mpa <= 0.0:
        raise ValueError("fct_eff_mpa must be positive when supplied.")
    if es_mpa <= 0.0:
        raise ValueError("es_mpa must be positive.")

    fck_mpa = float(project.materials.fck_mpa)
    properties = concrete_properties_ec2(fck_mpa)
    ecm_mpa = (
        float(project.materials.elastic_modulus_mpa)
        if project.materials.elastic_modulus_mpa is not None
        else properties.ecm_mpa
    )
    return EurocodeMaterialInput(
        fck_mpa=fck_mpa,
        fyk_mpa=float(project.materials.fyk_mpa),
        ecm_mpa=ecm_mpa,
        fct_eff_mpa=fct_eff_mpa or properties.fctm_mpa,
        es_mpa=es_mpa,
    )


def internal_girder_deck_self_weight_kn_m(project: ProjectInput) -> float:
    """Physical deck self-weight on an internal girder tributary width.

    This includes both precast false slab and in-situ slab because both are
    permanent weight, regardless of whether the false slab participates in the
    composite compression flange.
    """
    geometry = project.geometry
    return deck_self_weight_per_girder_kn_m(
        deck_thickness_m=geometry.physical_deck_depth_m,
        girder_spacing_m=float(geometry.girder_spacing_m),
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def internal_girder_characteristic_permanent_effects(
    project: ProjectInput,
    *,
    span_index: int = 0,
    additional: UniformPermanentLoadInput | None = None,
) -> LoadEffects:
    """Return simple-span characteristic G effects for an internal girder.

    Deck self-weight is derived from the physical deck build-up. Girder own
    weight, surfacing, barriers/services, and other permanent loads are explicit
    inputs until the corresponding section/load models are defined. Edge-girder
    deck tributary width must be handled separately.
    """
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This permanent-load adapter currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    deck_kn_m = internal_girder_deck_self_weight_kn_m(project)
    extra_kn_m = (additional or UniformPermanentLoadInput()).total_additional_kn_m
    result = udl_simple_span(span_m, deck_kn_m + extra_kn_m)
    return LoadEffects(
        moment_knm=result.max_moment_knm,
        shear_kn=result.max_shear_kn,
    )


def run_project_lm1_equal_share_verification(
    project: ProjectInput,
    *,
    span_index: int = 0,
    movement_steps: int = 81,
    section_stations: int = 101,
) -> BridgeLM1TrafficResult:
    """Run the current simple-span LM1 benchmark with equal transverse shares.

    This is intentionally labelled verification-only. It checks longitudinal
    LM1 mechanics, bridge geometry plumbing, and conservation of total traffic
    effects. It is not the production transverse-distribution solution; that
    must use validated analytical factors or imported grillage results.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("This verification workflow currently supports Eurocode projects only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This verification workflow currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    carriageway_width_m = float(project.geometry.carriageway_width_m)
    girder_count = int(project.geometry.girder_count)
    layout = notional_lane_layout(carriageway_width_m)

    lane_distributions = [
        equal_lane_distribution(lane_number, girder_count)
        for lane_number in range(1, layout.lane_count + 1)
    ]
    remaining_distribution = (
        equal_remaining_area_distribution(girder_count)
        if layout.remaining_width_m > 0.0
        else None
    )

    return run_simple_span_lm1_bridge_traffic(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        lane_distributions=lane_distributions,
        remaining_area_distribution=remaining_distribution,
        movement_steps=movement_steps,
        section_stations=section_stations,
    )
