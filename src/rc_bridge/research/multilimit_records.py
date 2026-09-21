from __future__ import annotations

from dataclasses import asdict, dataclass

from rc_bridge.core.models import ProjectInput
from rc_bridge.design.bs5400_provided_shear import (
    provided_vertical_link_resistance_bs5400,
)
from rc_bridge.design.eurocode_shear import provided_vertical_shear_resistance
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)
from rc_bridge.workflow.bs5400_girder import BS5400TGirderInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import ProjectTGirderVerificationResult
from rc_bridge.workflow.project_bs5400_complete import (
    ProjectBS5400CompleteVerificationResult,
)


@dataclass(frozen=True)
class MultiLimitTrainingRecord:
    """One provenance-safe deterministic row for multi-output ANN training."""

    solver_profile: str
    girder_index: int
    span_m: float
    girder_spacing_m: float
    girder_depth_m: float
    deck_thickness_m: float
    effective_depth_m: float
    web_width_m: float
    fck_mpa: float | None
    fcu_mpa: float | None
    fyk_mpa: float
    longitudinal_steel_area_mm2: float
    provided_shear_steel_mm2_per_m: float | None
    permanent_moment_knm: float
    traffic_moment_knm: float
    design_moment_knm: float
    design_shear_kn: float
    moment_resistance_knm: float
    shear_resistance_kn: float
    crack_width_mm: float
    crack_limit_mm: float
    deflection_mm: float
    deflection_limit_mm: float
    flexure_utilization: float
    shear_utilization: float
    crack_utilization: float
    deflection_utilization: float
    g_flexure_knm: float
    g_shear_kn: float
    g_crack_mm: float
    g_deflection_mm: float
    g_fatigue: float | None
    g_torsion: float | None
    traffic_distribution_method: str
    crack_combination_name: str
    deflection_combination_name: str

    def to_dict(self) -> dict[str, float | int | str | None]:
        return asdict(self)


def eurocode_multilimit_record_from_project(
    result: ProjectTGirderVerificationResult,
    *,
    project: ProjectInput,
    section: TGirderDesignInput,
    verification: DeterministicSolverVerification,
    span_index: int = 0,
    provided_shear_steel_mm2_per_m: float | None = None,
    g_fatigue: float | None = None,
    g_torsion: float | None = None,
) -> MultiLimitTrainingRecord:
    """Convert a verified Eurocode project result into one ANN ground-truth row.

    If V_Ed exceeds V_Rd,c, actual provided vertical shear reinforcement must be
    supplied. The shear target then uses min(V_Rd,s, V_Rd,max) - V_Ed rather than
    the concrete-only reserve or the *required* reinforcement demand.
    """
    verification.require_ready_for(\n        expected_profile=SolverProfile.EUROCODE_1G,\n        scope=verification_scope,\n    )
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")

    design = result.design.uls_design
    shear = design.shear
    ved_kn = abs(design.design_effects.shear_kn)
    shear_resistance_kn = shear.concrete_resistance_kn
    shear_utilization = shear.utilization_concrete_only
    g_shear_kn = shear.g_shear_concrete_kn

    section_provided_shear = section.provided_shear_asw_per_s_mm2_per_m
    if (
        provided_shear_steel_mm2_per_m is not None
        and section_provided_shear is not None
        and abs(provided_shear_steel_mm2_per_m - section_provided_shear) > 1.0e-9
    ):
        raise ValueError(
            "Conflicting provided shear reinforcement was supplied in the section "
            "and ANN record call."
        )
    effective_provided_shear = (
        provided_shear_steel_mm2_per_m
        if provided_shear_steel_mm2_per_m is not None
        else section_provided_shear
    )

    if ved_kn > shear.concrete_resistance_kn:
        if effective_provided_shear is None:
            raise ValueError(
                "Actual provided A_sw/s is required for ANN shear ground truth when "
                "V_Ed exceeds V_Rd,c. Required reinforcement alone cannot define g_V."
            )
        provided = provided_vertical_shear_resistance(
            provided_asw_per_s_mm2_per_m=effective_provided_shear,
            web_width_m=section.web_width_m,
            effective_depth_m=section.effective_depth_m,
            fck_mpa=result.materials.fck_mpa,
            fyk_mpa=result.materials.fyk_mpa,
        )
        shear_resistance_kn = provided.governing_resistance_kn
        shear_utilization = (
            ved_kn / shear_resistance_kn if shear_resistance_kn > 0.0 else float("inf")
        )
        g_shear_kn = shear_resistance_kn - ved_kn

    span_m = float(project.geometry.span_lengths_m[span_index])
    return MultiLimitTrainingRecord(
        solver_profile=SolverProfile.EUROCODE_1G.value,
        girder_index=result.combinations.girder_index,
        span_m=span_m,
        girder_spacing_m=float(project.geometry.girder_spacing_m),
        girder_depth_m=float(project.geometry.girder_depth_m),
        deck_thickness_m=project.geometry.physical_deck_depth_m,
        effective_depth_m=section.effective_depth_m,
        web_width_m=section.web_width_m,
        fck_mpa=result.materials.fck_mpa,
        fcu_mpa=None,
        fyk_mpa=result.materials.fyk_mpa,
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        provided_shear_steel_mm2_per_m=effective_provided_shear,
        permanent_moment_knm=result.combinations.permanent_characteristic.moment_knm,
        traffic_moment_knm=result.combinations.traffic_characteristic.moment_knm,
        design_moment_knm=design.design_effects.moment_knm,
        design_shear_kn=ved_kn,
        moment_resistance_knm=design.flexure.resistance_knm,
        shear_resistance_kn=shear_resistance_kn,
        crack_width_mm=result.design.crack.crack_width_mm,
        crack_limit_mm=result.design.crack.crack_limit_mm,
        deflection_mm=result.design.deflection.interpolated_deflection_mm,
        deflection_limit_mm=result.design.deflection.allowable_deflection_mm,
        flexure_utilization=design.flexure.utilization,
        shear_utilization=shear_utilization,
        crack_utilization=result.design.crack.utilization,
        deflection_utilization=result.design.deflection.utilization,
        g_flexure_knm=result.design.g_flexure_knm,
        g_shear_kn=g_shear_kn,
        g_crack_mm=result.design.g_crack_mm,
        g_deflection_mm=result.design.g_deflection_mm,
        g_fatigue=g_fatigue,
        g_torsion=g_torsion,
        traffic_distribution_method=result.combinations.traffic_distribution_method,
        crack_combination_name=result.serviceability.crack_combination_name,
        deflection_combination_name=result.serviceability.deflection_combination_name,
    )


