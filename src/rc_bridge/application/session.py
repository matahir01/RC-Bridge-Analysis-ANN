from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rc_bridge.application.action_combinations import (
    BridgeActionCombinationFactors,
    IntegratedActionCombinationSuite,
    build_integrated_action_combinations,
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
from rc_bridge.application.load_cases import (
    ApplicationGirderCombinationSummary,
    ApplicationLoadCaseFields,
    PermanentGirderLoadAudit,
    application_combination_summary,
    permanent_load_audit,
)
from rc_bridge.application.preferences import ApplicationPreferences
from rc_bridge.application.project_io import load_project_document, save_project
from rc_bridge.application.reporting import (
    application_html_report,
    write_native_lm1_pdf_report,
)
from rc_bridge.application.verification_files import (
    WrittenConsolidatedVerificationFiles,
    WrittenVerificationPackage,
    write_consolidated_governing_lm1_verification_files,
    write_governing_lm1_verification_packages,
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

    def set_preferences(self, preferences: ApplicationPreferences) -> None:
        if preferences.analysis != self.preferences.analysis:
            self.last_lm1_search = None
            self.last_design_interpretation = None
            self.last_extended_actions = None
            self.last_action_combinations = None
        elif preferences.actions != self.preferences.actions:
            self.last_extended_actions = None
            self.last_action_combinations = None
            self.last_design_interpretation = None
        elif (
            preferences.eurocode != self.preferences.eurocode
            or preferences.design != self.preferences.design
        ):
            self.last_design_interpretation = None
            self.last_action_combinations = None
        self.preferences = preferences

    def dashboard(self) -> ApplicationDashboard:
        return build_application_dashboard(
            self.project,
            has_native_lm1_analysis=self.last_lm1_search is not None,
            has_extended_actions=self.last_extended_actions is not None,
            has_integrated_design=self.last_design_interpretation is not None,
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
        return permanent_load_audit(self.project)

    def combination_summary(self) -> tuple[ApplicationGirderCombinationSummary, ...]:
        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before generating load combinations."
            )
        return application_combination_summary(
            self.project,
            self.last_lm1_search,
            uls_factors=self.preferences.eurocode.uls_factors,
            sls_factors=self.preferences.eurocode.sls_factors,
        )

    def run_extended_actions(
        self,
        *,
        lm2_progress_callback: Callable[[int, int], None] | None = None,
        gr2_progress_callback: Callable[[int, int], None] | None = None,
    ) -> ExtendedActionSuite:
        analysis = self.preferences.analysis
        result = run_extended_actions(
            self.project,
            self.preferences.actions,
            grid_spacing_m=analysis.grid_spacing_m,
            traffic_step_m=analysis.traffic_step_m,
            max_exhaustive_tandem_combinations=(
                analysis.max_exhaustive_tandem_combinations
            ),
            lm2_progress_callback=lm2_progress_callback,
            gr2_progress_callback=gr2_progress_callback,
        )
        self.last_extended_actions = result
        self.last_action_combinations = None
        self.last_design_interpretation = None
        return result

    def run_design_interpretation(self) -> ApplicationDesignInterpretationSuite:
        if self.last_lm1_search is None:
            raise RuntimeError(
                "Run native LM1 analysis before running the design interpretation."
            )
        if self.last_extended_actions is None:
            raise RuntimeError(
                "Run Additional actions 1-6 before design so LM2, pedestrian, "
                "braking, thermal, barrier and construction actions cannot be "
                "silently omitted."
            )
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
        )
        result = run_application_design_interpretation(
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
        )
        self.last_action_combinations = combinations
        self.last_design_interpretation = result
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

        stations = longitudinal_grid_stations(
            self.project,
            maximum_spacing_m=grid_spacing,
        )
        result = run_project_native_lm1_grillage_search(
            self.project,
            transverse_stations_m=stations,
            longitudinal_step_m=traffic_step,
            max_exhaustive_tandem_combinations=max_tandem,
            include_spanwise_udl_patterns=True,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            retain_all_cases=False,
            name=f"{self.project.name} - application native LM1",
        )
        self.last_lm1_search = result
        self.last_action_combinations = None
        self.last_design_interpretation = None
        return result

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
