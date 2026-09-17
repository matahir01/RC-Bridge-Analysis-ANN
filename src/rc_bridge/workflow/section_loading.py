from __future__ import annotations

from rc_bridge.analysis.loads import section_self_weight_kn_m
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.project_bridge import UniformPermanentLoadInput


def girder_profile_self_weight_kn_m(project: ProjectInput) -> float:
    """Return physical girder self-weight when explicit profile dimensions exist."""
    area_m2 = project.geometry.girder_profile_area_m2
    if area_m2 is None:
        raise ValueError(
            "Physical girder profile dimensions are required before girder self-weight can be derived."
        )
    return section_self_weight_kn_m(
        area_m2=area_m2,
        concrete_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )


def permanent_load_input_from_profile(
    project: ProjectInput,
    *,
    surfacing_and_finishes_kn_m: float = 0.0,
    assigned_barrier_and_services_kn_m: float = 0.0,
    other_kn_m: float = 0.0,
) -> UniformPermanentLoadInput:
    """Build explicit permanent line loads with self-weight derived from profile area."""
    return UniformPermanentLoadInput(
        girder_self_weight_kn_m=girder_profile_self_weight_kn_m(project),
        surfacing_and_finishes_kn_m=surfacing_and_finishes_kn_m,
        assigned_barrier_and_services_kn_m=assigned_barrier_and_services_kn_m,
        other_kn_m=other_kn_m,
    )
