import pytest

from rc_bridge.codes.eurocode.combinations import (
    ServiceabilityPsiFactors,
    SignedSectionEnvelope,
    signed_section_combinations,
)
from rc_bridge.design.eurocode_layered_cracking import HorizontalSectionLayer
from rc_bridge.workflow.continuous_support_sls import (
    ContinuousSupportCrackInput,
    check_continuous_support_cracking,
)


def _support_layers() -> tuple[HorizontalSectionLayer, ...]:
    return (
        HorizontalSectionLayer(0.80, 0.00, 0.15, "bottom compression flange"),
        HorizontalSectionLayer(0.30, 0.15, 0.95, "web"),
        HorizontalSectionLayer(1.70, 0.95, 1.20, "deck tension zone"),
    )


def _crack_input() -> ContinuousSupportCrackInput:
    return ContinuousSupportCrackInput(
        layers_from_compression_face=_support_layers(),
        total_depth_m=1.20,
        top_tension_steel_area_mm2=7500.0,
        steel_depth_from_compression_face_m=1.12,
        bar_diameter_mm=25.0,
        bar_spacing_mm=125.0,
        cover_mm=45.0,
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
        crack_limit_mm=0.30,
    )


def _moment_combinations():
    return signed_section_combinations(
        permanent_characteristic_effect=-800.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=250.0,
            minimum_negative_effect=-700.0,
            response_kind="moment",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
    )


def test_support_cracking_uses_explicit_negative_service_combination() -> None:
    combinations = _moment_combinations()
    characteristic = check_continuous_support_cracking(
        combinations,
        _crack_input(),
        service_combination="characteristic",
    )
    frequent = check_continuous_support_cracking(
        combinations,
        _crack_input(),
        service_combination="frequent",
    )
    quasi = check_continuous_support_cracking(
        combinations,
        _crack_input(),
        service_combination="quasi_permanent",
    )

    assert characteristic.signed_service_moment_knm == pytest.approx(
        combinations.negative_characteristic_sls_effect
    )
    assert frequent.signed_service_moment_knm == pytest.approx(
        combinations.negative_frequent_sls_effect
    )
    assert quasi.signed_service_moment_knm == pytest.approx(
        combinations.negative_quasi_permanent_sls_effect
    )
    assert characteristic.service_moment_magnitude_knm > frequent.service_moment_magnitude_knm
    assert frequent.service_moment_magnitude_knm > quasi.service_moment_magnitude_knm
    assert characteristic.crack.steel_stress_mpa > frequent.crack.steel_stress_mpa
    assert frequent.crack.steel_stress_mpa > quasi.crack.steel_stress_mpa


def test_support_cracking_represents_deck_as_tension_zone_not_compression_flange() -> None:
    result = check_continuous_support_cracking(
        _moment_combinations(),
        _crack_input(),
        service_combination="frequent",
    )

    assert result.service_moment_magnitude_knm > 0.0
    assert result.crack.effective_tension_area_mm2 > 0.0
    assert result.crack.effective_tension_depth_mm > 0.0
    assert result.crack.crack_width_mm >= 0.0


def test_support_cracking_rejects_shear_combinations() -> None:
    combinations = signed_section_combinations(
        permanent_characteristic_effect=-100.0,
        traffic_characteristic=SignedSectionEnvelope(
            maximum_positive_effect=100.0,
            minimum_negative_effect=-120.0,
            response_kind="shear",
        ),
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
    )
    with pytest.raises(ValueError, match="moment combinations"):
        check_continuous_support_cracking(
            combinations,
            _crack_input(),
            service_combination="frequent",
        )
