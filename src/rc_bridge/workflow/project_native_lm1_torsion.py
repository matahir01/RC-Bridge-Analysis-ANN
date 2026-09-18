from __future__ import annotations

from dataclasses import dataclass

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
from rc_bridge.research.lm1_benchmark_runner import LM1ExternalBenchmarkSuiteReport
from rc_bridge.research.lm1_grillage_benchmark import LM1GoverningBenchmarkSuite
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    girder_characteristic_permanent_effects,
)
from rc_bridge.workflow.project_native_lm1 import require_native_lm1_external_benchmark
from rc_bridge.workflow.project_torsion import TorsionCellInput


@dataclass(frozen=True)
class NativeLM1ShearTorsionPoint:
    """One co-located native-grillage V/T check at a longitudinal member end."""

    case_id: int
    member_id: int
    member_end: str
    x_m: float
    traffic_shear_kn: float
    traffic_torsion_knm: float
    permanent_shear_kn: float
    design_shear_kn: float
    design_torsion_knm: float
    torsion: TorsionResult
    shear_strut: ShearReinforcementResult
    interaction: ShearTorsionInteractionResult


@dataclass(frozen=True)
class NativeLM1MatchedShearTorsionResult:
    """Matched native LM1 torsion design and V-T interaction for one girder."""

    girder_index: int
    governing_torsion: NativeLM1ShearTorsionPoint
    governing_interaction: NativeLM1ShearTorsionPoint
    evaluated_points: tuple[NativeLM1ShearTorsionPoint, ...]
    benchmark_source: str
    status: str

    @property
    def passes_interaction(self) -> bool:
        return self.governing_interaction.interaction.passes


def _require_simple_span_project(project: ProjectInput) -> float:
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Native LM1 shear-torsion design currently supports Eurocode only.")
    if project.geometry.support_system != SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Native LM1 matched shear-torsion design currently supports simple spans only."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError(
            "Native LM1 matched shear-torsion design currently requires exactly one span."
        )
    return float(project.geometry.span_lengths_m[0])


def _girder_longitudinal_member_ids(
    case,
    *,
    target_y_m: float,
    tolerance: float = 1.0e-8,
) -> tuple[int, ...]:
    nodes = {node.node_id: node for node in case.model.nodes}
    selected: list[tuple[float, int]] = []
    for beam in case.model.beams:
        node_i = nodes[beam.node_i]
        node_j = nodes[beam.node_j]
        dx = node_j.x_m - node_i.x_m
        dy = node_j.y_m - node_i.y_m
        if abs(dy) <= tolerance and abs(dx) > tolerance:
            y_m = 0.5 * (node_i.y_m + node_j.y_m)
            if abs(y_m - target_y_m) <= tolerance:
                selected.append((min(node_i.x_m, node_j.x_m), beam.member_id))
    if not selected:
        raise ValueError(
            f"Native LM1 case {case.placement.case_id} contains no longitudinal members "
            f"for girder line y={target_y_m:.6g} m."
        )
    return tuple(member_id for _, member_id in sorted(selected))


def _permanent_shear_at_x(
    *,
    maximum_support_shear_kn: float,
    span_m: float,
    x_m: float,
) -> float:
    if x_m < -1.0e-8 or x_m > span_m + 1.0e-8:
        raise ValueError("Longitudinal grillage member end lies outside the physical span.")
    x = min(max(x_m, 0.0), span_m)
    return maximum_support_shear_kn * abs(1.0 - 2.0 * x / span_m)


