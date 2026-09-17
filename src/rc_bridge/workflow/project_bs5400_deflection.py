from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.loads import PointLoad
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.bs5400_deflection import (
    BS5400DeflectionResult,
    bs5400_simple_span_elastic_deflection,
)
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    internal_girder_deck_self_weight_kn_m,
)
from rc_bridge.workflow.project_bs5400 import run_project_ha_equal_share_verification


@dataclass(frozen=True)
class BS5400ProjectDeflectionInput:
    long_term_concrete_modulus_mpa: float
    short_term_concrete_modulus_mpa: float
    permanent_second_moment_mm4: float
    live_second_moment_mm4: float
    allowable_deflection_mm: float | None = None
    integration_segments: int = 2000

    def __post_init__(self) -> None:
        if min(
            self.long_term_concrete_modulus_mpa,
            self.short_term_concrete_modulus_mpa,
            self.permanent_second_moment_mm4,
            self.live_second_moment_mm4,
        ) <= 0.0:
            raise ValueError("BS 5400 deflection stiffness inputs must be positive.")
        if self.allowable_deflection_mm is not None and self.allowable_deflection_mm <= 0.0:
            raise ValueError("allowable_deflection_mm must be positive when supplied.")
        if self.integration_segments < 2 or self.integration_segments % 2 != 0:
            raise ValueError("integration_segments must be an even integer of at least 2.")


@dataclass(frozen=True)
class ProjectBS5400DeflectionVerificationResult:
    deflection: BS5400DeflectionResult
    permanent_udl_kn_m: float
    live_udl_kn_m: float
    live_point_loads: tuple[PointLoad, ...]
    traffic_distribution_method: str
    status: str


def run_project_internal_bs5400_deflection_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    input: BS5400ProjectDeflectionInput,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
) -> ProjectBS5400DeflectionVerificationResult:
    """Run nominal-load BS 5400 midspan deflection for one internal girder.

    This verification path uses equal transverse shares for every HA lane. The
    longitudinal load shape is retained explicitly: each lane contributes its
    distributed UDL and a distributed KEL at midspan, which governs simple-span
    midspan deflection. Production use requires validated transverse factors or
    grillage-derived service-load effects.
    """
    if project.design_code != DesignCode.BS5400:
        raise ValueError("BS 5400 deflection verification requires a BS5400 project.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError("This BS 5400 deflection workflow currently supports simple spans only.")
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    girder_count = int(project.geometry.girder_count)
    if not 2 <= girder_index <= girder_count - 1:
        raise ValueError("This verification helper is for internal girders only.")

    span_m = float(project.geometry.span_lengths_m[span_index])
    permanent_udl = internal_girder_deck_self_weight_kn_m(project)
    permanent_udl += (additional_permanent or UniformPermanentLoadInput()).total_additional_kn_m

    traffic = run_project_ha_equal_share_verification(project, span_index=span_index)
    share = 1.0 / girder_count
    live_udl = sum(envelope.lane_load.udl_kn_m * share for envelope in traffic.lane_envelopes)
    live_points = tuple(
        PointLoad(
            magnitude_kn=envelope.lane_load.kel_kn * share,
            position_m=span_m / 2.0,
            label=f"HA lane {envelope.lane_load.lane_number} KEL equal share",
        )
        for envelope in traffic.lane_envelopes
    )

    deflection = bs5400_simple_span_elastic_deflection(
        span_m=span_m,
        permanent_udl_kn_m=permanent_udl,
        live_udl_kn_m=live_udl,
        live_point_loads=live_points,
        long_term_concrete_modulus_mpa=input.long_term_concrete_modulus_mpa,
        short_term_concrete_modulus_mpa=input.short_term_concrete_modulus_mpa,
        permanent_second_moment_mm4=input.permanent_second_moment_mm4,
        live_second_moment_mm4=input.live_second_moment_mm4,
        allowable_deflection_mm=input.allowable_deflection_mm,
        integration_segments=input.integration_segments,
    )

    method = traffic.girder_effects[girder_index - 1].method
    return ProjectBS5400DeflectionVerificationResult(
        deflection=deflection,
        permanent_udl_kn_m=permanent_udl,
        live_udl_kn_m=live_udl,
        live_point_loads=live_points,
        traffic_distribution_method=method,
        status=(
            "Project BS 5400 nominal-load deflection verification with equal-share HA "
            "transverse distribution; validated distribution and construction-stage effects remain pending"
        ),
    )
