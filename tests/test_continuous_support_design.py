import pytest

from rc_bridge.codes.eurocode.combinations import (
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.workflow.continuous_support_design import (
    ContinuousSupportFlexureInput,
    check_continuous_support_flexure,
)


def test_signed_hogging_uls_routes_to_top_steel_support_check() -> None:
    combinations = signed_section_combinations(
        permanent_characteristic_effect=-300.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=50.0,
            minimum_negative_effect=-120.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
    )
    result = check_continuous_support_flexure(
        combinations,
        ContinuousSupportFlexureInput(
            compression_width_m=0.30,
            effective_depth_m=1.05,
            provided_top_steel_area_mm2=6000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        ),
    )

    assert result.negative_uls_effect_knm == pytest.approx(-585.0)
    assert result.flexure.design_moment_knm == pytest.approx(-585.0)
    assert result.flexure.signed_resistance_knm < 0.0
    assert result.flexure.g_hogging_knm == pytest.approx(
        result.flexure.resistance_magnitude_knm - 585.0
    )


def test_support_flexure_rejects_shear_combination() -> None:
    combinations = signed_section_combinations(
        permanent_characteristic_effect=-100.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=20.0,
            minimum_negative_effect=-30.0,
            response_kind="shear",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
    )

    with pytest.raises(ValueError, match="moment combinations"):
        check_continuous_support_flexure(
            combinations,
            ContinuousSupportFlexureInput(
                compression_width_m=0.30,
                effective_depth_m=1.05,
                provided_top_steel_area_mm2=6000.0,
                fck_mpa=35.0,
                fyk_mpa=500.0,
            ),
        )