def check_project_native_lm1_matched_shear_torsion(
    project: ProjectInput,
    *,
    search: ProjectNativeLM1GrillageSearchResult,
    benchmark_suite: LM1GoverningBenchmarkSuite,
    benchmark_report: LM1ExternalBenchmarkSuiteReport,
    girder_index: int,
    section: TGirderDesignInput,
    torsion_cell: TorsionCellInput,
    additional_permanent: UniformPermanentLoadInput | None = None,
    uls_factors: EurocodeFactors | None = None,
    cot_theta: float = 2.0,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    alpha_cw: float = 1.0,
    nu1: float | None = None,
) -> NativeLM1MatchedShearTorsionResult:
    """Check torsion and V-T interaction using co-located native LM1 member-end effects.

    Independent M/V/T envelope maxima are appropriate for separate component
    checks, but V-T interaction must not combine a shear maximum from one traffic
    placement with a torsion maximum from another. This routine scans every
    native LM1 candidate case and every longitudinal member end of the selected
    girder, pairing shear and torsion from the same solved case and section.

    Permanent shear is the exact simple-span UDL shear magnitude derived from the
    selected girder's characteristic permanent-load model. It is combined
    conservatively by magnitude with the simultaneous LM1 traffic shear.
    """
    span_m = _require_simple_span_project(project)
    require_native_lm1_external_benchmark(
        search,
        benchmark_suite=benchmark_suite,
        benchmark_report=benchmark_report,
    )
    if not 1 <= girder_index <= int(project.geometry.girder_count):
        raise IndexError("girder_index is outside the project girder layout.")
    if len(search.girders) != int(project.geometry.girder_count):
        raise ValueError("Native LM1 search girder count does not match the project.")
    if section.web_width_m <= 0.0 or section.effective_depth_m <= 0.0:
        raise ValueError("T-girder shear dimensions must be positive.")

    policy = uls_factors or EurocodeFactors()
    permanent = girder_characteristic_permanent_effects(
        project,
        girder_index=girder_index,
        additional=additional_permanent,
    )
    target = next(item for item in search.girders if item.girder_index == girder_index)
    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)

    points: list[NativeLM1ShearTorsionPoint] = []
    for case in search.cases:
        member_ids = _girder_longitudinal_member_ids(
            case,
            target_y_m=target.y_m,
        )
        beams = {beam.member_id: beam for beam in case.model.beams}
        nodes = {node.node_id: node for node in case.model.nodes}
        results = {item.member_id: item for item in case.analysis.members}

        for member_id in member_ids:
            if member_id not in results:
                raise ValueError(
                    f"Native LM1 case {case.placement.case_id} is missing member result "
                    f"{member_id}."
                )
            beam = beams[member_id]
            result = results[member_id]
            end_data = (
                (
                    "I",
                    nodes[beam.node_i].x_m,
                    result.i_vertical_force_kn,
                    result.i_torsion_knm,
                ),
                (
                    "J",
                    nodes[beam.node_j].x_m,
                    result.j_vertical_force_kn,
                    result.j_torsion_knm,
                ),
            )
            for member_end, x_m, traffic_shear_signed, traffic_torsion_signed in end_data:
                traffic_shear = abs(float(traffic_shear_signed))
                traffic_torsion = abs(float(traffic_torsion_signed))
                permanent_shear = _permanent_shear_at_x(
                    maximum_support_shear_kn=permanent.shear_kn,
                    span_m=span_m,
                    x_m=float(x_m),
                )
                design_shear = (
                    policy.gamma_g_unfavourable * permanent_shear
                    + policy.gamma_q_traffic * traffic_shear
                )
                design_torsion = policy.gamma_q_traffic * traffic_torsion

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
                shear_strut = required_vertical_shear_reinforcement(
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
                    vrdmax_kn=shear_strut.vrdmax_kn,
                )
                points.append(
                    NativeLM1ShearTorsionPoint(
                        case_id=case.placement.case_id,
                        member_id=member_id,
                        member_end=member_end,
                        x_m=float(x_m),
                        traffic_shear_kn=traffic_shear,
                        traffic_torsion_knm=traffic_torsion,
                        permanent_shear_kn=permanent_shear,
                        design_shear_kn=design_shear,
                        design_torsion_knm=design_torsion,
                        torsion=torsion,
                        shear_strut=shear_strut,
                        interaction=interaction,
                    )
                )

    if not points:
        raise ValueError("Native LM1 matched shear-torsion scan produced no design points.")

    governing_torsion = max(points, key=lambda item: item.design_torsion_knm)
    governing_interaction = max(
        points,
        key=lambda item: item.interaction.utilization,
    )
    return NativeLM1MatchedShearTorsionResult(
        girder_index=girder_index,
        governing_torsion=governing_torsion,
        governing_interaction=governing_interaction,
        evaluated_points=tuple(points),
        benchmark_source=benchmark_report.source_name,
        status=(
            "EC2 torsion reinforcement uses the maximum native LM1 torsion demand; "
            "shear-torsion strut interaction is governed by co-located V/T from the same "
            "traffic case and member end, with simple-span permanent UDL shear added "
            "conservatively by magnitude."
        ),
    )
