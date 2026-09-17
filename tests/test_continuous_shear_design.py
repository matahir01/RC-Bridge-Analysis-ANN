import pytest

from rc_bridge.codes.eurocode.combinations import (
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.workflow.continuous_shear_design import (
    ContinuousShearDesignInput,
    check_continuous_section_shear,
)


def _shear_combinations(
    permanent_kn: float,
    q_positive_kn: float,
    q_negative_kn: float,
):
    return signed_section_combinations(
        permanent_characteristic_effect=permanent_kn,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=q_positive_kn,
            minimum_negative_effect=q_negative_kn,
            response_kind="shear",
        ),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        ),
    )


def test_continuous_shear_uses_larger_absolute_signed_uls_branch() -> None:
    combinations = _shear_combinations(-100.0, 200.0, -300.0)
    result = check_continuous_section_shear(
        combinations,
        ContinuousShearDesignInput(
            web_width_m=0.30,
            effective_depth_m=0.80,
            longitudinal_steel_area_mm2=3000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        ),
    )

    assert result.governing_branch == "negative"
    assert result.design_shear_kn == pytest.approx(abs(combinations.negative_uls_effect))
    assert result.reinforcement_required
    assert result.required_links is not None
    assert result.provided_links is None
    assert result.governing_resistance_kn is None
    assert result.g_shear_kn is None
    assert result.provided_reinforcement_adequate is None


def test_continuous_shear_checks_actual_provided_links_when_required() -> None:
    combinations = _shear_combinations(-100.0, 200.0, -300.0)
    result = check_continuous_section_shear(
        combinations,
        ContinuousShearDesignInput(
            web_width_m=0.30,
            effective_depth_m=0.80,
            longitudinal_steel_area_mm2=3000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
            provided_asw_per_s_mm2_per_m=1200.0,
            cot_theta=2.0,
        ),
    )

    assert result.reinforcement_required
    assert result.provided_links is not None
    assert result.governing_resistance_kn == pytest.approx(
        result.provided_links.governing_resistance_kn
    )
    assert result.utilization == pytest.approx(
        result.design_shear_kn / result.governing_resistance_kn
    )
    assert result.g_shear_kn == pytest.approx(
        result.governing_resistance_kn - result.design_shear_kn
    )
    assert result.provided_reinforcement_adequate is True


def test_continuous_shear_uses_concrete_resistance_when_links_not_required() -> None:
    combinations = _shear_combinations(20.0, 20.0, -10.0)
    result = check_continuous_section_shear(
        combinations,
        ContinuousShearDesignInput(
            web_width_m=0.50,
            effective_depth_m=0.90,
            longitudinal_steel_area_mm2=5000.0,
            fck_mpa=35.0,
            fyk_mpa=500.0,
        ),
    )

    assert result.reinforcement_required is False
    assert result.required_links is None
    assert result.governing_resistance_kn == pytest.approx(result.concrete.vrdc_kn)
    assert result.g_shear_kn is not None and result.g_shear_kn > 0.0
    assert result.provided_reinforcement_adequate is True


def test_continuous_shear_rejects_moment_combination() -> None:
    combinations = signed_section_combinations(
        permanent_characteristic_effect=100.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=200.0,
            minimum_negative_effect=-50.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        ),
    )

    with pytest.raises(ValueError, match="shear combinations"):
        check_continuous_section_shear(
            combinations,
            ContinuousShearDesignInput(
                web_width_m=0.30,
                effective_depth_m=0.80,
                longitudinal_steel_area_mm2=3000.0,
                fck_mpa=35.0,
                fyk_mpa=500.0,
            ),
        )
