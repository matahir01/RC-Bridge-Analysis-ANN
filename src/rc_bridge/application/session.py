from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rc_bridge.application.dashboard import (
    ApplicationDashboard,
    build_application_dashboard,
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

    def set_preferences(self, preferences: ApplicationPreferences) -> None:
        if preferences.analysis != self.preferences.analysis:
            self.last_lm1_search = None
        self.preferences = preferences

    def dashboard(self) -> ApplicationDashboard:
        return build_application_dashboard(
            self.project,
            has_native_lm1_analysis=self.last_lm1_search is not None,
        )

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
