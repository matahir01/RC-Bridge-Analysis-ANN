import pytest

from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.continuous_shear_design import ContinuousShearDesignInput
from rc_bridge.workflow.project_continuous_shear import (
    ProjectContinuousShearSectionInput,
    run_project_continuous_lm1_shear_scan,
    run_project_continuous_lm1_shear_section,
)


def _project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[15.0, 15.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )


def _lane_distributions() -> tuple[LaneGirderDistribution, ...]:
    lane_1 = (0.20, 0.18, 0.16, 0.14, 0.12, 0.10, 0.10)
    lane_2 = tuple(reversed(lane_1))
    return (
        LaneGirderDistribution(
            lane_number=1,
            moment_fractions=lane_1,
            shear_fractions=lane_1,
            method="validated_shear_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=lane_2,
            shear_fractions=lane_2,
            method="validated_shear_lane_2",
        ),
    )


def _remaining_distribution() -> RemainingAreaGirderDistribution:
    fractions = tuple(1.0 / 7.0 for _ in range(7))
    return RemainingAreaGirderDistribution(
        moment_fractions=fractions,
        shear_fractions=fractions,
        method="validated_shear_remaining_area",
    )


def _design_input() -> ContinuousShearDesignInput:
    return ContinuousShearDesignInput(
        web_width_m=0.30,
        effective_depth_m=0.90,
        longitudinal_steel_area_mm2=5000.0,
        fck_mpa=35.0,
        fyk_mpa=500.0,
        provided_asw_per_s_mm2_per_m=1400.0,
    )


def test_project_continuous_shear_section_preserves_signed_effects_and_provenance() -> None:
    result = run_project_continuous_lm1_shear_section(
        _project(),
        ei_kn_m2_by_span=(1.0e6, 1.0e6),
        section=ProjectContinuousShearSectionInput(
            response_span_index=0,
            response_position_m=14.1,
            girder_index=4,
            permanent_characteristic_shear_kn=-250.0,
            design=_design_input(),
            label="span 1 near internal support",
        ),
        lane_distributions=_lane_distributions(),
        remaining_area_distribution=_remaining_distribution(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
        influence_positions=41,
        movement_steps=61,
    )

    assert result.traffic.girder_effects[3].response_kind == "shear"
    assert result.combinations.response_kind == "shear"
    assert result.combinations.negative_uls_effect < result.combinations.positive_uls_effect
    assert result.design.design_shear_kn == pytest.approx(
        max(
            abs(result.combinations.positive_uls_effect),
            abs(result.combinations.negative_uls_effect),
        )
    )
    assert "validated_shear_lane_1" in result.traffic.traffic_distribution_method


def test_project_continuous_shear_scan_selects_largest_factored_demand() -> None:
    sections = (
        ProjectContinuousShearSectionInput(
            response_span_index=0,
            response_position_m=0.9,
            girder_index=4,
            permanent_characteristic_shear_kn=220.0,
            design=_design_input(),
            label="span 1 left support critical section",
        ),
        ProjectContinuousShearSectionInput(
            response_span_index=0,
            response_position_m=14.1,
            girder_index=4,
            permanent_characteristic_shear_kn=-300.0,
            design=_design_input(),
            label="span 1 internal support critical section",
        ),
    )
    result = run_project_continuous_lm1_shear_scan(
        _project(),
        ei_kn_m2_by_span=(1.0e6, 1.0e6),
        sections=sections,
        lane_distributions=_lane_distributions(),
        remaining_area_distribution=_remaining_distribution(),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
        influence_positions=41,
        movement_steps=61,
    )

    assert len(result.sections) == 2
    expected = max(item.design.design_shear_kn for item in result.sections)
    assert result.governing_design_shear_kn == pytest.approx(expected)
    assert result.governing_section.design.design_shear_kn == pytest.approx(expected)


def test_project_continuous_shear_scan_requires_sections() -> None:
    with pytest.raises(ValueError, match="At least one critical shear section"):
        run_project_continuous_lm1_shear_scan(
            _project(),
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            sections=(),
            lane_distributions=_lane_distributions(),
            remaining_area_distribution=_remaining_distribution(),
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
            influence_positions=21,
            movement_steps=21,
        )
