import pytest

from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)


def test_signed_combinations_use_directional_permanent_factors_for_sagging_g() -> None:
    result = signed_section_combinations(
        permanent_characteristic_effect=100.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=50.0,
            minimum_negative_effect=-80.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
        uls_factors=EurocodeFactors(
            gamma_g_unfavourable=1.35,
            gamma_g_favourable=1.0,
            gamma_q_traffic=1.50,
        ),
    )

    assert result.positive_gamma_g == pytest.approx(1.35)
    assert result.negative_gamma_g == pytest.approx(1.0)
    assert result.positive_uls_effect == pytest.approx(210.0)
    assert result.negative_uls_effect == pytest.approx(-20.0)
    assert result.positive_characteristic_sls_effect == pytest.approx(150.0)
    assert result.negative_characteristic_sls_effect == pytest.approx(20.0)
    assert result.positive_frequent_sls_effect == pytest.approx(137.5)
    assert result.negative_frequent_sls_effect == pytest.approx(40.0)


def test_signed_combinations_use_directional_permanent_factors_for_hogging_g() -> None:
    result = signed_section_combinations(
        permanent_characteristic_effect=-100.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=80.0,
            minimum_negative_effect=-50.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.5, psi2_traffic=0.2),
    )

    assert result.positive_gamma_g == pytest.approx(1.0)
    assert result.negative_gamma_g == pytest.approx(1.35)
    assert result.positive_uls_effect == pytest.approx(20.0)
    assert result.negative_uls_effect == pytest.approx(-210.0)
    assert result.positive_quasi_permanent_sls_effect == pytest.approx(-84.0)
    assert result.negative_quasi_permanent_sls_effect == pytest.approx(-110.0)


def test_signed_envelope_rejects_wrong_extreme_signs() -> None:
    with pytest.raises(ValueError, match="maximum_positive_effect"):
        SignedSectionEnvelope(
            maximum_positive_effect=-1.0,
            minimum_negative_effect=-2.0,
            response_kind="shear",
        )
    with pytest.raises(ValueError, match="minimum_negative_effect"):
        SignedSectionEnvelope(
            maximum_positive_effect=1.0,
            minimum_negative_effect=2.0,
            response_kind="shear",
        )
