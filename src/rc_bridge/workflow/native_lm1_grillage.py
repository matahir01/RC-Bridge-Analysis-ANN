from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_effects import NativeGrillageEnvelopeResult, native_grillage_traffic_envelope
from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult, solve_vertical_grillage
from rc_bridge.codes.eurocode.en1991_2 import LM1AdjustmentFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.export.model_verification_package import (
    ModelVerificationExportPackage,
    build_model_verification_export_package,
)
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1RemainingAreaVerificationPlacement,
    build_project_lm1_grillage_verification_model,
)


@dataclass(frozen=True)
class ProjectNativeLM1GrillageSnapshotResult:
    """One explicit LM1 grillage snapshot solved internally and exportable unchanged."""

    model: VerificationModel
    analysis: GrillageAnalysisResult
    girder_envelope: NativeGrillageEnvelopeResult
    verification_package: ModelVerificationExportPackage

    @property
    def girder_count(self) -> int:
        return self.girder_envelope.envelope.girder_count


def run_project_native_lm1_grillage_snapshot(
    project: ProjectInput,
    *,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...],
    transverse_section: GrillageSectionProperties,
    transverse_stations_m: tuple[float, ...],
    lane_placements: tuple[LM1LaneVerificationPlacement, ...],
    remaining_area_placements: tuple[LM1RemainingAreaVerificationPlacement, ...] = (),
    factors: LM1AdjustmentFactors | None = None,
    name: str = "EN 1991-2 LM1 native grillage snapshot",
) -> ProjectNativeLM1GrillageSnapshotResult:
    """Build, solve and export exactly one explicit LM1 grillage placement.

    The function deliberately does not claim that one supplied placement is the
    governing traffic configuration. It solves the explicit snapshot only. A
    separate placement/envelope search must establish governing LM1 effects before
    this result can be treated as the characteristic traffic action for design.

    The MIDAS/STAAD verification package is generated from the exact same model
    object passed to the native solver, enabling direct model-for-model validation.
    """
    model = build_project_lm1_grillage_verification_model(
        project,
        longitudinal_sections_by_span=longitudinal_sections_by_span,
        transverse_section=transverse_section,
        transverse_stations_m=transverse_stations_m,
        lane_placements=lane_placements,
        remaining_area_placements=remaining_area_placements,
        factors=factors,
        name=name,
    )
    analysis = solve_vertical_grillage(model)
    girder_envelope = native_grillage_traffic_envelope(model, analysis)
    verification_package = build_model_verification_export_package(model)
    return ProjectNativeLM1GrillageSnapshotResult(
        model=model,
        analysis=analysis,
        girder_envelope=girder_envelope,
        verification_package=verification_package,
    )
