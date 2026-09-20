from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rc_bridge.application.session import BridgeApplicationSession

APPLICATION_INTERFACE_VERSION = "1.0"
ENGINE_INTERFACE_VERSION = "1.0"

FROZEN_ENGINE_ENTRYPOINTS: tuple[str, ...] = (
    "rc_bridge.workflow.lm1_grillage_search:run_project_native_lm1_grillage_search",
    "rc_bridge.application.extended_actions:run_extended_actions",
    "rc_bridge.application.local_deck:run_local_deck_design",
    "rc_bridge.application.design_checks:run_application_design_interpretation",
    "rc_bridge.application.fatigue:run_application_fatigue",
    "rc_bridge.application.verification_campaign:build_unified_final_service_verification_model",
)

# These names are the application-facing contract consumed by the desktop UI and
# other presentation layers. New internal engine methods can be added freely; removing
# or changing one of these operations requires an explicit interface-version change.
FROZEN_SESSION_OPERATIONS: tuple[str, ...] = (
    "replace_project",
    "set_preferences",
    "save",
    "run_native_lm1",
    "run_extended_actions",
    "run_local_deck_design",
    "run_design_interpretation",
    "run_fatigue",
    "calculation_trace",
    "write_last_lm1_report",
    "write_last_lm1_pdf_report",
    "export_verification_campaign",
    "build_stage5_verification_model",
    "import_stage5_staad_anl",
    "import_stage5_midas_tables",
    "write_last_verification_evidence",
)

FROZEN_SESSION_STATE: tuple[str, ...] = (
    "project",
    "preferences",
    "project_path",
    "last_lm1_search",
    "last_extended_actions",
    "last_local_deck_design",
    "last_action_combinations",
    "last_design_interpretation",
    "last_fatigue",
    "last_verification_import",
    "last_performance_record",
)


@dataclass(frozen=True)
class WorkflowStageView:
    key: str
    title: str
    state: str
    detail: str

    def __post_init__(self) -> None:
        if self.state not in {"ready", "complete", "pending", "review"}:
            raise ValueError(f"Unsupported workflow stage state: {self.state}")


@dataclass(frozen=True)
class ApplicationViewSnapshot:
    interface_version: str
    project_name: str
    project_subtitle: str
    stages: tuple[WorkflowStageView, ...]
    calculation_trace_available: bool
    verification_summary: str
    design_blocker_count: int
    last_operation: str
    last_operation_detail: str

    @property
    def completed_stage_count(self) -> int:
        return sum(stage.state == "complete" for stage in self.stages)

    @property
    def total_stage_count(self) -> int:
        return len(self.stages)


def validate_engine_interface() -> None:
    """Assert that the deterministic entry points frozen for presentation still exist."""

    missing: list[str] = []
    for entrypoint in FROZEN_ENGINE_ENTRYPOINTS:
        module_name, attribute_name = entrypoint.split(":", 1)
        module = import_module(module_name)
        if not hasattr(module, attribute_name):
            missing.append(entrypoint)
    if missing:
        raise TypeError(
            "Deterministic engine does not satisfy interface "
            f"{ENGINE_INTERFACE_VERSION}; missing: {', '.join(missing)}"
        )


def validate_application_interface(session: Any) -> None:
    """Fail early when a presentation layer receives an incompatible application API."""

    missing = [
        name
        for name in (*FROZEN_SESSION_OPERATIONS, *FROZEN_SESSION_STATE)
        if not hasattr(session, name)
    ]
    if missing:
        raise TypeError(
            "Application session does not satisfy desktop interface "
            f"{APPLICATION_INTERFACE_VERSION}; missing: {', '.join(missing)}"
        )


