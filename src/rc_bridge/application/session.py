from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rc_bridge.application.action_combinations import (
    BridgeActionCombinationFactors,
    IntegratedActionCombinationSuite,
    build_integrated_action_combinations,
)
from rc_bridge.application.calculation_trace import (
    CalculationTrace,
    build_application_calculation_trace,
)
from rc_bridge.application.dashboard import (
    ApplicationDashboard,
    build_application_dashboard,
)
from rc_bridge.application.design_checks import (
    ApplicationDesignInterpretationSuite,
    run_application_design_interpretation,
)
from rc_bridge.application.extended_actions import (
    ExtendedActionSuite,
    run_extended_actions,
)
from rc_bridge.application.fatigue import (
    FatigueApplicationResult,
    run_application_fatigue,
)
from rc_bridge.application.load_cases import (
    ApplicationGirderCombinationSummary,
    ApplicationLoadCaseFields,
    PermanentGirderLoadAudit,
    application_combination_summary,
    permanent_load_audit,
)
from rc_bridge.application.local_deck import (
    LocalDeckDesignResult,
    run_local_deck_design,
)
from rc_bridge.application.performance import (
    ApplicationPerformanceRecord,
    cache_hit_record,
    timed_call,
)
from rc_bridge.application.preferences import ApplicationPreferences
from rc_bridge.application.project_io import load_project_document, save_project
from rc_bridge.application.reporting import (
    application_html_report,
    write_native_lm1_pdf_report,
)
from rc_bridge.application.verification_campaign import (
    WrittenVerificationCampaign,
    build_unified_final_service_verification_model,
    write_application_verification_campaign,
)
from rc_bridge.application.verification_files import (
    WrittenConsolidatedVerificationFiles,
    WrittenVerificationPackage,
    write_consolidated_governing_lm1_verification_files,
    write_governing_lm1_verification_packages,
)
from rc_bridge.application.verification_import import (
    ApplicationVerificationImportReport,
    VerificationImportTolerance,
    WrittenVerificationImportEvidence,
    import_midas_table_verification_results,
    import_staad_anl_verification_results,
    write_verification_import_evidence,
)
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    run_project_native_lm1_grillage_search,
)


def longitudinal_grid_stations(
    project: ProjectInput,
    *,
    maximum_spacing_m: float,
) -> tuple[float, ...]:
    """Create an application grid that always retains every physical support line."""
    if maximum_spacing_m <= 0.0:
        raise ValueError("maximum_spacing_m must be positive.")

    supports = [0.0]
    for span in project.geometry.span_lengths_m:
        supports.append(supports[-1] + float(span))
    total_length = supports[-1]

    values = {round(value, 12) for value in supports}
    position = 0.0
    while position < total_length - 1.0e-12:
        values.add(round(position, 12))
        position += maximum_spacing_m
    values.add(round(total_length, 12))
    return tuple(sorted(values))


