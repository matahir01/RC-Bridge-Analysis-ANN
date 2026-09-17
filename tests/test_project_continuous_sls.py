import pytest

from rc_bridge.analysis.lane_distribution import (
    LaneGirderDistribution,
    RemainingAreaGirderDistribution,
)
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeInput,
    run_project_continuous_lm1_design_envelope,
)
from rc_bridge.workflow.project_continuous_sls import (
    HoggingCrackMaterialInput,
    HoggingCrackSectionInput,
    run_continuous_hogging_crack_check,
)


def _envelope():
    project = ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[15.0, 15.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )
    lane_1 = (0.20, 0.18, 0.16, 0.14, 0.12, 0.10, 0.10)
    lane_2 = tuple(reversed(lane_1))
    distributions = (
        LaneGirderDistribution(
            lane_number=1,
            moment_fractions=lane_1,
            shear_fractions=lane_1,
            method="validated_sls_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=lane_2,
            shear_fractions=lane_2,
            method="validated_sls_lane_2",
        ),
    )
    fractions = tuple(1.0 / 7.0 for _ in range(7))
    remaining = RemainingAreaGirderDistribution(
        moment_fractions=fractions,
        shear_fractions=fractions,
        method="validated_sls_remaining",
    )
    return run_project_continuous_lm1_design_envelope(
        project,
        ContinuousDesignEnvelopeInput(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            permanent_udl_kn_m_by_span=(30.0, 30.0),
            girder_index=4,
            lane_distributions=distributions,
            remaining_area_distribution=remaining,
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
            stations_per_span=3,
            influence_positions=31,
            movement_steps=41,
        ),
    )


def _section() -> HoggingCrackSectionInput:
    return HoggingCrackSectionInput(
        bottom_flange_width_m=0.65,
        bottom_flange_thickness_m=0.18,
        web_width_m=0.30,
        total_depth_m=1.20,
        top_tension_flange_width_m=1.70,
        top_tension_flange_thickness_m=0.175,
        top_steel_area_mm2=6500.0,
        steel_depth_from_bottom_m=1.14,
        bar_diameter_mm=25.0,
        bar_spacing_mm=150.0,
        cover_mm=40.0,
    )


def _materials() -> HoggingCrackMaterialInput:
    return HoggingCrackMaterialInput(
        es_mpa=200000.0,
        ecm_mpa=34000.0,
        fct_eff_mpa=3.2,
    )


def test_continuous_hogging_crack_check_finds_internal_support_sls_station() -> None:
    result = run_continuous_hogging_crack_check(
        _envelope(),
        section=_section(),
        materials=_materials(),
        cracking_moment_knm=100.0,
        crack_limit_mm=0.30,
        combination_kind="frequent",
    )

    assert result.signed_service_moment_knm < 0.0
    assert result.service_moment_knm == pytest.approx(-result.signed_service_moment_knm)
    assert result.governing_station.global_position_m == pytest.approx(15.0)
    assert result.crack.steel_stress_mpa > 0.0
    assert result.crack.crack_width_mm >= 0.0
    assert result.crack.g_crack_mm == pytest.approx(0.30 - result.crack.crack_width_mm)


def test_continuous_hogging_service_moments_preserve_sls_combination_order() -> None:
    envelope = _envelope()
    characteristic = run_continuous_hogging_crack_check(
        envelope,
        section=_section(),
        materials=_materials(),
        cracking_moment_knm=100.0,
        crack_limit_mm=0.30,
        combination_kind="characteristic",
    )
    frequent = run_continuous_hogging_crack_check(
        envelope,
        section=_section(),
        materials=_materials(),
        cracking_moment_knm=100.0,
        crack_limit_mm=0.30,
        combination_kind="frequent",
    )
    quasi = run_continuous_hogging_crack_check(
        envelope,
        section=_section(),
        materials=_materials(),
        cracking_moment_knm=100.0,
        crack_limit_mm=0.30,
        combination_kind="quasi_permanent",
    )

    assert characteristic.service_moment_knm >= frequent.service_moment_knm
    assert frequent.service_moment_knm >= quasi.service_moment_knm
    assert characteristic.governing_station.global_position_m == pytest.approx(15.0)
    assert frequent.governing_station.global_position_m == pytest.approx(15.0)
    assert quasi.governing_station.global_position_m == pytest.approx(15.0)