def bs5400_multilimit_record_from_project(
    result: ProjectBS5400CompleteVerificationResult,
    *,
    project: ProjectInput,
    section: BS5400TGirderInput,
    verification: DeterministicSolverVerification,
    provided_shear_steel_mm2_per_m: float,
    span_index: int = 0,
    g_fatigue: float | None = None,
    g_torsion: float | None = None,
) -> MultiLimitTrainingRecord:
    """Convert a verified BS 5400/BD 37/01 result into the common ANN row.

    Cube strength remains explicit and cylinder strength is left empty. Actual
    supplied beam links are required so the shear margin is a resistance margin,
    not merely the link quantity calculated by the design equation.
    """
    verification.require_ready_for(\n        expected_profile=SolverProfile.BS5400_BD37_01,\n        scope=verification_scope,\n    )
    if not 0 <= span_index < len(project.geometry.span_lengths_m):
        raise IndexError("span_index is outside the project span list.")
    if project.materials.fcu_mpa is None:
        raise ValueError("BS 5400 ANN records require explicit fcu_mpa.")

    deflection = result.deflection.deflection
    if (
        deflection.allowable_deflection_mm is None
        or deflection.utilization is None
        or deflection.g_deflection_mm is None
    ):
        raise ValueError(
            "BS 5400 ANN deflection ground truth requires an explicit project "
            "deflection acceptance criterion."
        )

    design = result.uls.design
    ved_kn = design.shear.design_shear_kn
    fyv_mpa = section.shear_steel_yield_mpa or float(project.materials.fyk_mpa)
    provided = provided_vertical_link_resistance_bs5400(
        ved_kn=ved_kn,
        provided_asv_per_s_mm2_per_m=provided_shear_steel_mm2_per_m,
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        fcu_mpa=float(project.materials.fcu_mpa),
        fyv_mpa=fyv_mpa,
    )
    crack = result.cracking.crack.crack
    span_m = float(project.geometry.span_lengths_m[span_index])

    return MultiLimitTrainingRecord(
        solver_profile=SolverProfile.BS5400_BD37_01.value,
        girder_index=result.girder_index,
        span_m=span_m,
        girder_spacing_m=float(project.geometry.girder_spacing_m),
        girder_depth_m=float(project.geometry.girder_depth_m),
        deck_thickness_m=project.geometry.physical_deck_depth_m,
        effective_depth_m=section.effective_depth_m,
        web_width_m=section.web_width_m,
        fck_mpa=None,
        fcu_mpa=float(project.materials.fcu_mpa),
        fyk_mpa=float(project.materials.fyk_mpa),
        longitudinal_steel_area_mm2=section.steel_area_mm2,
        provided_shear_steel_mm2_per_m=provided_shear_steel_mm2_per_m,
        permanent_moment_knm=result.uls.permanent_characteristic.moment_knm,
        traffic_moment_knm=result.uls.traffic_characteristic.moment_knm,
        design_moment_knm=result.uls.design.uls_combination.effects.moment_knm,
        design_shear_kn=ved_kn,
        moment_resistance_knm=design.flexure.resistance_knm,
        shear_resistance_kn=provided.governing_resistance_kn,
        crack_width_mm=crack.crack_width_mm,
        crack_limit_mm=crack.allowable_crack_width_mm,
        deflection_mm=deflection.total_deflection_mm,
        deflection_limit_mm=deflection.allowable_deflection_mm,
        flexure_utilization=design.flexure.utilization,
        shear_utilization=provided.utilization,
        crack_utilization=crack.utilization,
        deflection_utilization=deflection.utilization,
        g_flexure_knm=design.flexure.g_flexure_knm,
        g_shear_kn=provided.g_shear_kn,
        g_crack_mm=crack.g_crack_mm,
        g_deflection_mm=deflection.g_deflection_mm,
        g_fatigue=g_fatigue,
        g_torsion=g_torsion,
        traffic_distribution_method=result.traffic_distribution_method,
        crack_combination_name="BS 5400 characteristic permanent + nominal HA service effects",
        deflection_combination_name="BS 5400 nominal-load deflection",
    )
