from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.research.limit_states import deflection_limit_state
from rc_bridge.workflow.project_continuous import (
    ProjectContinuousAnalysisResult,
    ProjectContinuousMovingAnalysisResult,
)


@dataclass(frozen=True)
class ContinuousDeflectionServiceabilityCheck:
    calculated_max_abs_deflection_mm: float
    allowable_deflection_mm: float
    utilization: float
    g_deflection_mm: float
    passes: bool
    governing_span_index: int
    governing_local_position_m: float
    governing_global_position_m: float
    load_case_name: str
    status: str


@dataclass(frozen=True)
class ContinuousMovingDeflectionServiceabilityCheck:
    calculated_max_abs_deflection_mm: float
    allowable_deflection_mm: float
    utilization: float
    g_deflection_mm: float
    passes: bool
    governing_span_index: int
    governing_local_position_m: float
    governing_global_position_m: float
    governing_lead_position_m: float
    load_case_name: str
    status: str


def _deflection_margin(
    calculated_mm: float,
    allowable_deflection_mm: float,
) -> tuple[float, float, bool]:
    if allowable_deflection_mm <= 0.0:
        raise ValueError("Allowable deflection must be positive.")
    utilization = calculated_mm / allowable_deflection_mm
    margin = deflection_limit_state(allowable_deflection_mm, calculated_mm)
    return utilization, margin, margin >= 0.0


def check_project_continuous_deflection(
    analysis: ProjectContinuousAnalysisResult,
    *,
    allowable_deflection_mm: float,
) -> ContinuousDeflectionServiceabilityCheck:
    """Check a solved continuous-girder load case against an explicit deflection limit.

    The workflow deliberately does not invent an ``L/n`` limit, service load
    combination, gross/cracked stiffness, creep multiplier or National Annex
    value. Those assumptions must already be reflected in the supplied analysis
    and the caller-selected allowable deflection.
    """
    calculated_mm = analysis.max_abs_vertical_displacement_m * 1000.0
    utilization, margin, passes = _deflection_margin(
        calculated_mm,
        allowable_deflection_mm,
    )
    return ContinuousDeflectionServiceabilityCheck(
        calculated_max_abs_deflection_mm=calculated_mm,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=margin,
        passes=passes,
        governing_span_index=analysis.max_abs_vertical_displacement_span_index,
        governing_local_position_m=analysis.max_abs_vertical_displacement_local_position_m,
        governing_global_position_m=analysis.max_abs_vertical_displacement_global_position_m,
        load_case_name=analysis.load_case_name,
        status=(
            "Continuous-girder vertical deflection checked against an explicit caller-supplied "
            "serviceability limit; load combination and stiffness assumptions remain traceable"
        ),
    )


def check_project_continuous_moving_deflection(
    analysis: ProjectContinuousMovingAnalysisResult,
    *,
    allowable_deflection_mm: float,
) -> ContinuousMovingDeflectionServiceabilityCheck:
    """Check a moving axle-train deflection envelope against an explicit limit.

    The moving train and any static loads in ``analysis`` are whatever the caller
    supplied. This function does not label them as an EN 1990 service combination
    or apply traffic representative-value factors implicitly.
    """
    envelope = analysis.envelope
    calculated_mm = envelope.max_abs_displacement_m * 1000.0
    utilization, margin, passes = _deflection_margin(
        calculated_mm,
        allowable_deflection_mm,
    )
    return ContinuousMovingDeflectionServiceabilityCheck(
        calculated_max_abs_deflection_mm=calculated_mm,
        allowable_deflection_mm=allowable_deflection_mm,
        utilization=utilization,
        g_deflection_mm=margin,
        passes=passes,
        governing_span_index=envelope.max_abs_displacement_span_index,
        governing_local_position_m=envelope.max_abs_displacement_local_position_m,
        governing_global_position_m=envelope.max_abs_displacement_global_position_m,
        governing_lead_position_m=envelope.max_abs_displacement_lead_position_m,
        load_case_name=analysis.load_case_name,
        status=(
            "Continuous moving axle-train vertical deflection checked against an explicit "
            "caller-supplied limit; train definition, service factors and span EI remain explicit"
        ),
    )
