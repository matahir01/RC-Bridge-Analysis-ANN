from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import equal_lane_distribution
from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.codes.bs5400.traffic import notional_lane_layout_bd37_01
from rc_bridge.codes.common import LoadEffects
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.workflow.bs5400_bridge_traffic import (
    BS5400HABridgeTrafficResult,
    run_simple_span_ha_bridge_traffic_bd37_01,
)
from rc_bridge.workflow.bs5400_girder import (
    BS5400TGirderInput,
    BS5400TGirderResult,
    run_bs5400_t_girder_case,
)
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    internal_girder_characteristic_permanent_effects,
)


@dataclass(frozen=True)
class ProjectBS5400TGirderVerificationResult:
    traffic: BS5400HABridgeTrafficResult
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    design: BS5400TGirderResult
    traffic_distribution_method: str
    status: str


def run_project_ha_equal_share_verification(
    project: ProjectInput,
    *,
    span_index: int = 0,
) -> BS5400HABridgeTrafficResult:
    """Run the current BD 37/01 HA benchmark with equal girder shares.

    This is intentionally verification-only. The longitudinal HA mechanics and
    project geometry are real; equal transverse shares must be replaced by a
    validated analytical or grillage distribution before production design or
    ANN ground-truth generation.
    """
    if project.design_code != DesignCode.BS5400:
        raise ValueError("BS 5400 HA verification requires a BS5400 project.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This BS 5400 HA verification currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    carriageway_width_m = float(project.geometry.carriageway_width_m)
    girder_count = int(project.geometry.girder_count)
    layout = notional_lane_layout_bd37_01(carriageway_width_m)
    distributions = [
        equal_lane_distribution(lane_number, girder_count)
        for lane_number in range(1, layout.lane_count + 1)
    ]
    return run_simple_span_ha_bridge_traffic_bd37_01(
        span_m=span_m,
        carriageway_width_m=carriageway_width_m,
        lane_distributions=distributions,
    )


def run_project_internal_bs5400_t_girder_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    section: BS5400TGirderInput,
    factors: BS5400Factors,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
) -> ProjectBS5400TGirderVerificationResult:
    """Run deck Gk + HA Qk + BS 5400 ULS checks for one internal T-girder.

    The transverse HA distribution is equal-share verification only. This path
    is for benchmark plumbing and hand-check comparison, not production design
    or ANN training until transverse distribution is independently verified.
    """
    girder_count = int(project.geometry.girder_count)
    if not 2 <= girder_index <= girder_count - 1:
        raise ValueError(
            "This verification helper is for internal girders only; edge-girder "
            "permanent-load tributary widths must be modelled separately."
        )

    permanent = internal_girder_characteristic_permanent_effects(
        project,
        span_index=span_index,
        additional=additional_permanent,
    )
    traffic = run_project_ha_equal_share_verification(
        project,
        span_index=span_index,
    )
    item = traffic.girder_effects[girder_index - 1]
    live = LoadEffects(moment_knm=item.moment_knm, shear_kn=item.shear_kn)
    design = run_bs5400_t_girder_case(
        project,
        permanent_effects=permanent,
        live_effects=live,
        factors=factors,
        section=section,
    )

    return ProjectBS5400TGirderVerificationResult(
        traffic=traffic,
        permanent_characteristic=permanent,
        traffic_characteristic=live,
        design=design,
        traffic_distribution_method=item.method,
        status=(
            "Project BS 5400 HA-to-T-girder verification path complete; transverse "
            "distribution remains equal-share verification only."
        ),
    )
