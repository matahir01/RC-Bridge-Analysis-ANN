"""Incremental elastic permanent-action analysis, not construction acceptance.

New concrete is assumed stress-free when activated in the already-deformed
configuration. Previously applied loads are NOT reapplied to the final stiffness.
The grid, restraints and continuity remain unchanged throughout. Support removal,
propping, staged continuity, shrinkage, creep redistribution and layer stress
history are outside this workflow. Explicit effective stiffness is an input, not
a time-dependent constitutive model. Independent validation is still required.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from rc_bridge.analysis.grillage_solver import (
    GrillageAnalysisResult,
    GrillageMemberEndResult,
    GrillageNodeResult,
    solve_vertical_grillage,
)
from rc_bridge.core.models import PermanentActionStage, ProjectInput, SupportSystem
from rc_bridge.export.model_verification_package import (
    ModelVerificationExportPackage,
    build_model_verification_export_package,
)
from rc_bridge.export.verification_model import (
    VerificationLoadCase,
    VerificationModel,
    VerificationUniformLoad,
)
from rc_bridge.workflow.grillage_verification_export import (
    GrillageSectionProperties,
    GrillageStiffnessModifiers,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)
from rc_bridge.workflow.project_bridge import (
    ProjectPermanentLoadSegment,
    UniformPermanentLoadInput,
    girder_permanent_load_segments,
)


@dataclass(frozen=True)
class PermanentGrillageStageInput:
    """Stiffness active when this stage's characteristic load increment arrives.

    An early-stage transverse override represents a cross-beam/equivalent member
    at EVERY supplied grid station, including supports. Its appropriateness must
    be justified in ``basis``; no temporary diaphragm layout is inferred.
    """

    stage: PermanentActionStage
    basis: str
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...] | None = None
    transverse_section: GrillageSectionProperties | None = None
    stiffness_modifiers: GrillageStiffnessModifiers | None = None
    deck_construction_false_slab_participates: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage", PermanentActionStage(self.stage))
        if not self.basis.strip():
            raise ValueError("A construction-stage stiffness basis is required.")
        if self.stage != PermanentActionStage.SUPERIMPOSED and self.transverse_section is None:
            raise ValueError(
                "Pre-final construction stages require an explicit transverse section."
            )
        if (
            self.deck_construction_false_slab_participates
            and self.stage != PermanentActionStage.DECK_CONSTRUCTION
        ):
            raise ValueError(
                "False-slab stage participation is only valid during deck construction."
            )


@dataclass(frozen=True)
class PermanentGrillageLoadAssignment:
    """Trace one physical/explicit action to its exact clipped member loads."""

    girder_index: int
    segment: ProjectPermanentLoadSegment
    member_loads: tuple[VerificationUniformLoad, ...]


@dataclass(frozen=True)
class CumulativePermanentGrillageResponse:
    """Signed sum of increments, NOT a solution at the final section stiffness.

    In particular, final EI times cumulative curvature must not be used to
    reconstruct moment. Recover each increment with its own stiffness first.
    This object deliberately has no single load-case/model identity.
    """

    nodes: tuple[GrillageNodeResult, ...]
    members: tuple[GrillageMemberEndResult, ...]
    total_applied_vertical_load_kn: float
    total_vertical_reaction_kn: float
    vertical_equilibrium_residual_kn: float


@dataclass(frozen=True)
class PermanentGrillageStageResult:
    input: PermanentGrillageStageInput
    model: VerificationModel
    assignments: tuple[PermanentGrillageLoadAssignment, ...]
    increment: GrillageAnalysisResult
    cumulative: CumulativePermanentGrillageResponse


@dataclass(frozen=True)
class ProjectConstructionGrillageResult:
    stages: tuple[PermanentGrillageStageResult, ...]
    unchanged_supports_and_continuity_basis: str

    @property
    def final_response(self) -> CumulativePermanentGrillageResponse:
        return self.stages[-1].cumulative


def _cumulative_response(
    increments: tuple[GrillageAnalysisResult, ...],
) -> CumulativePermanentGrillageResponse:
    # All increments come from the same geometry/order/constraints. Keep the
    # signed local end actions, rather than adding independently enveloped maxima.
    nodes = tuple(
        GrillageNodeResult(
            node_id=items[0].node_id,
            **{
                name: sum(getattr(item, name) for item in items)
                for name in (
                    "vertical_displacement_m",
                    "rotation_x_rad",
                    "rotation_y_rad",
                    "vertical_reaction_kn",
                    "reaction_mx_knm",
                    "reaction_my_knm",
                )
            },
        )
        for items in zip(*(result.nodes for result in increments), strict=True)
    )
    members = tuple(
        GrillageMemberEndResult(
            member_id=items[0].member_id,
            node_i=items[0].node_i,
            node_j=items[0].node_j,
            length_m=items[0].length_m,
            **{
                name: sum(getattr(item, name) for item in items)
                for name in (
                    "i_vertical_force_kn",
                    "i_vertical_bending_moment_knm",
                    "i_torsion_knm",
                    "j_vertical_force_kn",
                    "j_vertical_bending_moment_knm",
                    "j_torsion_knm",
                )
            },
        )
        for items in zip(*(result.members for result in increments), strict=True)
    )
    return CumulativePermanentGrillageResponse(
        nodes=nodes,
        members=members,
        total_applied_vertical_load_kn=sum(r.total_applied_vertical_load_kn for r in increments),
        total_vertical_reaction_kn=sum(r.total_vertical_reaction_kn for r in increments),
        vertical_equilibrium_residual_kn=sum(
            r.vertical_equilibrium_residual_kn for r in increments
        ),
    )


def _assign_segment(
    model: VerificationModel,
    *,
    girder_index: int,
    segment: ProjectPermanentLoadSegment,
) -> PermanentGrillageLoadAssignment:
    nodes = {node.node_id: node for node in model.nodes}
    y_girders = sorted(
        {
            nodes[beam.node_i].y_m
            for beam in model.beams
            if abs(nodes[beam.node_i].x_m - nodes[beam.node_j].x_m) > 1.0e-9
        }
    )
    loads = []
    for beam in model.beams:
        ni, nj = nodes[beam.node_i], nodes[beam.node_j]
        if nj.x_m <= ni.x_m or abs(ni.y_m - y_girders[girder_index - 1]) > 1.0e-9:
            continue
        start = max(segment.x_start_m, ni.x_m)
        end = min(segment.x_end_m, nj.x_m)
        if end > start:
            loads.append(
                VerificationUniformLoad(
                    member_id=beam.member_id,
                    direction="GZ",
                    magnitude_kn_m=-segment.magnitude_kn_m,
                    start_m=start - ni.x_m,
                    end_m=end - ni.x_m,
                )
            )
    return PermanentGrillageLoadAssignment(girder_index, segment, tuple(loads))


def run_project_construction_grillage(
    project: ProjectInput,
    *,
    stages: tuple[PermanentGrillageStageInput, ...],
    transverse_stations_m: tuple[float, ...],
    unchanged_supports_and_continuity_basis: str,
    additional_permanent_by_girder: tuple[UniformPermanentLoadInput, ...] | None = None,
) -> ProjectConstructionGrillageResult:
    """Analyse all three ordered permanent-action stages without double counting.

    The existing tributary-area/statical-line allocation supplies longitudinal
    loads. This is NOT a physical transverse pressure/overhang-torsion analysis;
    local deck/overhang demands remain separate. Stage bounds are clipped to
    members as exact partial UDLs, without introducing fictitious cross-beams at
    load boundaries. Both single spans and unchanged-continuity multi-spans are
    supported. No construction sequence, age effects or validation is invented.
    """
    if tuple(item.stage for item in stages) != tuple(PermanentActionStage):
        raise ValueError("Supply each permanent-action stage exactly once in construction order.")
    if not unchanged_supports_and_continuity_basis.strip():
        raise ValueError("An explicit unchanged supports and continuity basis is required.")
    if (
        len(project.geometry.span_lengths_m) > 1
        and project.geometry.support_system != SupportSystem.CONTINUOUS
    ):
        raise ValueError("Multiple independent simple spans require separate construction models.")
    girder_count = int(project.geometry.girder_count)
    if (
        additional_permanent_by_girder is not None
        and len(additional_permanent_by_girder) != girder_count
    ):
        raise ValueError("Additional permanent inputs must match the project girder count.")
    segments = tuple(
        girder_permanent_load_segments(
            project,
            girder_index=index + 1,
            additional=(
                None
                if additional_permanent_by_girder is None
                else additional_permanent_by_girder[index]
            ),
        )
        for index in range(girder_count)
    )
    results: list[PermanentGrillageStageResult] = []
    for stage_input in stages:
        model = build_project_grillage_verification_model(
            project,
            longitudinal_sections_by_span=stage_input.longitudinal_sections_by_span,
            transverse_section=stage_input.transverse_section,
            transverse_stations_m=transverse_stations_m,
            load_case=GrillageVerificationLoadCase(name=f"G_{stage_input.stage.value}"),
            stiffness_modifiers=stage_input.stiffness_modifiers,
            automatic_section_stage=stage_input.stage,
            deck_construction_false_slab_participates=(
                stage_input.deck_construction_false_slab_participates
            ),
        )
        assignments = tuple(
            _assign_segment(model, girder_index=index + 1, segment=segment)
            for index, girder_segments in enumerate(segments)
            for segment in girder_segments
            if segment.stage == stage_input.stage and segment.magnitude_kn_m > 0.0
        )
        model = replace(
            model,
            load_cases=(
                VerificationLoadCase(
                    load_case_id=1,
                    name=model.load_cases[0].name,
                    uniform_loads=tuple(load for item in assignments for load in item.member_loads),
                ),
            ),
            metadata={
                **model.metadata,
                "purpose": "incremental_elastic_construction_analysis_requires_validation",
                "construction_stage_basis": stage_input.basis,
                "unchanged_supports_and_continuity_basis": unchanged_supports_and_continuity_basis,
                "permanent_transverse_allocation": (
                    "tributary area / statical line allocation; NOT physical overhang torsion"
                ),
                "construction_superposition": (
                    "sum signed stage increments; new concrete initially stress-free; "
                    "no propping/support changes, creep redistribution or shrinkage"
                ),
                "self_weight_basis": "physical weights included exactly once in stage member UDLs",
                "permanent_load_audit": json.dumps(
                    [
                        {
                            "girder_index": item.girder_index,
                            "source": item.segment.source,
                            "category": item.segment.category,
                            "stage": item.segment.stage.value,
                            "magnitude_kn_m": item.segment.magnitude_kn_m,
                            "x_start_m": item.segment.x_start_m,
                            "x_end_m": item.segment.x_end_m,
                            "member_ids": [load.member_id for load in item.member_loads],
                        }
                        for item in assignments
                    ],
                    sort_keys=True,
                ),
            },
        )
        model.validate_load_positions()
        increment = solve_vertical_grillage(model)
        cumulative = _cumulative_response((*[item.increment for item in results], increment))
        results.append(
            PermanentGrillageStageResult(
                stage_input,
                model,
                assignments,
                increment,
                cumulative,
            )
        )
    return ProjectConstructionGrillageResult(
        tuple(results), unchanged_supports_and_continuity_basis
    )


def build_construction_stage_verification_packages(
    result: ProjectConstructionGrillageResult,
) -> dict[str, ModelVerificationExportPackage]:
    """Export each exact analysed increment; never export a fictitious final-EI sum.

    For unchanged supports, signed external increments may be summed after
    confirming axes and model equivalence. Generating these files does not supply
    independent results or unlock any production/ANN verification manifest.
    """
    return {
        stage.input.stage.value: build_model_verification_export_package(stage.model)
        for stage in result.stages
    }
