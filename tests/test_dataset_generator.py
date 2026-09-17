import pytest
from rc_bridge.research.generator import SolverOutputs, generate_training_records


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


def test_training_generation_is_locked_until_solver_is_verified() -> None:
    with pytest.raises(RuntimeError):
        generate_training_records([SAMPLE], fake_solver)


def test_verified_solver_produces_limit_state_record() -> None:
    records = generate_training_records([SAMPLE], fake_solver, solver_verified=True)
    assert len(records) == 1
    assert records[0].g_flexure_knm == pytest.approx(450.0)
