from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.application.design_checks import ApplicationDesignInterpretationSuite
from rc_bridge.application.fatigue import FatigueApplicationResult
from rc_bridge.application.local_deck import LocalDeckDesignResult
from rc_bridge.application.verification_import import ApplicationVerificationImportReport
from rc_bridge.core.models import (
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    TGirderProfile,
)
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    native_lm1_girder_moment_diagram,
)


@dataclass(frozen=True)
class BridgePreviewData:
    span_lengths_m: tuple[float, ...]
    deck_width_m: float
    carriageway_left_m: float
    carriageway_right_m: float
    girder_y_m: tuple[float, ...]
    girder_shape: str
    girder_outline_m: tuple[tuple[float, float], ...]
    girder_depth_m: float
    false_slab_depth_m: float
    in_situ_slab_depth_m: float

    @property
    def total_length_m(self) -> float:
        return sum(self.span_lengths_m)


@dataclass(frozen=True)
class AnalysisGirderMetric:
    girder_index: int
    y_m: float
    moment_knm: float
    shear_kn: float
    torsion_knm: float
    deflection_mm: float | None


@dataclass(frozen=True)
class AnalysisDashboardData:
    girders: tuple[AnalysisGirderMetric, ...]
    max_moment_knm: float
    max_shear_kn: float
    max_torsion_knm: float
    max_deflection_mm: float | None
    evaluated_case_count: int
    prepared_structure_count: int
    reused_factorization_solve_count: int


@dataclass(frozen=True)
class AnalysisLineDiagram:
    girder_index: int
    metric: str
    case_id: int
    stations_m: tuple[float, ...]
    values: tuple[float, ...]
    unit: str
    note: str


@dataclass(frozen=True)
class DesignGirderMetric:
    girder_index: int
    flexure_utilization: float
    shear_utilization: float
    crack_utilization: float
    deflection_utilization: float
    governing_utilization: float
    provided_bars: str
    provided_links: str
    status: str


@dataclass(frozen=True)
class ConstructionStageMetric:
    girder_index: int
    stage: str
    moment_knm: float
    shear_kn: float
    flexural_utilization: float
    shear_utilization: float
    governing_utilization: float
    status: str


@dataclass(frozen=True)
class DesignDashboardData:
    girders: tuple[DesignGirderMetric, ...]
    construction_stages: tuple[ConstructionStageMetric, ...]
    worst_utilization: float
    governing_girder_index: int | None
    blocker_count: int
    all_current_checks_pass: bool


@dataclass(frozen=True)
class DeckDashboardData:
    stations_y_m: tuple[float, ...]
    permanent_moments_knm_per_m: tuple[float, ...]
    lm2_moments_knm_per_m: tuple[float, ...] | None
    bottom_reinforcement: str
    top_reinforcement: str
    bottom_utilization: float
    top_utilization: float
    shear_utilization: float
    status: str
    fatigue_status: str


@dataclass(frozen=True)
class VerificationMetric:
    result_id: int
    name: str
    status: str
    max_relative_error: float | None
    failed_count: int
    coverage_complete: bool


@dataclass(frozen=True)
class VerificationDashboardData:
    source_name: str
    status: str
    imported_count: int
    requested_count: int
    missing_count: int
    failed_count: int
    max_relative_error: float | None
    results: tuple[VerificationMetric, ...]


