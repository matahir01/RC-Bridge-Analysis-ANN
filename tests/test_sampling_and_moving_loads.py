import math

from rc_bridge.analysis.moving_loads import AxleTrain, moving_train_max_moment
from rc_bridge.research.sampling import VariableRange, latin_hypercube_samples


def test_single_axle_moving_load_matches_closed_form() -> None:
    span = 10.0
    train = AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,))
    max_m, x, lead = moving_train_max_moment(
        span,
        train,
        movement_steps=101,
        section_stations=101,
    )
    # A single moving point load has maximum sagging moment P*L/4 at midspan.
    assert math.isclose(max_m, 250.0, rel_tol=1e-12)
    assert math.isclose(x, 5.0, abs_tol=0.11)
    assert math.isclose(lead, 5.0, abs_tol=0.11)


def test_lhs_samples_respect_bounds_and_seed() -> None:
    variables = [
        VariableRange("span_m", 10.0, 25.0),
        VariableRange("fck_mpa", 25.0, 60.0),
    ]
    a = latin_hypercube_samples(variables, sample_count=20, seed=42)
    b = latin_hypercube_samples(variables, sample_count=20, seed=42)
    assert a == b
    assert len(a) == 20
    assert all(10.0 <= row["span_m"] <= 25.0 for row in a)
    assert all(25.0 <= row["fck_mpa"] <= 60.0 for row in a)
