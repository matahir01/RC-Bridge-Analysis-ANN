from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_shear import (
    ShearReinforcementResult,
    required_vertical_shear_reinforcement,
)
from rc_bridge.design.eurocode_torsion import (
    ShearTorsionInteractionResult,
    TorsionResult,
    shear_torsion_interaction,
    torsion_reinforcement_and_resistance,
)
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import ProjectGirderCombinationSet


@dataclass(frozen=True)
class TorsionCellInput:
    """Verified equivalent thin-walled torsion geometry."""

    ak_m2: float
    uk_m: float
    tef_m: float

    def __post_init__(self) -> None:
        if min(self.ak_m2, self.uk_m, self.tef_m) <= 0.0:
            raise ValueError("Ak, uk and tef must all be positive.")


@dataclass(frozen=True)
class ProjectShearTorsionResult:
    torsion: TorsionResult
    shear_strut: ShearReinforcementResult
    interaction: ShearTorsionInteractionResult
    geometry: TorsionCellInput
    status: str


def check_project_shear_torsion(
    project: ProjectInput,
    *,
    combinations: ProjectGirderCombinationSet,
    section: TGirderDesignInput,
    torsion_cell: TorsionCellInput,
    cot_theta: float = 2.0,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    alpha_cw: float = 1.0,
    nu1: float | None = None,
) -> ProjectShearTorsionResult:
    """Check EC2 torsion reinforcement and shear-torsion concrete-strut interaction.

    The same compression-strut angle is used for shear and torsion. Torsion-cell
    geometry is caller-supplied and must be independently verified; this helper
    intentionally does not infer Ak, uk or tef from an arbitrary girder shape.
    Minimum reinforcement, closed-link detailing, longitudinal bar placement,
    and torsion/cracking threshold checks remain separate detailing tasks.
    """
    if project.design_code != DesignCode.EUROCODE:
        raise ValueError("The shear-torsion adapter currently supports Eurocode only.")
    if combinations.girder_index <= 0:
        raise ValueError("A valid girder combination set is required.")

    fck_mpa = float(project.materials.fck_mpa)
    fyk_mpa = float(project.materials.fyk_mpa)
    ted_knm = abs(combinations.persistent_uls.effects.torsion_knm)
    ved_kn = abs(combinations.persistent_uls.effects.shear_kn)

    torsion = torsion_reinforcement_and_resistance(
        ted_knm=ted_knm,
        ak_m2=torsion_cell.ak_m2,
        uk_m=torsion_cell.uk_m,
        tef_m=torsion_cell.tef_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        alpha_cw=alpha_cw,
        cot_theta=cot_theta,
        nu1=nu1,
    )
    shear_strut = required_vertical_shear_reinforcement(
        ved_kn=ved_kn,
        web_width_m=section.web_width_m,
        effective_depth_m=section.effective_depth_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        gamma_c=gamma_c,
        gamma_s=gamma_s,
        alpha_cc=alpha_cc,
        cot_theta=cot_theta,
        alpha_cw=alpha_cw,
    )
    interaction = shear_torsion_interaction(
        ted_knm=ted_knm,
        trdmax_knm=torsion.trdmax_knm,
        ved_kn=ved_kn,
        vrdmax_kn=shear_strut.vrdmax_kn,
    )

    return ProjectShearTorsionResult(
        torsion=torsion,
        shear_strut=shear_strut,
        interaction=interaction,
        geometry=torsion_cell,
        status=(
            "EC2 shear-torsion strut interaction evaluated with explicit thin-wall geometry; "
            "detailing and torsion threshold checks remain pending"
        ),
    )