def _girder_outline(project: ProjectInput) -> tuple[tuple[float, float], ...]:
    profile = project.geometry.girder_profile
    if isinstance(profile, RectangularGirderProfile):
        half = float(profile.width_m) / 2.0
        depth = float(profile.depth_m)
        return (
            (-half, 0.0),
            (half, 0.0),
            (half, depth),
            (-half, depth),
        )
    if isinstance(profile, TGirderProfile):
        half_f = float(profile.flange_width_m) / 2.0
        half_w = float(profile.web_width_m) / 2.0
        tf = float(profile.flange_thickness_m)
        depth = float(profile.total_depth_m)
        return (
            (-half_f, 0.0),
            (half_f, 0.0),
            (half_f, tf),
            (half_w, tf),
            (half_w, depth),
            (-half_w, depth),
            (-half_w, tf),
            (-half_f, tf),
        )
    if isinstance(profile, IGirderProfile):
        half_top = float(profile.top_flange_width_m) / 2.0
        half_bottom = float(profile.bottom_flange_width_m) / 2.0
        half_web = float(profile.web_width_m) / 2.0
        top_t = float(profile.top_flange_thickness_m)
        web_d = float(profile.web_depth_m)
        depth = float(profile.total_depth_m)
        bottom_top = top_t + web_d
        return (
            (-half_top, 0.0),
            (half_top, 0.0),
            (half_top, top_t),
            (half_web, top_t),
            (half_web, bottom_top),
            (half_bottom, bottom_top),
            (half_bottom, depth),
            (-half_bottom, depth),
            (-half_bottom, bottom_top),
            (-half_web, bottom_top),
            (-half_web, top_t),
            (-half_top, top_t),
        )

    depth = float(project.geometry.girder_depth_m)
    half = min(float(project.geometry.girder_spacing_m) * 0.12, 0.3)
    return ((-half, 0.0), (half, 0.0), (half, depth), (-half, depth))


def bridge_preview_data(project: ProjectInput) -> BridgePreviewData:
    geometry = project.geometry
    count = int(geometry.girder_count)
    spacing = float(geometry.girder_spacing_m)
    centre_offset = 0.5 * (count - 1) * spacing
    girder_y_m = tuple(
        index * spacing - centre_offset
        for index in range(count)
    )
    return BridgePreviewData(
        span_lengths_m=tuple(float(value) for value in geometry.span_lengths_m),
        deck_width_m=float(geometry.deck_width_m),
        carriageway_left_m=float(geometry.carriageway_left_edge_m),
        carriageway_right_m=float(geometry.carriageway_right_edge_m),
        girder_y_m=girder_y_m,
        girder_shape=geometry.section_type.value,
        girder_outline_m=_girder_outline(project),
        girder_depth_m=float(geometry.girder_depth_m),
        false_slab_depth_m=float(
            geometry.deck_construction.precast_false_slab_depth_m
        ),
        in_situ_slab_depth_m=float(geometry.deck_construction.in_situ_slab_depth_m),
    )


def analysis_dashboard_data(
    result: ProjectNativeLM1GrillageSearchResult,
) -> AnalysisDashboardData:
    deflection_by_girder = {
        item.girder_index: abs(float(item.value_mm))
        for item in result.deflections
    }
    girders = tuple(
        AnalysisGirderMetric(
            girder_index=item.girder_index,
            y_m=float(item.y_m),
            moment_knm=abs(float(item.moment_knm.value)),
            shear_kn=abs(float(item.shear_kn.value)),
            torsion_knm=abs(float(item.torsion_knm.value)),
            deflection_mm=deflection_by_girder.get(item.girder_index),
        )
        for item in result.girders
    )
    return AnalysisDashboardData(
        girders=girders,
        max_moment_knm=max((item.moment_knm for item in girders), default=0.0),
        max_shear_kn=max((item.shear_kn for item in girders), default=0.0),
        max_torsion_knm=max((item.torsion_knm for item in girders), default=0.0),
        max_deflection_mm=max(
            (item.deflection_mm for item in girders if item.deflection_mm is not None),
            default=None,
        ),
        evaluated_case_count=result.evaluated_case_count,
        prepared_structure_count=result.prepared_structure_count,
        reused_factorization_solve_count=result.reused_factorization_solve_count,
    )


