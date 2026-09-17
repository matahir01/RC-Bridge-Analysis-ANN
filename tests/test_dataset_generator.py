import pytest

from rc_bridge.research.generator import SolverOutputs, generate_training_records
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)

EUROCODE_SAMPLE = {
    "span_m": 15.0,
    "girder_spacing_m": 1.7,
    "girder_depth_m": 0.95,
    "deck_thickness_m": 0.25,
    "fck_mpa": 35.0,
    "fyk_mpa": 500.0,
    "steel_area_mm2": 4800.0,
}

BS5400_SAMPLE = {
    "span_m": 15.0,
    "girder_spacing_m": 1.7,
    "girder_depth_m": 0.95,
    "deck_thickness_m": 0.25,
    "fcu_mpa": 40.0,
    "fyk_mpa": 500.0,
    "steel_area_mm2": 4800.0,
}


def fake_solver(_: dict[str, float]) -> SolverOutputs:
    return SolverOutputs(
        permanent_moment_knm=1000.0,
        traffic_moment_knm=800.0,
        design_moment_knm=2550.0,
        resistance_moment_knm=3000.0,
    )


def _fully_verified(profile: SolverProfile) -> DeterministicSolverVerification:
    return DeterministicSolverVerification(
        solver_profile=profile,
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


def test_training_generation_is_locked_without_solver_profile() -> None:
    with pytest.raises(RuntimeError, match="solver_profile"):
        generate_training_records(EUROCODE_SAMPLE, fake_solver)


def test_training_generation_is_locked_without_structured_verification() -> None:
    with pytest.raises(RuntimeError, match="structured deterministic"):
        generate_training_records(
            [EUROCODE_SAMPLE],
            fake_solver,
            solver_profile=SolverProfile.EUROCODE_1G,
        )


def test_legacy_boolean_cannot_unlock_training_data() -> None:
    with pytest.raises(RuntimeError, match="legacy solver_verified"):
        generate_training_records(
            [EUROCODE_SAMPLE],
            fake_solver,
            solver_profile=SolverProfile.EUROCODE_1G,
            solver_verified=True,
        )


def test_incomplete_verification_reports_missing_milestones() -> None:
    verification = DeterministicSolverVerification(
        solver_profile=SolverProfile.EUROCODE_1G,
        traffic_loading=True,
        load_combinations=True,
        flexure=True,
        shear=True,
    )
    with pytest.raises(RuntimeError, match="cracking"):
        generate_training_records(
            [EUROCODE_SAMPLE],
            fake_solver,
            solver_profile=SolverProfile.EUROCODE_1G,
            verification=verification,
        )


def test_fully_verified_eurocode_solver_produces_profiled_record() -> None:
    records = generate_training_records(
        [EUROCODE_SAMPLE],
        fake_solver,
        solver_profile=SolverProfile.EUROCODE_1G,
        verification=_fully_verified(SolverProfile.EUROCODE_1G),
    )
    assert len(records) == 1
    assert records[0].solver_profile == SolverProfile.EUROCODE_1G.value
    assert records[0].fck_mpa == pytest.approx(35.0)
    assert records[0].fcu_mpa is None
    assert records[0].g_flexure_knm == pytest.approx(450.0)


def test_fully_verified_bs5400_solver_uses_cube_strength() -> None:
    records = generate_training_records(
        [BS5400_SAMPLE],
        fake_solver,
        solver_profile=SolverProfile.BS5400_BD37_01,
        verification=_fully_verified(SolverProfile.BS5400_BD37_01),
    )
    assert records[0].solver_profile == SolverProfile.BS5400_BD37_01.value
    assert records[0].fcu_mpa == pytest.approx(40.0)
    assert records[0].fck_mpa is None


def test_verification_profile_mismatch_cannot_unlock_other_code() -> None:
    verification = _fully_verified(SolverProfile.EUROCODE_1G)
    with pytest.raises(RuntimeError, match="does not match"):
        generate_training_records(
            [BS5400_SAMPLE],
            fake_solver,
            solver_profile=SolverProfile.BS5400_BD37_01,
            verification=verification,
        )


def test_bs5400_profile_requires_fcu_not_fck() -> None:
    with pytest.raises(ValueError, match="fcu_mpa"):
        generate_training_records(
            [EUROCODE_SAMPLE],
            fake_solver,
            solver_profile=SolverProfile.BS5400_BD37_01,
            verification=_fully_verified(SolverProfile.BS5400_BD37_01),
        )


def test_torsion_must_be_verified_when_it_is_in_scope() -> None:
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
        torsion_required=True,
        torsion=False,
    )
    assert not verification.ann_ready
    assert verification.missing_requirements() == ("torsion",)
