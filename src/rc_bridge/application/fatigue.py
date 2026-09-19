from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.application.design_checks import ApplicationDesignInterpretationSuite
from rc_bridge.application.session_types import ApplicationAnalysisGrid
from rc_bridge.core.models import ProjectInput, SupportSystem
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3LayeredGirderFatigueResult,
    ProjectNativeFLM3GrillageSearchResult,
    run_project_layered_girder_fatigue_from_native_flm3,
    run_project_native_flm3_grillage_search,
)


@dataclass(frozen=True)
class FatigueApplicationSettings:
    movement_step_m: float = 0.5
    section_step_m: float = 0.5
    axle_load_factor: float = 1.0
    lambda_s: float = 0.0
    characteristic_fatigue_strength_mpa: float = 0.0
    gamma_s_fat: float = 1.15
    phi_fat: float = 1.0
    check_concrete: bool = True
    shear_link_characteristic_fatigue_strength_mpa: float = 0.0
    shear_link_lambda_s: float = 0.0
    shear_link_phi_fat: float = 1.0

    def __post_init__(self) -> None:
        if min(
            self.movement_step_m,
            self.section_step_m,
            self.axle_load_factor,
            self.gamma_s_fat,
            self.phi_fat,
            self.shear_link_phi_fat,
        ) <= 0.0:
            raise ValueError("Fatigue search/factor settings must be positive.")
        if min(
            self.lambda_s,
            self.characteristic_fatigue_strength_mpa,
            self.shear_link_characteristic_fatigue_strength_mpa,
            self.shear_link_lambda_s,
        ) < 0.0:
            raise ValueError("Fatigue resistance inputs cannot be negative.")

    @property
    def longitudinal_input_complete(self) -> bool:
        return (
            self.lambda_s > 0.0
            and self.characteristic_fatigue_strength_mpa > 0.0
        )

    @property
    def shear_link_input_complete(self) -> bool:
        return (
            self.shear_link_lambda_s > 0.0
            and self.shear_link_characteristic_fatigue_strength_mpa > 0.0
        )


@dataclass(frozen=True)
class FatigueApplicationResult:
    search: ProjectNativeFLM3GrillageSearchResult
    girders: tuple[NativeFLM3LayeredGirderFatigueResult, ...]
    blockers: tuple[str, ...]
    status: str

    @property
    def passes(self) -> bool | None:
        if self.blockers:
            return None
        checks: list[bool] = []
        for item in self.girders:
            checks.append(item.fatigue.passes)
            if item.shear_links is not None:
                checks.append(item.shear_links.fatigue.passes)
        return all(checks) if checks else None


def run_application_fatigue(
    project: ProjectInput,
    design: ApplicationDesignInterpretationSuite,
    *,
    settings: FatigueApplicationSettings,
    analysis_grid: ApplicationAnalysisGrid,
) -> FatigueApplicationResult:
    """Run native FLM3 and connect its stress ranges to the selected design cage."""

    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Desktop FLM3 integration currently targets the simple-span application path."
        )
    search = run_project_native_flm3_grillage_search(
        project,
        transverse_stations_m=analysis_grid.stations_m,
        axle_load_factor=settings.axle_load_factor,
        movement_step_m=settings.movement_step_m,
        section_step_m=settings.section_step_m,
        name=f"{project.name} - application native FLM3",
    )

    blockers: list[str] = []
    if not settings.longitudinal_input_complete:
        blockers.append(
            "FLM3 longitudinal reinforcement fatigue requires project/detail "
            "lambda_s and characteristic fatigue strength"
        )
    if not settings.shear_link_input_complete:
        blockers.append(
            "FLM3 vertical-link fatigue requires link lambda_s and characteristic "
            "fatigue strength"
        )

    girder_results: list[NativeFLM3LayeredGirderFatigueResult] = []
    if settings.longitudinal_input_complete:
        for row in design.girders:
            bars = row.selected_bars
            links = row.selected_links
            section = LayeredGirderDesignInput(
                composite_slab_width_m=row.slab_width_m,
                effective_depth_m=row.effective_depth_m,
                steel_area_mm2=bars.provided_area_mm2,
                bar_diameter_mm=bars.bar_diameter_mm,
                bar_spacing_mm=(
                    bars.bar_diameter_mm + bars.clear_horizontal_spacing_mm
                ),
                cover_mm=row.detailing.cover_and_durability.provided_cover_mm,
                provided_shear_asw_per_s_mm2_per_m=(
                    links.provided_asw_per_s_mm2_per_m
                ),
            )
            girder_results.append(
                run_project_layered_girder_fatigue_from_native_flm3(
                    project,
                    search=search,
                    girder_index=row.girder_index,
                    section=section,
                    lambda_s=settings.lambda_s,
                    characteristic_fatigue_strength_mpa=(
                        settings.characteristic_fatigue_strength_mpa
                    ),
                    gamma_s_fat=settings.gamma_s_fat,
                    phi_fat=settings.phi_fat,
                    check_concrete=settings.check_concrete,
                    shear_link_characteristic_fatigue_strength_mpa=(
                        settings.shear_link_characteristic_fatigue_strength_mpa
                        if settings.shear_link_input_complete
                        else None
                    ),
                    shear_link_lambda_s=(
                        settings.shear_link_lambda_s
                        if settings.shear_link_input_complete
                        else None
                    ),
                    shear_link_phi_fat=settings.shear_link_phi_fat,
                )
            )

    return FatigueApplicationResult(
        search=search,
        girders=tuple(girder_results),
        blockers=tuple(blockers),
        status=(
            "Native full-width FLM3 is now part of the desktop design workflow. "
            "Traffic moment/shear ranges are calculated for every physical girder and, "
            "when the project fatigue-category inputs are supplied, are checked against "
            "the actual selected longitudinal bars, concrete compression and vertical links."
        ),
    )