def analysis_girder_diagram(
    result: ProjectNativeLM1GrillageSearchResult,
    *,
    girder_index: int,
    metric: str,
) -> AnalysisLineDiagram:
    """Recover one signed governing longitudinal response diagram for the GUI."""

    girder = next(
        (item for item in result.girders if item.girder_index == girder_index),
        None,
    )
    if girder is None:
        raise ValueError(f"Unknown girder index {girder_index}.")

    metric_key = metric.strip().lower()
    if metric_key == "moment":
        case_id = girder.moment_knm.case_id
        diagram = native_lm1_girder_moment_diagram(
            result,
            girder_index=girder_index,
            case_id=case_id,
        )
        return AnalysisLineDiagram(
            girder_index=girder_index,
            metric="Moment",
            case_id=case_id,
            stations_m=diagram.stations_m,
            values=diagram.moments_knm,
            unit="kNm",
            note="Signed internal section moment from the exact governing LM1 case.",
        )

    if metric_key == "deflection":
        trace = result.deflection_for_girder(girder_index)
        case_id = trace.case_id
    elif metric_key == "shear":
        case_id = girder.shear_kn.case_id
    elif metric_key == "torsion":
        case_id = girder.torsion_knm.case_id
    else:
        raise ValueError(f"Unsupported analysis diagram metric: {metric}")

    case = next(
        (item for item in result.cases if item.placement.case_id == case_id),
        None,
    )
    if case is None:
        raise RuntimeError(
            f"Governing case {case_id} is not retained in the native LM1 result."
        )

    nodes = {item.node_id: item for item in case.model.nodes}
    target_y = float(girder.y_m)

    if metric_key == "deflection":
        node_results = {item.node_id: item for item in case.analysis.nodes}
        points = sorted(
            (
                (float(node.x_m), node_results[node.node_id].vertical_displacement_m * 1000.0)
                for node in case.model.nodes
                if abs(float(node.y_m) - target_y) <= 1.0e-9
            ),
            key=lambda item: item[0],
        )
        return AnalysisLineDiagram(
            girder_index=girder_index,
            metric="Deflection",
            case_id=case_id,
            stations_m=tuple(item[0] for item in points),
            values=tuple(item[1] for item in points),
            unit="mm",
            note=(
                "Signed nodal vertical displacement from the exact governing deflection "
                "case; the solver's reported governing displacement may occur between nodes."
            ),
        )

    member_results = {item.member_id: item for item in case.analysis.members}
    longitudinal = []
    for beam in case.model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(float(ni.y_m) - target_y) <= 1.0e-9
            and abs(float(nj.y_m) - target_y) <= 1.0e-9
            and float(nj.x_m) > float(ni.x_m) + 1.0e-9
        ):
            longitudinal.append((float(ni.x_m), float(nj.x_m), beam.member_id))
    longitudinal.sort()

    stations: list[float] = []
    values: list[float] = []
    for x_i, x_j, member_id in longitudinal:
        end = member_results[member_id]
        if metric_key == "shear":
            left_value = -float(end.i_vertical_force_kn)
            right_value = float(end.j_vertical_force_kn)
            unit = "kN"
            title = "Shear"
        else:
            left_value = -float(end.i_torsion_knm)
            right_value = float(end.j_torsion_knm)
            unit = "kNm"
            title = "Torsion"
        stations.extend((x_i, x_j))
        values.extend((left_value, right_value))

    return AnalysisLineDiagram(
        girder_index=girder_index,
        metric=title,
        case_id=case_id,
        stations_m=tuple(stations),
        values=tuple(values),
        unit=unit,
        note=(
            "Signed member-end internal actions from the exact governing LM1 case. "
            "Repeated stations preserve genuine joint jumps."
        ),
    )


