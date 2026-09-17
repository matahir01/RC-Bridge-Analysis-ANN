import pytest

from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)


def test_continuous_eurocode_profile_is_distinct_and_locked_by_default() -> None:
    verification = DeterministicSolverVerification(
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS
    )

    assert SolverProfile.EUROCODE_CONTINUOUS != SolverProfile.EUROCODE_1G
    assert verification.ann_ready is False
    assert "independent_benchmark" in verification.missing_requirements()
    assert "deflection" in verification.missing_requirements()
    with pytest.raises(RuntimeError, match="Missing deterministic verification milestones"):
        verification.require_ann_ready(expected_profile=SolverProfile.EUROCODE_CONTINUOUS)


def test_simple_span_verification_cannot_unlock_continuous_ground_truth() -> None:
    verification = DeterministicSolverVerification(
        solver_profile=SolverProfile.EUROCODE_1G,
        traffic_loading=True,
        load_combinations=True,
        flexure=True,
        shear=True,
        cracking=True,
        deflection=True,
        fatigue=True,
        detailing=True,
        transverse_distribution=True,
        independent_benchmark=True,
    )

    assert verification.ann_ready is True
    with pytest.raises(RuntimeError, match="does not match requested solver profile"):
        verification.require_ann_ready(expected_profile=SolverProfile.EUROCODE_CONTINUOUS)