def build_application_view_snapshot(
    session: BridgeApplicationSession,
) -> ApplicationViewSnapshot:
    """Return a stable, presentation-ready view of the mutable application session."""

    validate_application_interface(session)
    project = session.project
    geometry = project.geometry
    profile_complete = geometry.girder_profile is not None

    design_blockers = (
        ()
        if session.last_design_interpretation is None
        else session.last_design_interpretation.coverage_blockers
    )
    verification = session.last_verification_import
    if verification is None:
        verification_summary = "No external Stage-5 result import yet."
        verification_state = "pending"
    else:
        verification_state = "review"
        imported = len(verification.result_sets)
        requested = len(verification.requested_result_ids)
        import_status = (
            "COMPLETE" if verification.import_complete else "INCOMPLETE"
        )
        numerical_status = (
            "PASS" if verification.numerical_agreement_passes else "FAIL / REVIEW"
        )
        envelope_status = verification.envelope_comparison_passes
        envelope_text = (
            "not run"
            if envelope_status is None
            else ("PASS" if envelope_status else "FAIL / REVIEW")
        )
        combination_envelope_status = getattr(
            verification,
            "combination_envelope_comparison_passes",
            None,
        )
        combination_envelope_text = (
            "not run"
            if combination_envelope_status is None
            else ("PASS" if combination_envelope_status else "FAIL / REVIEW")
        )
        verification_summary = (
            f"{verification.source_name}: import {import_status} "
            f"({imported}/{requested}); detailed numerical agreement "
            f"{'PASS' if verification.detailed_comparisons_pass else 'FAIL / REVIEW'}; "
            f"engineering envelope {envelope_text}; combination envelope "
            f"{combination_envelope_text}; overall numerical {numerical_status}. "
            "Engineering acceptance remains PENDING model/source-equivalence review."
        )

    stages = (
        WorkflowStageView(
            "project",
            "Project model",
            "complete" if profile_complete else "ready",
            (
                f"{len(geometry.span_lengths_m)} span(s), "
                f"{geometry.girder_count} girders @ {geometry.girder_spacing_m:g} m"
                if profile_complete
                else "Complete geometry and a physical girder profile."
            ),
        ),
        WorkflowStageView(
            "analysis",
            "LM1 analysis",
            "complete" if session.last_lm1_search is not None else "pending",
            (
                "Native governing traffic envelopes available."
                if session.last_lm1_search is not None
                else "Run native LM1 after defining the project."
            ),
        ),
        WorkflowStageView(
            "actions",
            "Additional actions",
            "complete" if session.last_extended_actions is not None else "pending",
            (
                "Braking, thermal, LM2, pedestrian, wind and construction scope evaluated."
                if session.last_extended_actions is not None
                else "Run the additional-action suite after LM1."
            ),
        ),
        WorkflowStageView(
            "deck",
            "Deck design",
            "complete" if session.last_local_deck_design is not None else "pending",
            (
                "Local deck flexure/shear design available."
                if session.last_local_deck_design is not None
                else "Run local deck/slab checks."
            ),
        ),
        WorkflowStageView(
            "design",
            "Girder design",
            (
                "review"
                if session.last_design_interpretation is not None and design_blockers
                else (
                    "complete"
                    if session.last_design_interpretation is not None
                    else "pending"
                )
            ),
            (
                (
                    f"Design calculated with {len(design_blockers)} explicit blocker(s)."
                    if design_blockers
                    else "Integrated ULS/SLS girder design available."
                )
                if session.last_design_interpretation is not None
                else "Run integrated design and detailing checks."
            ),
        ),
        WorkflowStageView(
            "fatigue",
            "FLM3 fatigue",
            (
                "review"
                if session.last_fatigue is not None and session.last_fatigue.blockers
                else ("complete" if session.last_fatigue is not None else "pending")
            ),
            (
                (
                    f"Fatigue analysis has {len(session.last_fatigue.blockers)} "
                    "explicit input blocker(s)."
                    if session.last_fatigue.blockers
                    else "Native FLM3 fatigue checks available."
                )
                if session.last_fatigue is not None
                else "Run fatigue after the design cage is available."
            ),
        ),
        WorkflowStageView(
            "verification",
            "External verification",
            verification_state,
            verification_summary,
        ),
    )

    last_record = session.last_performance_record
    if last_record is None:
        last_operation = "No timed operation yet"
        last_operation_detail = "Run an analysis or report operation to populate diagnostics."
    else:
        last_operation = last_record.operation.replace("_", " ").title()
        if last_record.cache_hit:
            last_operation_detail = "Reused unchanged session result from cache."
        else:
            last_operation_detail = f"Completed in {last_record.duration_s:.3f} s."
        if last_record.detail:
            last_operation_detail += f" {last_record.detail}"

    spans = " + ".join(f"{float(value):g} m" for value in geometry.span_lengths_m)
    subtitle = (
        f"{project.design_code.value} · {geometry.support_system.value} · "
        f"{spans} · deck {geometry.deck_width_m:g} m"
    )
    return ApplicationViewSnapshot(
        interface_version=APPLICATION_INTERFACE_VERSION,
        project_name=project.name,
        project_subtitle=subtitle,
        stages=stages,
        calculation_trace_available=session.last_lm1_search is not None,
        verification_summary=verification_summary,
        design_blocker_count=len(design_blockers),
        last_operation=last_operation,
        last_operation_detail=last_operation_detail,
    )
