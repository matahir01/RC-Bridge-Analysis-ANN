import pytest

from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous_design import (
    ContinuousShearDesignInput,
    NegativeSupportFlangedDesignInput,
    NegativeSupportRectangularDesignInput,
    PositiveCompositeTSectionDesignInput,
    run_continuous_eurocode_uls_design,
)
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeInput,
    run_project_continuous_lm1_design_envelope,
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
            method="validated_design_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=lane_2,
            shear_fractions=lane_2,
            method="validated_design_lane_2",
        ),
    )


def _remaining_distribution() -> RemainingAreaGirderDistribution:
    fractions = tuple(1.0 / 7.0 for _ in range(7))
    return RemainingAreaGirderDistribution(
        moment_fractions=fractions,
        shear_fractions=fractions,
        method="validated_design_remaining",
    )


def _envelope():
    return run_project_continuous_lm1_design_envelope(
        _project(),
        ContinuousDesignEnvelopeInput(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            permanent_udl_kn_m_by_span=(30.0, 30.0),
            girder_index=4,
            lane_distributions=_lane_distributions(),
            remaining_area_distribution=_remaining_distribution(),
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
            stations_per_span=3,
            influence_positions=31,
            movement_steps=41,
        ),
    )


def test_continuous_uls_design_uses_separate_bottom_flange_for_hogging() -> None:
    result = run_continuous_eurocode_uls_design(
        _envelope(),
        positive_section=PositiveCompositeTSectionDesignInput(
            effective_flange_width_m=1.70,
            flange_thickness_m=0.175,
            web_width_m=0.30,
            effective_depth_from_top_m=1.10,
            provided_bottom_steel_area_mm2=7000.0,
        ),
        negative_section=NegativeSupportFlangedDesignInput(
            bottom_flange_width_m=0.70,
            bottom_flange_thickness_m=0.18,
            web_width_m=0.30,
            effective_depth_from_bottom_m=1.12,
            provided_top_steel_area_mm2=6500.0,
        ),
        shear_section=ContinuousShearDesignInput(
            web_width_m=0.30,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
        ),
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert result.positive_design_moment_knm > 0.0
    assert result.negative_design_moment_knm > 0.0
    assert result.design_shear_kn > 0.0
    assert result.positive_flexure.required_steel_area_mm2 > 0.0
    assert result.negative_flexure.required_steel_area_mm2 > 0.0
    assert result.shear.design_shear_kn == pytest.approx(result.design_shear_kn)
    assert result.negative_station.global_position_m == pytest.approx(15.0)
    assert result.negative_flexure.compression_model == "bottom_flanged"
    assert result.negative_flexure.signed_resistance_knm < 0.0


def test_continuous_uls_design_can_use_web_only_hogging_compression() -> None:
    result = run_continuous_eurocode_uls_design(
        _envelope(),
        positive_section=PositiveCompositeTSectionDesignInput(
            effective_flange_width_m=1.70,
            flange_thickness_m=0.175,
            web_width_m=0.30,
            effective_depth_from_top_m=1.10,
            provided_bottom_steel_area_mm2=7000.0,
        ),
        negative_section=NegativeSupportRectangularDesignInput(
            compression_width_m=0.30,
            effective_depth_from_bottom_m=1.12,
            provided_top_steel_area_mm2=6500.0,
        ),
        shear_section=ContinuousShearDesignInput(
            web_width_m=0.30,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
        ),
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert result.negative_flexure.required_steel_area_mm2 > 0.0
    assert result.negative_flexure.resistance_knm > 0.0
    assert result.negative_flexure.compression_model == "rectangular"
    assert result.negative_station.permanent_moment_knm < 0.0
