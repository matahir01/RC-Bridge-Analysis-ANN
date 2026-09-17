from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.codes.bs5400.combinations import BS5400Factors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.bs5400_girder import BS5400TGirderInput
from rc_bridge.workflow.project_bridge import UniformPermanentLoadInput
from rc_bridge.workflow.project_bs5400 import (
    BS5400TServiceabilityInput,
    ProjectBS5400TGirderSLSResult,
    ProjectBS5400TGirderVerificationResult,
    run_project_internal_bs5400_t_girder_sls_verification,
    run_project_internal_bs5400_t_girder_verification,
)
from rc_bridge.workflow.project_bs5400_deflection import (
    BS5400ProjectDeflectionInput,
    ProjectBS5400DeflectionVerificationResult,
    run_project_internal_bs5400_deflection_verification,
)


@dataclass(frozen=True)
class ProjectBS5400CompleteVerificationResult:
    """Consolidated BS 5400 verification result for one internal T-girder."""

    uls: ProjectBS5400TGirderVerificationResult
    cracking: ProjectBS5400TGirderSLSResult
    deflection: ProjectBS5400DeflectionVerificationResult
    traffic_distribution_method: str
    status: str


def run_project_internal_bs5400_complete_verification(
    project: ProjectInput,
    *,
    girder_index: int,
    section: BS5400TGirderInput,
    factors: BS5400Factors,
    serviceability: BS5400TServiceabilityInput,
    deflection: BS5400ProjectDeflectionInput,
    span_index: int = 0,
    additional_permanent: UniformPermanentLoadInput | None = None,
) -> ProjectBS5400CompleteVerificationResult:
    """Run ULS flexure/shear plus crack-width and deflection verification.

    All three paths intentionally retain the same verification-only HA equal-share
    transverse distribution. This wrapper does not upgrade that distribution to a
    production method; it only guarantees that ULS and SLS results are packaged
    together with consistent provenance before later ANN/export integration.
    """
    uls = run_project_internal_bs5400_t_girder_verification(
        project,
        girder_index=girder_index,
        section=section,
        factors=factors,
        span_index=span_index,
        additional_permanent=additional_permanent,
    )
    cracking = run_project_internal_bs5400_t_girder_sls_verification(
        project,
        girder_index=girder_index,
        section=section,
        serviceability=serviceability,
        span_index=span_index,
        additional_permanent=additional_permanent,
    )
    deflection_result = run_project_internal_bs5400_deflection_verification(
        project,
        girder_index=girder_index,
        input=deflection,
        span_index=span_index,
        additional_permanent=additional_permanent,
    )

    methods = {
        uls.traffic_distribution_method,
        cracking.traffic_distribution_method,
        deflection_result.traffic_distribution_method,
    }
    if len(methods) != 1:
        raise RuntimeError(
            "BS 5400 ULS/cracking/deflection results do not share one transverse "
            "distribution provenance."
        )
    method = methods.pop()

    return ProjectBS5400CompleteVerificationResult(
        uls=uls,
        cracking=cracking,
        deflection=deflection_result,
        traffic_distribution_method=method,
        status=(
            "Consolidated BS 5400 internal T-girder verification complete for ULS "
            "flexure/shear, surface cracking and nominal-load deflection; transverse "
            "distribution remains verification-only until independently validated."
        ),
    )
