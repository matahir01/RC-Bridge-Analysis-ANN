from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import equal_lane_distribution
from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.codes.bs5400.traffic import notional_lane_layout_bd37_01
from rc_bridge.codes.common import LoadEffects
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.bs5400_cracking import (
    BS5400TSectionCrackResult,
    crack_width_t_section_bs5400,
)
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


@dataclass(frozen=True)
class BS5400TServiceabilityInput:
    """Explicit project inputs needed only by the BS 5400 crack check."""

    total_depth_m: float
    ec_modified_mpa: float
    crack_point_depth_mm: float
    acr_mm: float
    nominal_cover_mm: float
    allowable_crack_width_mm: float
    es_mpa: float = 200000.0
    tension_zone_width_m: float | None = None

    def __post_init__(self) -> None:
        if min(
            self.total_depth_m,
            self.ec_modified_mpa,
            self.crack_point_depth_mm,
            self.acr_mm,
            self.allowable_crack_width_mm,
            self.es_mpa,
        ) <= 0.0:
            raise ValueError("BS 5400 serviceability dimensions and moduli must be positive.")
        if self.nominal_cover_mm < 0.0:
            raise ValueError("nominal_cover_mm cannot be negative.")
        if self.crack_point_depth_mm > self.total_depth_m * 1000.0:
            raise ValueError("crack_point_depth_mm cannot exceed the overall section depth.")
        if self.tension_zone_width_m is not None and self.tension_zone_width_m <= 0.0:
            raise ValueError("tension_zone_width_m must be positive when supplied.")


@dataclass(frozen=True)
class ProjectBS5400TGirderSLSResult:
    traffic: BS5400HABridgeTrafficResult
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    crack: BS5400TSectionCrackResult
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


def _internal_characteristic_effects(
    project: ProjectInput,
    *,
    girder_index: int,
    span_index: int,
    additional_permanent: UniformPermanentLoadInput | None,
) -> tuple[LoadEffects, BS5400HABridgeTrafficResult, LoadEffects, str]:
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
    traffic = run_project_ha_equal_share_verification(project, span_index=span_index)
    item = traffic.girder_effects[girder_index - 1]
    live = LoadEffects(moment_knm=item.moment_knm, shear_kn=item.shear_kn)
    return permanent, traffic, live, item.method


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
    permanent, traffic, live, method = _internal_characteristic_effects(
        project,
        girder_index=girder_index,
        span_index=span_index,
        additional_permanent=additional_permanent,
    )
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
        traffic_distribution_method=method,
        status=(
            "Project BS 5400 HA-to-T-girder verification path complete; transverse "
            "distribution remains equal-share verification only."
        ),
    )


def run_project_internal_bs5400_t_girder_sls_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    section: BS5400TGirderInput,
    serviceability: BS5400TServiceabilityInput,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
) -> ProjectBS5400TGirderSLSResult:
    """Run characteristic Gk + HA Qk through the BS 5400 T-girder crack check.

    The same verification-only equal transverse shares are used as in the ULS
    benchmark. Modified concrete modulus and crack-point geometry stay explicit
    because they depend on the serviceability basis and project detailing.
    """
    if section.effective_depth_m >= serviceability.total_depth_m:
        raise ValueError("Tension steel effective depth must be less than total depth.")

    permanent, traffic, live, method = _internal_characteristic_effects(
        project,
        girder_index=girder_index,
        span_index=span_index,
        additional_permanent=additional_permanent,
    )
    crack = crack_width_t_section_bs5400(
        effective_flange_width_m=section.effective_flange_width_m,
        flange_thickness_m=section.flange_thickness_m,
        web_width_m=section.web_width_m,
        total_depth_m=serviceability.total_depth_m,
        steel_area_mm2=section.steel_area_mm2,
        steel_depth_m=section.effective_depth_m,
        permanent_moment_knm=abs(permanent.moment_knm),
        live_moment_knm=abs(live.moment_knm),
        es_mpa=serviceability.es_mpa,
        ec_modified_mpa=serviceability.ec_modified_mpa,
        crack_point_depth_mm=serviceability.crack_point_depth_mm,
        acr_mm=serviceability.acr_mm,
        nominal_cover_mm=serviceability.nominal_cover_mm,
        allowable_crack_width_mm=serviceability.allowable_crack_width_mm,
        tension_zone_width_m=serviceability.tension_zone_width_m,
    )

    return ProjectBS5400TGirderSLSResult(
        traffic=traffic,
        permanent_characteristic=permanent,
        traffic_characteristic=live,
        crack=crack,
        traffic_distribution_method=method,
        status=(
            "Project BS 5400 characteristic HA crack-width verification path complete; "
            "transverse distribution remains equal-share verification only."
        ),
    )
