from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_station_response import (
    longitudinal_station_end_response,
)
from rc_bridge.codes.eurocode.combinations import EurocodeFactors
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.design.eurocode_shear import (
    ShearReinforcementResult,
    required_vertical_shear_reinforcement,
)
from rc_bridge.design.eurocode_torsion import (
    ShearTorsionInteractionResult,
    TorsionResult,
    shear_torsion_interaction,
    torsion_reinforcement_and_resistance,
)
from rc_bridge.workflow.project_continuous_design import ContinuousShearDesignInput
from rc_bridge.workflow.project_continuous_native import (
    ProjectContinuousNativeLM1EnvelopeResult,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput


@dataclass(frozen=True)
class ContinuousNativeShearTorsionPoint:
    """One co-located continuous V-T ULS check at one station side and LM1 case."""

    span_index: int
    local_position_m: float
    global_position_m: float
    side: str
    case_id: int | None
    member_id: int
    member_end: str
    gamma_g: float
    permanent_shear_kn: float
    permanent_torsion_knm: float
    traffic_shear_kn: float
    traffic_torsion_knm: float
    design_shear_kn: float
    design_torsion_knm: float
    torsion: TorsionResult
    shear_strut: ShearReinforcementResult
    interaction: ShearTorsionInteractionResult


@dataclass(frozen=True)
class ProjectContinuousNativeShearTorsionResult:
    girder_index: int
    governing_torsion: ContinuousNativeShearTorsionPoint
    governing_interaction: ContinuousNativeShearTorsionPoint
    evaluated_points: tuple[ContinuousNativeShearTorsionPoint, ...]
    torsion_cell: TorsionCellInput
    status: str

    @property
    def passes_interaction(self) -> bool:
        return self.governing_interaction.interaction.passes


def _span_bounds(
    project: ProjectInput,
    span_index: int,
) -> tuple[float, float]:
    spans = tuple(float(value) for value in project.geometry.span_lengths_m)
    if not 0 <= span_index < len(spans):
        raise IndexError("span_index is outside the project span layout.")
    start = sum(spans[:span_index])
    return start, start + spans[span_index]


def _evaluate_point(
    *,
    project: ProjectInput,
    section: ContinuousShearDesignInput,
    torsion_cell: TorsionCellInput,
    span_index: int,
    local_position_m: float,
    global_position_m: float,
    side: str,
    case_id: int | None,
    member_id: int,
    member_end: str,
    gamma_g: float,
    permanent_shear_kn: float,
    permanent_torsion_knm: float,
    traffic_shear_kn: float,
    traffic_torsion_knm: float,
    gamma_q: float,
    gamma_c: float,
    gamma_s: float,
    alpha_cc: float,
    alpha_cw: float,
    cot_theta: float,
    nu1: float | None,
) -> ContinuousNativeShearTorsionPoint:
    design_shear = abs(
        gamma_g * permanent_shear_kn + gamma_q * traffic_shear_kn
    )
    design_torsion = abs(
        gamma_g * permanent_torsion_knm + gamma_q * traffic_torsion_knm
    )
    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)

    torsion = torsion_reinforcement_and_resistance(
        ted_knm=design_torsion,
        ak_m2=torsion_cell.ak_m2,
        uk_m=torsion_cell.uk_m,
        tef_m=torsion_cell.tef_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        alpha_cw=alpha_cw,
        cot_theta=cot_theta,
        nu1=nu1,
    )
    shear = required_vertical_shear_reinforcement(
        ved_kn=design_shear,
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        cot_theta=cot_theta,
        alpha_cw=alpha_cw,
    )
    interaction = shear_torsion_interaction(
        ted_knm=design_torsion,
        trdmax_knm=torsion.trdmax_knm,
        ved_kn=design_shear,
        vrdmax_kn=shear.vrdmax_kn,
    )
    return ContinuousNativeShearTorsionPoint(
        span_index=span_index,
        local_position_m=local_position_m,
        global_position_m=global_position_m,
        side=side,
        case_id=case_id,
        member_id=member_id,
        member_end=member_end,
        gamma_g=gamma_g,
        permanent_shear_kn=permanent_shear_kn,
        permanent_torsion_knm=permanent_torsion_knm,
        traffic_shear_kn=traffic_shear_kn,
        traffic_torsion_knm=traffic_torsion_knm,
        design_shear_kn=design_shear,
        design_torsion_knm=design_torsion,
        torsion=torsion,
        shear_strut=shear,
        interaction=interaction,
    )


