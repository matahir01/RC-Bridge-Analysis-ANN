import pytest

from rc_bridge.research.generator import SolverOutputs, generate_training_records
from rc_bridge.research.verification import DeterministicSolverVerification

SAMPLE = {
    "span_m": 15.0,
    "girder_spacing_m": 1.7,
    "girder_depth_m": 0.95,
    "deck_thickness_m": 0.25,
    "fck_mpa": 35.0,
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


def _fully_verified() -> DeterministicSolverVerification:
    return DeterministicSolverVerification(
        flexure=True,
        shear=True,
        cracking=True,
        deflection=True,
        fatigue=True,
        detailing=True,
        transverse_distribution=True,
        independent_benchmark=True,
    )


def test_training_generation_is_locked_without_structured_verification() -> None:
    with pytest.raises(RuntimeError, match="structured deterministic"):
        generate_training_records([SAMPLE], fake_solver)


def test_legacy_boolean_cannot_unlock_training_data() -> None:
    with pytest.raises(RuntimeError, match="legacy solver_verified"):
        generate_training_records([SAMPLE], fake_solver, solver_verified=True)


def test_incomplete_verification_reports_missing_milestones() -> None:
    verification = DeterministicSolverVerification(
        flexure=True,
        shear=True,
    )
    with pytest.raises(RuntimeError, match="cracking"):
        generate_training_records(
            [SAMPLE],
            fake_solver,
            verification=verification,
        )


def test_fully_verified_solver_produces_limit_state_record() -> None:
    records = generate_training_records(
        [SAMPLE],
        fake_solver,
        verification=_fully_verified(),
    )
    assert len(records) == 1
    assert records[0].g_flexure_knm == pytest.approx(450.0)


def test_torsion_must_be_verified_when_it_is_in_scope() -> None:
    verification = DeterministicSolverVerification(
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
