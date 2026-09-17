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
            method="validated_envelope_lane_1",
        ),
        LaneGirderDistribution(
            lane_number=2,
            moment_fractions=lane_2,
            shear_fractions=lane_2,
            method="validated_envelope_lane_2",
        ),
    )


def _remaining_distribution() -> RemainingAreaGirderDistribution:
    fractions = tuple(1.0 / 7.0 for _ in range(7))
    return RemainingAreaGirderDistribution(
        moment_fractions=fractions,
        shear_fractions=fractions,
        method="validated_envelope_remaining_area",
    )


def test_continuous_design_envelope_finds_sagging_hogging_and_shear() -> None:
    result = run_project_continuous_lm1_design_envelope(
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

    assert len(result.stations) == 6
    assert result.max_positive_uls_moment_knm > 0.0
    assert result.min_negative_uls_moment_knm < 0.0
    assert result.max_abs_uls_shear_kn > 0.0
    assert abs(result.max_abs_shear_signed_kn) == pytest.approx(result.max_abs_uls_shear_kn)
    assert "validated_envelope_lane_1" in result.traffic_distribution_method
    assert result.max_positive_moment_station.moment_combinations.response_kind == "moment"
    assert result.max_abs_shear_station.shear_combinations.response_kind == "shear"


def test_continuous_design_envelope_retains_both_sides_of_internal_support() -> None:
    result = run_project_continuous_lm1_design_envelope(
        _project(),
        ContinuousDesignEnvelopeInput(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            permanent_udl_kn_m_by_span=(30.0, 30.0),
            girder_index=4,
            lane_distributions=_lane_distributions(),
            remaining_area_distribution=_remaining_distribution(),
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
            stations_per_span=3,
            influence_positions=21,
            movement_steps=31,
        ),
    )

    support_stations = [
        station for station in result.stations if station.global_position_m == pytest.approx(15.0)
    ]
    assert len(support_stations) == 2
    assert support_stations[0].permanent_moment_knm == pytest.approx(
        support_stations[1].permanent_moment_knm,
        rel=1e-9,
    )
    assert support_stations[0].permanent_moment_knm < 0.0
    assert support_stations[0].permanent_shear_kn != pytest.approx(
        support_stations[1].permanent_shear_kn
    )


def test_continuous_design_envelope_reports_station_coordinates() -> None:
    result = run_project_continuous_lm1_design_envelope(
        _project(),
        ContinuousDesignEnvelopeInput(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            permanent_udl_kn_m_by_span=(10.0, 10.0),
            girder_index=1,
            lane_distributions=_lane_distributions(),
            remaining_area_distribution=_remaining_distribution(),
            sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.0),
            stations_per_span=2,
            influence_positions=11,
            movement_steps=11,
        ),
    )

    assert [station.global_position_m for station in result.stations] == pytest.approx(
        [0.0, 15.0, 15.0, 30.0]
    )
