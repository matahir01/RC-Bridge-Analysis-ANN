import pytest

from rc_bridge.application.preferences import (
    ApplicationPreferences,
    EurocodeApplicationBasis,
)
from rc_bridge.design.eurocode_deflection import ec2_interpolated_udl_deflection


def test_road_bridge_deflection_limit_is_not_invented_by_default() -> None:
    basis = EurocodeApplicationBasis()

    assert basis.deflection_limit_span_ratio is None


def test_explicit_project_deflection_ratio_is_preserved() -> None:
    preferences = ApplicationPreferences(
        eurocode=EurocodeApplicationBasis(
            deflection_limit_span_ratio=500.0,
        )
    )

    restored = ApplicationPreferences.from_dict(preferences.as_dict())

    assert restored.eurocode.deflection_limit_span_ratio == pytest.approx(500.0)


def test_legacy_saved_ratio_remains_usable_as_explicit_project_input() -> None:
    restored = ApplicationPreferences.from_dict(
        {
            "eurocode": {
                "deflection_limit_span_ratio": 1000.0,
            }
        }
    )

    assert restored.eurocode.deflection_limit_span_ratio == pytest.approx(1000.0)


def test_invalid_explicit_project_deflection_ratio_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive when specified"):
        EurocodeApplicationBasis(deflection_limit_span_ratio=0.0)


def test_deflection_can_be_calculated_without_assigning_false_pass_fail() -> None:
    result = ec2_interpolated_udl_deflection(
        udl_kn_m=25.0,
        span_m=15.0,
        ecm_mpa=34_000.0,
        uncracked_second_moment_mm4=1.2e10,
        cracked_second_moment_mm4=6.0e9,
        cracking_moment_knm=300.0,
        allowable_deflection_mm=None,
        beta=0.5,
    )

    assert result.interpolated_deflection_mm > 0.0
    assert result.allowable_deflection_mm is None
    assert result.utilization is None
    assert result.g_deflection_mm is None
    assert result.criterion_defined is False
    assert result.passes is None
    assert "project/client road-bridge deflection limit not specified" in result.status
