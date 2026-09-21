import pytest

from rc_bridge.codes.eurocode.combinations import (
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.workflow.continuous_support_design import (
    ContinuousSupportFlangedFlexureInput,
    ContinuousSupportFlexureInput,
    check_continuous_support_flexure,
)


def _hogging_combinations():
    return signed_section_combinations(
        permanent_characteristic_effect=-300.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=50.0,
            minimum_negative_effect=-120.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
    )


def test_signed_hogging_uls_routes_to_top_steel_support_check() -> None:
    result = check_continuous_support_flexure(
        _hogging_combinations(),
        ContinuousSupportFlexureInput(
            compression_width_m=0.30,
            effective_depth_m=1.05,
            provided_top_steel_area_mm2=6000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        ),
    )

    assert result.negative_uls_effect_knm == pytest.approx(-567.0)
    assert result.flexure.design_moment_knm == pytest.approx(-567.0)
    assert result.flexure.signed_resistance_knm < 0.0
    assert result.flexure.g_hogging_knm == pytest.approx(
        result.flexure.resistance_magnitude_knm - 567.0
    )
    assert result.flexure.compression_model == "rectangular"


def test_i_girder_hogging_can_use_actual_bottom_compression_flange() -> None:
    result = check_continuous_support_flexure(
        _hogging_combinations(),
        ContinuousSupportFlangedFlexureInput(
            bottom_flange_width_m=0.65,
            bottom_flange_thickness_m=0.18,
            web_width_m=0.30,
            effective_depth_from_bottom_m=1.12,
            provided_top_steel_area_mm2=6500.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        ),
    )

    assert result.negative_uls_effect_knm == pytest.approx(-567.0)
    assert result.flexure.design_moment_magnitude_knm == pytest.approx(567.0)
    assert result.flexure.compression_model == "bottom_flanged"
    assert result.flexure.compression_flange_width_m == pytest.approx(0.65)
    assert result.flexure.compression_flange_thickness_m == pytest.approx(0.18)
    assert result.flexure.web_width_m == pytest.approx(0.30)
    assert result.flexure.required_top_steel_area_mm2 > 0.0
    assert result.flexure.resistance_magnitude_knm > 0.0


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