@dataclass
class BridgeApplicationSession:
    """Mutable desktop/CLI application state around immutable validated inputs/results."""

    project: ProjectInput
    project_path: Path | None = None
    preferences: ApplicationPreferences = field(default_factory=ApplicationPreferences)
    last_lm1_search: ProjectNativeLM1GrillageSearchResult | None = None
    last_design_interpretation: ApplicationDesignInterpretationSuite | None = None
    last_extended_actions: ExtendedActionSuite | None = None
    last_action_combinations: IntegratedActionCombinationSuite | None = None
    last_local_deck_design: LocalDeckDesignResult | None = None
    last_fatigue: FatigueApplicationResult | None = None
    last_verification_import: ApplicationVerificationImportReport | None = None
    performance_history: list[ApplicationPerformanceRecord] = field(default_factory=list)
    _permanent_load_audit_cache: tuple[PermanentGirderLoadAudit, ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _combination_summary_cache: tuple[ApplicationGirderCombinationSummary, ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _calculation_trace_cache: CalculationTrace | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _last_lm1_run_key: tuple[float, float, int] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def _record_performance(self, record: ApplicationPerformanceRecord) -> None:
        self.performance_history.append(record)
        if len(self.performance_history) > 100:
            del self.performance_history[:-100]

    @property
    def last_performance_record(self) -> ApplicationPerformanceRecord | None:
        return self.performance_history[-1] if self.performance_history else None

    def _invalidate_derived_caches(self) -> None:
        self._permanent_load_audit_cache = None
        self._combination_summary_cache = None
        self._calculation_trace_cache = None

    @classmethod
    def open(cls, path: str | Path) -> BridgeApplicationSession:
        source = Path(path)
        document = load_project_document(source)
        return cls(
            project=document.project,
            project_path=source,
            preferences=document.application_preferences,
        )

    def save(self, path: str | Path | None = None) -> Path:
        destination = self.project_path if path is None else Path(path)
        if destination is None:
            raise ValueError("A project path is required for the first save.")
        written = save_project(
            self.project,
            destination,
            application_preferences=self.preferences,
        )
        self.project_path = written
        return written

    def replace_project(self, project: ProjectInput) -> None:
        self.project = project
        self.last_lm1_search = None
        self.last_design_interpretation = None
        self.last_extended_actions = None
        self.last_action_combinations = None
        self.last_local_deck_design = None
        self.last_fatigue = None
        self.last_verification_import = None
        self._last_lm1_run_key = None
        self.performance_history.clear()
        self._invalidate_derived_caches()

    def set_preferences(self, preferences: ApplicationPreferences) -> None:
        if preferences.analysis != self.preferences.analysis:
            self.last_lm1_search = None
            self._last_lm1_run_key = None
            self.last_extended_actions = None
            self.last_local_deck_design = None
            self.last_action_combinations = None
            self.last_design_interpretation = None
            self.last_fatigue = None
            self.last_verification_import = None
        elif preferences.actions != self.preferences.actions:
            self.last_extended_actions = None
            self.last_local_deck_design = None
            self.last_action_combinations = None
            self.last_design_interpretation = None
            self.last_fatigue = None
            self.last_verification_import = None
        elif (
            preferences.local_deck != self.preferences.local_deck
            or preferences.eurocode != self.preferences.eurocode
            or preferences.design != self.preferences.design
        ):
            self.last_local_deck_design = None
            self.last_action_combinations = None
            self.last_design_interpretation = None
            self.last_fatigue = None
            self.last_verification_import = None
        elif preferences.fatigue != self.preferences.fatigue:
            self.last_fatigue = None
            self.last_verification_import = None
        if preferences != self.preferences:
            self._combination_summary_cache = None
            self._calculation_trace_cache = None
        self.preferences = preferences

    def dashboard(self) -> ApplicationDashboard:
        return build_application_dashboard(
            self.project,
            has_native_lm1_analysis=self.last_lm1_search is not None,
            has_extended_actions=self.last_extended_actions is not None,
            has_integrated_design=self.last_design_interpretation is not None,
            has_local_deck_design=self.last_local_deck_design is not None,
            has_fatigue=self.last_fatigue is not None,
            design_blocker_count=(
                0
                if self.last_design_interpretation is None
                else len(self.last_design_interpretation.coverage_blockers)
            ),
        )

    def load_case_fields(self) -> ApplicationLoadCaseFields:
        return ApplicationLoadCaseFields.from_project(self.project)

    def apply_load_case_fields(self, fields: ApplicationLoadCaseFields) -> None:
        updated = fields.apply(self.project)
        if updated != self.project:
            self.replace_project(updated)

    def permanent_load_audit(self) -> tuple[PermanentGirderLoadAudit, ...]:
        if self._permanent_load_audit_cache is not None:
            self._record_performance(
                cache_hit_record("permanent_load_audit", detail="session cache")
            )
            return self._permanent_load_audit_cache
        result, record = timed_call(
            "permanent_load_audit",
            lambda: permanent_load_audit(self.project),
        )
        self._permanent_load_audit_cache = result
        self._record_performance(record)
        return result

    def combination_summary(self) -> tuple[ApplicationGirderCombinationSummary, ...]:
        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before generating load combinations."
            )
        if self._combination_summary_cache is not None:
            self._record_performance(
                cache_hit_record("combination_summary", detail="session cache")
            )
            return self._combination_summary_cache
        result, record = timed_call(
            "combination_summary",
            lambda: application_combination_summary(
                self.project,
                self.last_lm1_search,
                uls_factors=self.preferences.eurocode.uls_factors,
                sls_factors=self.preferences.eurocode.sls_factors,
            ),
        )
        self._combination_summary_cache = result
        self._record_performance(record)
        return result

    def run_extended_actions(
        self,
        *,
        lm2_progress_callback: Callable[[int, int], None] | None = None,
        gr2_progress_callback: Callable[[int, int], None] | None = None,
    ) -> ExtendedActionSuite:
        if self.last_extended_actions is not None:
            self._record_performance(
                cache_hit_record("extended_actions", detail="unchanged project/settings")
            )
            return self.last_extended_actions
        analysis = self.preferences.analysis
        result, record = timed_call(
            "extended_actions",
            lambda: run_extended_actions(
                self.project,
                self.preferences.actions,
                grid_spacing_m=analysis.grid_spacing_m,
                traffic_step_m=analysis.traffic_step_m,
                max_exhaustive_tandem_combinations=(
                    analysis.max_exhaustive_tandem_combinations
                ),
                lm2_progress_callback=lm2_progress_callback,
                gr2_progress_callback=gr2_progress_callback,
            ),
        )
        self._record_performance(record)
        self.last_extended_actions = result
        self.last_local_deck_design = None
        self.last_action_combinations = None
        self.last_design_interpretation = None
        self.last_fatigue = None
        self._calculation_trace_cache = None
        return result

    def run_local_deck_design(self) -> LocalDeckDesignResult:
        if self.last_local_deck_design is not None:
            self._record_performance(
                cache_hit_record("local_deck_design", detail="unchanged project/settings")
            )
            return self.last_local_deck_design
        if self.last_extended_actions is None:
            raise RuntimeError(
                "Run Additional actions before local deck design so LM2 and "
                "barrier-impact wheel actions are available."
            )
        basis = self.preferences.eurocode
        result, record = timed_call(
            "local_deck_design",
            lambda: run_local_deck_design(
                self.project,
                self.last_extended_actions,
                action_settings=self.preferences.actions,
                settings=self.preferences.local_deck,
                cover_mm=self.preferences.design.cover_mm,
                gamma_g=basis.gamma_g_unfavourable,
                gamma_q_traffic=basis.gamma_q_traffic,
            ),
        )
        self._record_performance(record)
        self.last_local_deck_design = result
        self.last_action_combinations = None
        self.last_design_interpretation = None
        self.last_fatigue = None
        self._calculation_trace_cache = None
        return result

    def run_design_interpretation(self) -> ApplicationDesignInterpretationSuite:
        if self.last_design_interpretation is not None:
            self._record_performance(
                cache_hit_record("design_interpretation", detail="unchanged project/settings")
            )
            return self.last_design_interpretation
        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before running the design interpretation."
            )
        if self.last_extended_actions is None:
            raise RuntimeError(
                "Run Additional actions before design so LM2, pedestrian, braking, "
                "thermal, wind, barrier and construction actions cannot be silently omitted."
            )
        if self.last_local_deck_design is None:
            self.run_local_deck_design()
        basis = self.preferences.eurocode
        factors = BridgeActionCombinationFactors(
            uls=basis.uls_factors,
            gamma_q_nontraffic=basis.gamma_q_nontraffic,
            psi1_lm2=basis.psi1_lm2,
            psi0_thermal_uls=basis.psi0_thermal_uls,
            psi0_thermal_sls=basis.psi0_thermal_sls,
            psi1_thermal=basis.psi1_thermal,
            psi2_thermal=basis.psi2_thermal,
        )
        combinations = build_integrated_action_combinations(
            self.project,
            self.last_lm1_search,
            self.last_extended_actions,
            settings=self.preferences.actions,
            factors=factors,
            local_deck=self.last_local_deck_design,
        )
        result, record = timed_call(
            "design_interpretation",
            lambda: run_application_design_interpretation(
                self.project,
                self.last_lm1_search,
                uls_factors=basis.uls_factors,
                sls_factors=basis.sls_factors,
                crack_limit_mm=basis.crack_limit_mm,
                deflection_limit_span_ratio=basis.deflection_limit_span_ratio,
                settings=self.preferences.design,
                action_combinations=combinations,
                extended_actions=self.last_extended_actions,
                gamma_q_nontraffic=basis.gamma_q_nontraffic,
            ),
        )
        self._record_performance(record)
        self.last_action_combinations = combinations
        self.last_design_interpretation = result
        self.last_fatigue = None
        self._calculation_trace_cache = None
        return result

    def run_fatigue(self) -> FatigueApplicationResult:
        if self.last_fatigue is not None:
            self._record_performance(
                cache_hit_record("fatigue", detail="unchanged project/settings")
            )
            return self.last_fatigue
        if self.last_design_interpretation is None:
            raise RuntimeError(
                "Run the integrated Design & checks workflow before FLM3 fatigue."
            )
        stations = longitudinal_grid_stations(
            self.project,
            maximum_spacing_m=self.preferences.analysis.grid_spacing_m,
        )
        result, record = timed_call(
            "fatigue",
            lambda: run_application_fatigue(
                self.project,
                self.last_design_interpretation,
                settings=self.preferences.fatigue,
                transverse_stations_m=stations,
            ),
        )
        self._record_performance(record)
        self.last_fatigue = result
        self._calculation_trace_cache = None
        return result

    def run_native_lm1(
        self,
        *,
        grid_spacing_m: float | None = None,
        longitudinal_step_m: float | None = None,
        max_exhaustive_tandem_combinations: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> ProjectNativeLM1GrillageSearchResult:
        if self.project.geometry.girder_profile is None:
            raise ValueError(
                "Application analysis requires a complete physical rectangular, T or I "
                "girder profile so grillage properties can be derived transparently."
            )

        settings = self.preferences.analysis
        grid_spacing = settings.grid_spacing_m if grid_spacing_m is None else grid_spacing_m
        traffic_step = (
            settings.traffic_step_m
            if longitudinal_step_m is None
            else longitudinal_step_m
        )
        max_tandem = (
            settings.max_exhaustive_tandem_combinations
            if max_exhaustive_tandem_combinations is None
            else max_exhaustive_tandem_combinations
        )
        if max_tandem <= 0:
            raise ValueError("max_exhaustive_tandem_combinations must be positive.")

        run_key = (float(grid_spacing), float(traffic_step), int(max_tandem))
        if self.last_lm1_search is not None and self._last_lm1_run_key == run_key:
            self._record_performance(
                cache_hit_record("native_lm1", detail="unchanged project/settings")
            )
            return self.last_lm1_search

        stations = longitudinal_grid_stations(
            self.project,
            maximum_spacing_m=grid_spacing,
        )
        result, record = timed_call(
            "native_lm1",
            lambda: run_project_native_lm1_grillage_search(
                self.project,
                transverse_stations_m=stations,
                longitudinal_step_m=traffic_step,
                max_exhaustive_tandem_combinations=max_tandem,
                include_spanwise_udl_patterns=True,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
                retain_all_cases=False,
                name=f"{self.project.name} - application native LM1",
            ),
        )
        self._record_performance(record)
        self.last_lm1_search = result
        self._last_lm1_run_key = run_key
        self.last_local_deck_design = None
        self.last_action_combinations = None
        self.last_design_interpretation = None
        self.last_fatigue = None
        self._combination_summary_cache = None
        self._calculation_trace_cache = None
        return result

    def calculation_trace(self) -> CalculationTrace:
        if self.last_lm1_search is None:
            raise RuntimeError("Run native LM1 analysis before building calculation traces.")
        if self._calculation_trace_cache is not None:
            self._record_performance(
                cache_hit_record("calculation_trace", detail="session cache")
            )
            return self._calculation_trace_cache
        trace, record = timed_call(
            "calculation_trace",
            lambda: build_application_calculation_trace(
                self.project,
                self.last_lm1_search,
                preferences=self.preferences,
                local_deck_design=self.last_local_deck_design,
                design_interpretation=self.last_design_interpretation,
                fatigue=self.last_fatigue,
            ),
        )
        self._calculation_trace_cache = trace
        self._record_performance(record)
        return trace

    def write_last_lm1_report(self, path: str | Path) -> Path:
        if self.last_lm1_search is None:
            raise RuntimeError("Run native LM1 analysis before generating a report.")
        destination = Path(path)
        if destination.suffix.lower() not in {".html", ".htm"}:
            raise ValueError("Application calculation report must use .html or .htm.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            application_html_report(
                self.project,
                self.last_lm1_search,
                preferences=self.preferences,
                extended_actions=self.last_extended_actions,
                local_deck_design=self.last_local_deck_design,
                design_interpretation=self.last_design_interpretation,
                fatigue=self.last_fatigue,
                calculation_trace=self.calculation_trace(),
            ),
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    def write_last_lm1_pdf_report(self, path: str | Path) -> Path:
        if self.last_lm1_search is None:
            raise RuntimeError("Run native LM1 analysis before generating a PDF report.")
        return write_native_lm1_pdf_report(
            self.project,
            self.last_lm1_search,
            path,
            preferences=self.preferences,
            extended_actions=self.last_extended_actions,
            local_deck_design=self.last_local_deck_design,
            design_interpretation=self.last_design_interpretation,
            fatigue=self.last_fatigue,
            calculation_trace=self.calculation_trace(),
        )


    def _verification_combination_factors(self) -> BridgeActionCombinationFactors:
        basis = self.preferences.eurocode
        return BridgeActionCombinationFactors(
            uls=basis.uls_factors,
            gamma_q_nontraffic=basis.gamma_q_nontraffic,
            psi1_lm2=basis.psi1_lm2,
            psi0_thermal_uls=basis.psi0_thermal_uls,
            psi0_thermal_sls=basis.psi0_thermal_sls,
            psi1_thermal=basis.psi1_thermal,
            psi2_thermal=basis.psi2_thermal,
        )

    def build_stage5_verification_model(self):
        if self.last_lm1_search is None:
            raise RuntimeError("Run native LM1 analysis before Stage-5 verification.")
        if self.last_extended_actions is None:
            raise RuntimeError(
                "Run Additional actions before Stage-5 verification."
            )
        if self.last_action_combinations is None:
            raise RuntimeError(
                "Run integrated Design & checks before Stage-5 verification."
            )
        return build_unified_final_service_verification_model(
            self.project,
            self.last_lm1_search,
            self.last_extended_actions,
            action_settings=self.preferences.actions,
            combination_factors=self._verification_combination_factors(),
            grid_spacing_m=self.preferences.analysis.grid_spacing_m,
        )

    def import_stage5_staad_anl(
        self,
        path: str | Path,
        *,
        tolerance: VerificationImportTolerance | None = None,
    ) -> ApplicationVerificationImportReport:
        source = Path(path)
        model = self.build_stage5_verification_model()
        report = import_staad_anl_verification_results(
            model,
            staad_anl_text=source.read_text(encoding="utf-8", errors="replace"),
            source_name="STAAD.Pro",
            tolerance=tolerance,
        )
        self.last_verification_import = report
        return report

    def import_stage5_midas_tables(
        self,
        *,
        reaction_path: str | Path,
        displacement_path: str | Path,
        member_force_path: str | Path,
        delimiter: str = ",",
        tolerance: VerificationImportTolerance | None = None,
    ) -> ApplicationVerificationImportReport:
        model = self.build_stage5_verification_model()
        report = import_midas_table_verification_results(
            model,
            reaction_table=Path(reaction_path).read_text(
                encoding="utf-8",
                errors="replace",
            ),
            displacement_table=Path(displacement_path).read_text(
                encoding="utf-8",
                errors="replace",
            ),
            member_force_table=Path(member_force_path).read_text(
                encoding="utf-8",
                errors="replace",
            ),
            source_name="MIDAS Civil",
            delimiter=delimiter,
            tolerance=tolerance,
        )
        self.last_verification_import = report
        return report

    def write_last_verification_evidence(
        self,
        directory: str | Path,
        *,
        base_name: str = "stage5_external_verification",
    ) -> WrittenVerificationImportEvidence:
        if self.last_verification_import is None:
            raise RuntimeError(
                "Import STAAD/MIDAS Stage-5 results before saving verification evidence."
            )
        return write_verification_import_evidence(
            self.last_verification_import,
            directory,
            base_name=base_name,
        )

    def export_verification_campaign(
        self,
        directory: str | Path,
        *,
        base_name: str = "application_verification",
    ) -> WrittenVerificationCampaign:
        """Export the complete available Stage-7 MIDAS/STAAD verification campaign."""

        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before exporting the verification campaign."
            )
        if self.last_extended_actions is None:
            raise RuntimeError(
                "Run Additional actions before export so gr2, LM2, pedestrian, wind, "
                "braking, thermal, barrier and construction actions are not omitted."
            )
        if self.last_local_deck_design is None:
            raise RuntimeError(
                "Run local deck design before export so local LM2/barrier results are recorded."
            )
        if self.last_action_combinations is None or self.last_design_interpretation is None:
            raise RuntimeError(
                "Run integrated Design & checks before export so compatible traffic groups "
                "and ULS/SLS combination summaries are included."
            )
        if self.last_fatigue is None:
            raise RuntimeError(
                "Run FLM3 fatigue before export so governing fatigue vehicle cases are included."
            )
        combination_factors = self._verification_combination_factors()
        return write_application_verification_campaign(
            self.project,
            self.last_lm1_search,
            directory,
            extended_actions=self.last_extended_actions,
            action_settings=self.preferences.actions,
            combination_factors=combination_factors,
            action_combinations=self.last_action_combinations,
            local_deck=self.last_local_deck_design,
            fatigue=self.last_fatigue,
            grid_spacing_m=self.preferences.analysis.grid_spacing_m,
            base_name=base_name,
        )

    def export_last_lm1_verification(
        self,
        directory: str | Path,
        *,
        base_name: str = "lm1_governing",
    ) -> WrittenConsolidatedVerificationFiles:
        """Write one MIDAS and one STAAD file containing all governing LM1 cases."""

        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before exporting governing verification models."
            )
        return write_consolidated_governing_lm1_verification_files(
            self.project,
            self.last_lm1_search,
            directory,
            base_name=base_name,
        )

    def export_last_lm1_verification_packages(
        self,
        directory: str | Path,
        *,
        base_name: str = "lm1_governing",
    ) -> tuple[WrittenVerificationPackage, ...]:
        """Write legacy one-folder-per-case packages for detailed/debug inspection."""

        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before exporting governing verification models."
            )
        return write_governing_lm1_verification_packages(
            self.last_lm1_search,
            directory,
            base_name=base_name,
        )