def design_dashboard_data(
    result: ApplicationDesignInterpretationSuite,
) -> DesignDashboardData:
    girders: list[DesignGirderMetric] = []
    stages: list[ConstructionStageMetric] = []
    for row in result.girders:
        values = (
            float(row.design.uls_design.flexure.utilization),
            float(row.design.shear_utilization),
            float(row.design.crack.utilization),
            float(row.design.deflection.utilization),
        )
        girders.append(
            DesignGirderMetric(
                girder_index=row.girder_index,
                flexure_utilization=values[0],
                shear_utilization=values[1],
                crack_utilization=values[2],
                deflection_utilization=values[3],
                governing_utilization=max(values),
                provided_bars=(
                    f"{row.selected_bars.bar_count}-Y"
                    f"{row.selected_bars.bar_diameter_mm:g}"
                ),
                provided_links=(
                    f"{row.selected_links.leg_count}L-Y"
                    f"{row.selected_links.link_diameter_mm:g}"
                    f"@{row.selected_links.spacing_mm:g}"
                ),
                status="PASS" if row.passes_current_checks else "CHECK",
            )
        )
        for check in row.construction_stage_checks:
            stages.append(
                ConstructionStageMetric(
                    girder_index=row.girder_index,
                    stage=check.stage.value,
                    moment_knm=float(check.design_moment_knm),
                    shear_kn=float(check.design_shear_kn),
                    flexural_utilization=float(check.flexural_utilization),
                    shear_utilization=float(check.shear_utilization),
                    governing_utilization=max(
                        float(check.flexural_utilization),
                        float(check.shear_utilization),
                    ),
                    status="PASS" if check.passes else "CHECK",
                )
            )

    governing = max(girders, key=lambda item: item.governing_utilization, default=None)
    return DesignDashboardData(
        girders=tuple(girders),
        construction_stages=tuple(stages),
        worst_utilization=0.0 if governing is None else governing.governing_utilization,
        governing_girder_index=None if governing is None else governing.girder_index,
        blocker_count=len(result.coverage_blockers),
        all_current_checks_pass=result.all_current_checks_pass,
    )


def deck_dashboard_data(
    deck: LocalDeckDesignResult,
    fatigue: FatigueApplicationResult | None = None,
) -> DeckDashboardData:
    fatigue_status = "NOT RUN"
    if fatigue is not None:
        if fatigue.passes is True:
            fatigue_status = "PASS"
        elif fatigue.passes is False:
            fatigue_status = "CHECK"
        else:
            fatigue_status = "BLOCKED"

    return DeckDashboardData(
        stations_y_m=tuple(float(value) for value in deck.permanent.stations_y_m),
        permanent_moments_knm_per_m=tuple(
            float(value) for value in deck.permanent.moments_knm_per_m
        ),
        lm2_moments_knm_per_m=(
            None
            if deck.lm2_governing is None
            else tuple(float(value) for value in deck.lm2_governing.moments_knm_per_m)
        ),
        bottom_reinforcement=deck.bottom_transverse.arrangement.label,
        top_reinforcement=deck.top_transverse.arrangement.label,
        bottom_utilization=float(deck.bottom_transverse.utilization),
        top_utilization=float(deck.top_transverse.utilization),
        shear_utilization=float(deck.one_way_shear.utilization),
        status="PASS" if deck.passes else "CHECK",
        fatigue_status=fatigue_status,
    )


def verification_dashboard_data(
    report: ApplicationVerificationImportReport,
) -> VerificationDashboardData:
    rows = tuple(
        VerificationMetric(
            result_id=item.result_id,
            name=item.result_name,
            status="PASS" if item.passes else "FAIL",
            max_relative_error=item.maximum_relative_error,
            failed_count=item.failed_count,
            coverage_complete=item.coverage.complete,
        )
        for item in report.result_sets
    )
    return VerificationDashboardData(
        source_name=report.source_name,
        status="PASS" if report.passes else "REVIEW / FAIL",
        imported_count=len(report.result_sets),
        requested_count=len(report.requested_result_ids),
        missing_count=len(report.missing_result_ids),
        failed_count=len(report.failed_result_ids),
        max_relative_error=report.maximum_relative_error,
        results=rows,
    )