def check_project_continuous_native_matched_shear_torsion(
    project: ProjectInput,
    *,
    production: ProjectContinuousNativeLM1EnvelopeResult,
    section: ContinuousShearDesignInput,
    torsion_cell: TorsionCellInput,
    uls_factors: EurocodeFactors | None = None,
    cot_theta: float | None = None,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    alpha_cw: float = 1.0,
    nu1: float | None = None,
) -> ProjectContinuousNativeShearTorsionResult:
    """Scan co-located continuous V/T actions without mixing independent maxima.

    Each traffic point uses shear and torsion from the same solved LM1 case,
    longitudinal member end and station side. The signed cumulative construction
    shear/torsion at that same section is added before absolute ULS demand is
    formed. Both configured favourable and unfavourable permanent-action factors
    are evaluated with one common gamma_G per vector point; the larger actual
    interaction is retained rather than choosing different gamma_G values for V
    and T independently.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Continuous native shear-torsion currently supports Eurocode only.")
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous native shear-torsion requires CONTINUOUS supports.")
    if production.traffic is None or not production.traffic.cases:
        raise ValueError("Continuous native shear-torsion requires solved LM1 traffic cases.")
    if section.web_width_m <= 0.0 or section.effective_depth_m <= 0.0:
        raise ValueError("Continuous shear/torsion section geometry must be positive.")

    factors = uls_factors or EurocodeFactors()
    theta = section.cot_theta if cot_theta is None else cot_theta
    gamma_g_values = tuple(
        dict.fromkeys(
            (
                factors.gamma_g_unfavourable,
                factors.gamma_g_favourable,
            )
        )
    )
    girder_index = production.trace[0].girder_index
    if any(item.girder_index != girder_index for item in production.trace):
        raise ValueError("Continuous native production trace mixes multiple girders.")

    final_model = production.construction.stages[-1].model
    permanent_members = production.construction.final_response.members
    target_y_m = next(
        item.y_m
        for item in production.traffic.girders
        if item.girder_index == girder_index
    )

    points: list[ContinuousNativeShearTorsionPoint] = []
    for trace in production.trace:
        span_start, span_end = _span_bounds(project, trace.span_index)
        permanent = longitudinal_station_end_response(
            final_model,
            permanent_members,
            target_y_m=target_y_m,
            x_m=trace.global_position_m,
            side=trace.side,
            span_start_m=span_start,
            span_end_m=span_end,
        )

        # Keep a permanent-only baseline because every traffic search case carries
        # nonzero LM1 and an opposite-signed traffic action can reduce |G+Q|.
        for gamma_g in gamma_g_values:
            points.append(
                _evaluate_point(
                    project=project,
                    section=section,
                    torsion_cell=torsion_cell,
                    span_index=trace.span_index,
                    local_position_m=trace.local_position_m,
                    global_position_m=trace.global_position_m,
                    side=trace.side,
                    case_id=None,
                    member_id=permanent.member_id,
                    member_end=permanent.member_end,
                    gamma_g=gamma_g,
                    permanent_shear_kn=permanent.shear_kn,
                    permanent_torsion_knm=permanent.torsion_knm,
                    traffic_shear_kn=0.0,
                    traffic_torsion_knm=0.0,
                    gamma_q=factors.gamma_q_traffic,
                    gamma_c=gamma_c,
                    gamma_s=gamma_s,
                    alpha_cc=alpha_cc,
                    alpha_cw=alpha_cw,
                    cot_theta=theta,
                    nu1=nu1,
                )
            )

        for case in production.traffic.cases:
            response = longitudinal_station_end_response(
                case.model,
                case.analysis.members,
                target_y_m=target_y_m,
                x_m=trace.global_position_m,
                side=trace.side,
                span_start_m=span_start,
                span_end_m=span_end,
            )
            for gamma_g in gamma_g_values:
                points.append(
                    _evaluate_point(
                        project=project,
                        section=section,
                        torsion_cell=torsion_cell,
                        span_index=trace.span_index,
                        local_position_m=trace.local_position_m,
                        global_position_m=trace.global_position_m,
                        side=trace.side,
                        case_id=case.placement.case_id,
                        member_id=response.member_id,
                        member_end=response.member_end,
                        gamma_g=gamma_g,
                        permanent_shear_kn=permanent.shear_kn,
                        permanent_torsion_knm=permanent.torsion_knm,
                        traffic_shear_kn=response.shear_kn,
                        traffic_torsion_knm=response.torsion_knm,
                        gamma_q=factors.gamma_q_traffic,
                        gamma_c=gamma_c,
                        gamma_s=gamma_s,
                        alpha_cc=alpha_cc,
                        alpha_cw=alpha_cw,
                        cot_theta=theta,
                        nu1=nu1,
                    )
                )

    if not points:
        raise ValueError("Continuous matched shear-torsion scan produced no points.")
    governing_torsion = max(points, key=lambda item: item.design_torsion_knm)
    governing_interaction = max(
        points,
        key=lambda item: item.interaction.utilization,
    )
    return ProjectContinuousNativeShearTorsionResult(
        girder_index=girder_index,
        governing_torsion=governing_torsion,
        governing_interaction=governing_interaction,
        evaluated_points=tuple(points),
        torsion_cell=torsion_cell,
        status=(
            "Continuous EC2 V-T scan preserves one LM1 case/member-end/station-side pair "
            "for each interaction point and adds the signed cumulative staged permanent "
            "response at the same section. Favourable/unfavourable gamma_G branches are "
            "evaluated as whole vector points. Independent MIDAS/STAAD acceptance remains "
            "part of the final validation stage."
        ),
    )
