from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_displacement import (
    combined_longitudinal_deflection_peak,
    longitudinal_displacement_field,
)
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.research.limit_states import deflection_limit_state
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult
from rc_bridge.workflow.project_construction import ProjectConstructionGrillageResult


@dataclass(frozen=True)
class ContinuousNativeServiceDeflectionResult:
    girder_index: int
    traffic_factor: float
    calculated_max_abs_deflection_mm: float
    signed_governing_deflection_mm: float
    governing_global_position_m: float
    governing_case_id: int | None
    allowable_deflection_mm: float
    utilization: float
    g_deflection_mm: float
    passes: bool
    permanent_only_max_abs_deflection_mm: float
    status: str


def _girder_y_m(project: ProjectInput, girder_index: int) -> float:
    count = int(project.geometry.girder_count)
    if not 1 <= girder_index <= count:
        raise IndexError("girder_index is outside the project girder layout.")
    return (
        girder_index - 1 - 0.5 * (count - 1)
    ) * float(project.geometry.girder_spacing_m)


def run_project_continuous_native_service_deflection(
    project: ProjectInput,
    *,
    construction: ProjectConstructionGrillageResult,
    traffic: ProjectNativeLM1GrillageSearchResult,
    girder_index: int,
    traffic_factor: float,
    allowable_deflection_mm: float,
) -> ContinuousNativeServiceDeflectionResult:
    """Envelope staged permanent plus scaled native-LM1 vertical displacement.

    Permanent displacement is the signed cumulative construction-stage response,
    so earlier loads retain the stiffness active when they arrived. Each LM1 case
    keeps the stiffness used by the supplied traffic search. Permanent and traffic
    cubic Hermite fields may have different longitudinal grids; their union is
    searched analytically for interior zero-slope extrema.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native continuous service deflection requires Eurocode.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError(
            "Native continuous service deflection requires CONTINUOUS supports."
        )
    if len(project.geometry.span_lengths_m) < 2:
        raise ValueError("Native continuous service deflection requires at least two spans.")
    if not 0.0 <= traffic_factor <= 1.0:
        raise ValueError("traffic_factor must lie between zero and one.")
    if allowable_deflection_mm <= 0.0:
        raise ValueError("allowable_deflection_mm must be positive.")
    if not construction.stages:
        raise ValueError("Construction result contains no permanent-action stages.")
    if not traffic.cases and traffic_factor > 0.0:
        raise ValueError("Native LM1 search contains no traffic cases.")

    y_m = _girder_y_m(project, girder_index)
    final_model = construction.stages[-1].model
    permanent_field = longitudinal_displacement_field(
        final_model,
        construction.final_response.nodes,
        target_y_m=y_m,
    )
    permanent_peak = combined_longitudinal_deflection_peak(permanent_field)
    best_peak = permanent_peak
    best_case_id: int | None = None

    if traffic_factor > 0.0:
        for case in traffic.cases:
            traffic_field = longitudinal_displacement_field(
                case.model,
                case.analysis.nodes,
                target_y_m=y_m,
            )
            peak = combined_longitudinal_deflection_peak(
                permanent_field,
                traffic_field,
                traffic_factor=traffic_factor,
            )
            if peak.maximum_absolute_deflection_m > best_peak.maximum_absolute_deflection_m:
                best_peak = peak
                best_case_id = case.placement.case_id

    calculated_mm = best_peak.maximum_absolute_deflection_m * 1000.0
    utilization = calculated_mm / allowable_deflection_mm
    margin = deflection_limit_state(allowable_deflection_mm, calculated_mm)
    return ContinuousNativeServiceDeflectionResult(
        girder_index=girder_index,
        traffic_factor=traffic_factor,
        calculated_max_abs_deflection_mm=calculated_mm,
        signed_governing_deflection_mm=best_peak.signed_deflection_m * 1000.0,
        governing_global_position_m=best_peak.position_m,
        governing_case_id=best_case_id,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=margin,
        passes=margin >= 0.0,
        permanent_only_max_abs_deflection_mm=(
            permanent_peak.maximum_absolute_deflection_m * 1000.0
        ),
        status=(
            "Continuous service deflection uses cumulative staged permanent displacement "
            "plus scaled native full-width LM1 displacement. The FE cubic fields are "
            "combined on their exact grid union and interior displacement extrema are "
            "solved analytically. The traffic search stiffness and service factor remain "
            "explicit caller/project assumptions."
        ),
    )
