from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.physical_sections import (
    girder_bottom_width_m,
    girder_web_width_m,
)
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.design.eurocode_detailing import (
    AnchorageLapResult,
    BeamDetailingResult,
    CoverDurabilityResult,
    LinkArrangement,
    LongitudinalBarArrangement,
    anchorage_and_lap_lengths_mm,
    beam_detailing_requirements,
    nominal_cover_check,
    select_longitudinal_bar_arrangement,
    select_vertical_link_arrangement,
)
from rc_bridge.workflow.eurocode_layered_girder import (
    EurocodeLayeredGirderWorkflowResult,
    LayeredGirderDesignInput,
)


@dataclass(frozen=True)
class ProjectLayeredGirderDetailingResult:
    detailing: BeamDetailingResult
    effective_concrete_area_m2: float
    tension_zone_width_m: float
    web_width_m: float
    provided_shear_asw_per_s_mm2_per_m: float | None
    provided_shear_satisfies_requirement: bool | None
    selected_longitudinal_bars: LongitudinalBarArrangement
    selected_links: LinkArrangement
    anchorage_and_laps: AnchorageLapResult
    cover_and_durability: CoverDurabilityResult
    status: str


def run_project_layered_girder_detailing(
    project: ProjectInput,
    *,
    section: LayeredGirderDesignInput,
    design: EurocodeLayeredGirderWorkflowResult,
    durability_minimum_cover_mm: float = 40.0,
    cover_deviation_mm: float = 10.0,
    nominal_link_diameter_mm: float = 12.0,
    aggregate_size_mm: float = 20.0,
) -> ProjectLayeredGirderDetailingResult:
    """Apply current EC2 beam detailing to a physical rectangular/T/I profile."""
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("Layered girder detailing currently supports Eurocode projects only.")
    web_width_m = girder_web_width_m(project.geometry)
    tension_width_m = girder_bottom_width_m(project.geometry)
    concrete_area_m2 = sum(layer.area_m2 for layer in design.concrete_layers)

    required_shear_steel = 0.0
    if design.uls_design.shear.shear_reinforcement is not None:
        required_shear_steel = (
            design.uls_design.shear.shear_reinforcement.asw_per_s_mm2_per_m
        )
    concrete = concrete_properties_ec2(float(project.materials.fck_mpa))
    detailing = beam_detailing_requirements(
        fctm_mpa=concrete.fctm_mpa,
        fck_mpa=float(project.materials.fck_mpa),
        fyk_mpa=float(project.materials.fyk_mpa),
        tension_zone_width_m=tension_width_m,
        web_width_m=web_width_m,
        effective_depth_m=section.effective_depth_m,
        concrete_area_m2=concrete_area_m2,
        provided_longitudinal_steel_mm2=section.steel_area_mm2,
        design_required_asw_per_s_mm2_per_m=required_shear_steel,
    )
    provided_shear = section.provided_shear_asw_per_s_mm2_per_m
    provided_shear_ok = (
        None
        if provided_shear is None
        else provided_shear >= detailing.shear.governing_required_asw_per_s_mm2_per_m
    )
    required_longitudinal = max(
        design.uls_design.flexure.required_steel_area_mm2,
        detailing.longitudinal.minimum_tension_steel_mm2,
    )
    selected_bars = select_longitudinal_bar_arrangement(
        required_area_mm2=required_longitudinal,
        web_width_mm=tension_width_m * 1000.0,
        cover_mm=section.cover_mm,
        link_diameter_mm=nominal_link_diameter_mm,
        aggregate_size_mm=aggregate_size_mm,
    )
    selected_links = select_vertical_link_arrangement(
        required_asw_per_s_mm2_per_m=(
            detailing.shear.governing_required_asw_per_s_mm2_per_m
        ),
        web_width_mm=web_width_m * 1000.0,
        maximum_longitudinal_spacing_mm=(
            detailing.shear.maximum_longitudinal_link_spacing_mm
        ),
        maximum_transverse_leg_spacing_mm=(
            detailing.shear.maximum_transverse_leg_spacing_mm
        ),
        cover_mm=section.cover_mm,
    )
    anchorage = anchorage_and_lap_lengths_mm(
        bar_diameter_mm=selected_bars.bar_diameter_mm,
        fyk_mpa=float(project.materials.fyk_mpa),
        fctd_mpa=0.7 * concrete.fctm_mpa / 1.5,
    )
    cover = nominal_cover_check(
        bar_diameter_mm=selected_bars.bar_diameter_mm,
        durability_minimum_cover_mm=durability_minimum_cover_mm,
        allowance_for_deviation_mm=cover_deviation_mm,
        provided_cover_mm=section.cover_mm,
    )
    return ProjectLayeredGirderDetailingResult(
        detailing=detailing,
        effective_concrete_area_m2=concrete_area_m2,
        tension_zone_width_m=tension_width_m,
        web_width_m=web_width_m,
        provided_shear_asw_per_s_mm2_per_m=provided_shear,
        provided_shear_satisfies_requirement=provided_shear_ok,
        selected_longitudinal_bars=selected_bars,
        selected_links=selected_links,
        anchorage_and_laps=anchorage,
        cover_and_durability=cover,
        status=(
            "EC2 physical-profile quantity checks, discrete longitudinal bars and vertical "
            "links, straight anchorage/laps and durability cover check completed"
        ),
    )
