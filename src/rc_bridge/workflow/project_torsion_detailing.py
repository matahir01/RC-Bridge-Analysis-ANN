from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.physical_sections import girder_web_width_m
from rc_bridge.core.models import ProjectInput
from rc_bridge.design.eurocode_detailing import maximum_vertical_link_spacings_mm
from rc_bridge.design.eurocode_torsion_detailing import (
    TorsionCageDetailingResult,
    select_torsion_cage_detailing,
)
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.project_native_lm1_torsion import (
    NativeLM1MatchedShearTorsionResult,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput


@dataclass(frozen=True)
class ProjectNativeTorsionCageDetailingResult:
    cage: TorsionCageDetailingResult
    governing_shear_case_id: int
    governing_shear_member_id: int
    governing_shear_member_end: str
    governing_torsion_link_case_id: int
    governing_torsion_link_member_id: int
    governing_torsion_link_member_end: str
    governing_longitudinal_case_id: int
    governing_longitudinal_member_id: int
    governing_longitudinal_member_end: str
    status: str


def run_project_native_torsion_cage_detailing(
    project: ProjectInput,
    *,
    section: LayeredGirderDesignInput,
    torsion_cell: TorsionCellInput,
    matched: NativeLM1MatchedShearTorsionResult,
) -> ProjectNativeTorsionCageDetailingResult:
    """Create a conservative full-span cage family from matched native V-T points."""
    if not matched.evaluated_points:
        raise ValueError("Matched native shear-torsion result contains no evaluated points.")

    shear_point = max(
        matched.evaluated_points,
        key=lambda item: item.shear_strut.asw_per_s_mm2_per_m,
    )
    torsion_link_point = max(
        matched.evaluated_points,
        key=lambda item: item.torsion.transverse_asw_per_s_mm2_per_m,
    )
    # The link family must satisfy the independent maxima of shear total-leg
    # demand and torsion one-leg demand. This is conservative when they occur at
    # different traffic placements and avoids combining non-coincident actions.
    required_shear = max(
        item.shear_strut.asw_per_s_mm2_per_m for item in matched.evaluated_points
    )
    required_torsion_transverse = max(
        item.torsion.transverse_asw_per_s_mm2_per_m
        for item in matched.evaluated_points
    )
    longitudinal_point = max(
        matched.evaluated_points,
        key=lambda item: item.torsion.longitudinal_asl_mm2,
    )
    required_longitudinal = longitudinal_point.torsion.longitudinal_asl_mm2

    max_longitudinal_spacing, max_transverse_spacing = maximum_vertical_link_spacings_mm(
        effective_depth_m=section.effective_depth_m
    )
    # EC2 torsion links require a stricter longitudinal spacing than ordinary
    # shear links. The code rule is based on the outer effective-section
    # perimeter. Only the verified torsion-cell centre-line perimeter uk is
    # available here; uk/8 is therefore used as an explicitly conservative cap
    # (uk is not larger than the corresponding outer perimeter).
    conservative_torsion_link_spacing_mm = torsion_cell.uk_m * 1000.0 / 8.0
    cage = select_torsion_cage_detailing(
        required_shear_asw_per_s_mm2_per_m=required_shear,
        required_torsion_leg_asw_per_s_mm2_per_m=required_torsion_transverse,
        required_torsion_longitudinal_area_mm2=required_longitudinal,
        torsion_cell_perimeter_m=torsion_cell.uk_m,
        web_width_mm=girder_web_width_m(project.geometry) * 1000.0,
        cover_mm=section.cover_mm,
        maximum_longitudinal_spacing_mm=max_longitudinal_spacing,
        maximum_transverse_leg_spacing_mm=max_transverse_spacing,
        maximum_torsion_link_spacing_mm=conservative_torsion_link_spacing_mm,
        maximum_longitudinal_torsion_bar_spacing_mm=350.0,
    )
    return ProjectNativeTorsionCageDetailingResult(
        cage=cage,
        governing_shear_case_id=shear_point.case_id,
        governing_shear_member_id=shear_point.member_id,
        governing_shear_member_end=shear_point.member_end,
        governing_torsion_link_case_id=torsion_link_point.case_id,
        governing_torsion_link_member_id=torsion_link_point.member_id,
        governing_torsion_link_member_end=torsion_link_point.member_end,
        governing_longitudinal_case_id=longitudinal_point.case_id,
        governing_longitudinal_member_id=longitudinal_point.member_id,
        governing_longitudinal_member_end=longitudinal_point.member_end,
        status=(
            "Full-span drawing cage family uses separately enveloped reinforcement demands "
            "from benchmark-gated matched V-T points. It does not claim that independent "
            "shear and torsion maxima are a simultaneous structural action. Torsion links "
            "also use the conservative verified-cell uk/8 spacing cap, and longitudinal "
            "torsion bars are limited to 350 mm nominal perimeter spacing."
        ),
    )
