from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    SignedSectionCombinationSet,
)
from rc_bridge.codes.eurocode.en1991_2 import LM1AdjustmentFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.continuous_shear_design import (
    ContinuousShearDesignCheck,
    ContinuousShearDesignInput,
    check_continuous_section_shear,
)
from rc_bridge.workflow.project_continuous_lm1 import (
    ProjectContinuousLM1SectionInput,
    ProjectContinuousLM1SectionResult,
    continuous_lm1_girder_combinations,
    run_project_continuous_lm1_section,
)


@dataclass(frozen=True)
class ProjectContinuousShearSectionInput:
    response_span_index: int
    response_position_m: float
    girder_index: int
    permanent_characteristic_shear_kn: float
    design: ContinuousShearDesignInput
    label: str = "critical shear section"

    def __post_init__(self) -> None:
        if self.response_span_index < 0:
            raise ValueError("response_span_index cannot be negative.")
        if self.response_position_m < 0.0:
            raise ValueError("response_position_m cannot be negative.")
        if self.girder_index <= 0:
            raise ValueError("girder_index must be positive.")
        if not self.label.strip():
            raise ValueError("Critical shear section label cannot be empty.")


@dataclass(frozen=True)
class ProjectContinuousShearSectionResult:
    label: str
    response_span_index: int
    response_position_m: float
    girder_index: int
    traffic: ProjectContinuousLM1SectionResult
    combinations: SignedSectionCombinationSet
    design: ContinuousShearDesignCheck
    status: str


@dataclass(frozen=True)
class ProjectContinuousShearScanResult:
    sections: tuple[ProjectContinuousShearSectionResult, ...]
    governing_section_index: int
    governing_design_shear_kn: float
    status: str

    @property
    def governing_section(self) -> ProjectContinuousShearSectionResult:
        return self.sections[self.governing_section_index]


def run_project_continuous_lm1_shear_section(
    project: ProjectInput,
    *,
    ei_kn_m2_by_span: tuple[float, ...],
    section: ProjectContinuousShearSectionInput,
    lane_distributions: tuple[LaneGirderDistribution, ...],
    sls_factors: ServiceabilityPsiFactors,
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None,
    lm1_factors: LM1AdjustmentFactors | None = None,
    uls_factors: EurocodeFactors | None = None,
    influence_positions: int = 801,
    movement_steps: int = 1201,
) -> ProjectContinuousShearSectionResult:
    """Generate LM1 shear, combine it, then design one explicit critical section.

    The section location is caller supplied. This is intentional: the current
    project geometry does not yet contain support-face/bearing dimensions, so the
    workflow will not pretend that a support centreline is the EC2 design section.
    """
    traffic = run_project_continuous_lm1_section(
        project,
        ProjectContinuousLM1SectionInput(
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            response_span_index=section.response_span_index,
            response_position_m=section.response_position_m,
            response_kind="shear",
            lane_distributions=lane_distributions,
            remaining_area_distribution=remaining_area_distribution,
            factors=lm1_factors,
            influence_positions=influence_positions,
            movement_steps=movement_steps,
        ),
    )
    combinations = continuous_lm1_girder_combinations(
        traffic,
        girder_index=section.girder_index,
        permanent_characteristic_effect=section.permanent_characteristic_shear_kn,
        sls_factors=sls_factors,
        uls_factors=uls_factors,
    )
    design = check_continuous_section_shear(combinations, section.design)
    return ProjectContinuousShearSectionResult(
        label=section.label,
        response_span_index=section.response_span_index,
        response_position_m=section.response_position_m,
        girder_index=section.girder_index,
        traffic=traffic,
        combinations=combinations,
        design=design,
        status=(
            "Continuous Eurocode critical shear section evaluated from LM1 influence-line effects, "
            "supplied transverse distribution, signed EN 1990 combinations and explicit EC2 shear input"
        ),
    )


def run_project_continuous_lm1_shear_scan(
    project: ProjectInput,
    *,
    ei_kn_m2_by_span: tuple[float, ...],
    sections: tuple[ProjectContinuousShearSectionInput, ...],
    lane_distributions: tuple[LaneGirderDistribution, ...],
    sls_factors: ServiceabilityPsiFactors,
    remaining_area_distribution: RemainingAreaGirderDistribution | None = None,
    lm1_factors: LM1AdjustmentFactors | None = None,
    uls_factors: EurocodeFactors | None = None,
    influence_positions: int = 801,
    movement_steps: int = 1201,
) -> ProjectContinuousShearScanResult:
    """Run a set of explicit continuous-girder critical shear sections."""
    if not sections:
        raise ValueError("At least one critical shear section is required.")

    results = tuple(
        run_project_continuous_lm1_shear_section(
            project,
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            section=section,
            lane_distributions=lane_distributions,
            sls_factors=sls_factors,
            remaining_area_distribution=remaining_area_distribution,
            lm1_factors=lm1_factors,
            uls_factors=uls_factors,
            influence_positions=influence_positions,
            movement_steps=movement_steps,
        )
        for section in sections
    )
    governing_index = max(
        range(len(results)),
        key=lambda index: results[index].design.design_shear_kn,
    )
    return ProjectContinuousShearScanResult(
        sections=results,
        governing_section_index=governing_index,
        governing_design_shear_kn=results[governing_index].design.design_shear_kn,
        status=(
            "Explicit continuous-girder critical shear sections scanned; governing section selected by "
            "largest absolute factored shear demand"
        ),
    )
