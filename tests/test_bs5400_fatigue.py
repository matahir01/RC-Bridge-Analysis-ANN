import pytest

from rc_bridge.design.bs5400_fatigue import (
    assess_reinforcement_fatigue_scope_bs5400,
    check_reinforcement_fatigue_bs5400,
    effective_stress_range_nonwelded_part10,
    part10_permissible_stress_range_mpa,
)


def test_base_bs5400_scope_does_not_force_part10_for_unwelded_bar() -> None:
    result = assess_reinforcement_fatigue_scope_bs5400(welded_reinforcement=False)
    assert not result.requires_part10_check


def test_base_bs5400_scope_requires_part10_for_welded_bar() -> None:
    result = assess_reinforcement_fatigue_scope_bs5400(welded_reinforcement=True)
    assert result.requires_part10_check


def test_part10_nonwelded_stress_reversal_uses_reduced_compression_component() -> None:
    stress_range = effective_stress_range_nonwelded_part10(
        maximum_stress_mpa=100.0,
        minimum_stress_mpa=-50.0,
    )
    assert stress_range == pytest.approx(130.0)


def test_part10_sn_relation_returns_permissible_stress_range() -> None:
    allowable = part10_permissible_stress_range_mpa(
        design_cycles=2_000_000.0,
        sn_exponent_m=9.0,
        sn_constant_k2=0.75e27,
    )
    assert allowable == pytest.approx(193.19837721)


def test_bs5400_fatigue_check_uses_explicit_sn_basis() -> None:
    result = check_reinforcement_fatigue_bs5400(
        maximum_stress_mpa=100.0,
        minimum_stress_mpa=-50.0,
        design_cycles=2_000_000.0,
        sn_exponent_m=9.0,
        sn_constant_k2=0.75e27,
        nonwelded_effective_range=True,
    )
    assert result.effective_stress_range_mpa == pytest.approx(130.0)
    assert result.allowable_stress_range_mpa == pytest.approx(193.19837721)
    assert result.g_fatigue_mpa > 0.0
    assert result.passes


def test_bs5400_fatigue_requires_one_explicit_allowable_basis() -> None:
    with pytest.raises(ValueError, match="Supply either"):
        check_reinforcement_fatigue_bs5400(
            maximum_stress_mpa=100.0,
            minimum_stress_mpa=20.0,
        )
