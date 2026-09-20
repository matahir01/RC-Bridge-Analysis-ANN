import pytest

from rc_bridge.application.verification_tolerance import VerificationImportTolerance


def test_default_v1_tolerance_matches_accepted_staad_output_resolution() -> None:
    policy = VerificationImportTolerance()

    assert policy.relative_tolerance == pytest.approx(0.001)
    assert policy.absolute_force_kn == pytest.approx(0.01)
    assert policy.absolute_moment_knm == pytest.approx(0.01)
    assert policy.absolute_displacement_m == pytest.approx(1.0e-6)
    assert policy.absolute_tolerance_for_unit("mm") == pytest.approx(0.001)


def test_v1_tolerance_accepts_one_print_increment_but_rejects_larger_near_zero_error() -> None:
    policy = VerificationImportTolerance()

    assert policy.passes(
        reference_value=0.0,
        comparison_value=0.01,
        unit="kN",
    )
    assert not policy.passes(
        reference_value=0.0,
        comparison_value=0.0101,
        unit="kN",
    )
    assert policy.passes(
        reference_value=0.0,
        comparison_value=0.001,
        unit="mm",
    )
    assert not policy.passes(
        reference_value=0.0,
        comparison_value=0.00101,
        unit="mm",
    )


def test_v1_tolerance_uses_relative_allowance_for_large_response() -> None:
    policy = VerificationImportTolerance()

    assert policy.allowable_absolute_error(
        reference_value=1_000.0,
        unit="kN",
    ) == pytest.approx(1.0)
    assert policy.passes(
        reference_value=1_000.0,
        comparison_value=1_000.9,
        unit="kN",
    )
    assert not policy.passes(
        reference_value=1_000.0,
        comparison_value=1_001.1,
        unit="kN",
    )
