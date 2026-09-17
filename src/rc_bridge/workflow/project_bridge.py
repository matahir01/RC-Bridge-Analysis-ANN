from __future__ import annotations

from rc_bridge.analysis.lane_distribution import (
    equal_lane_distribution,
    equal_remaining_area_distribution,
)
from rc_bridge.analysis.loads import deck_self_weight_per_girder_kn_m
from rc_bridge.codes.eurocode.en1991_2 import notional_lane_layout
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.eurocode_bridge_traffic import (
    BridgeLM1TrafficResult,
    run_simple_span_lm1_bridge_traffic,
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
