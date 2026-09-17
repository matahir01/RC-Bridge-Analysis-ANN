from rc_bridge.analysis.girder_effects import distribute_effects_to_girders
from rc_bridge.analysis.transverse import equal_distribution
from rc_bridge.codes.eurocode.lm1_effects import lm1_lane_simple_span_envelope


def test_lm1_lane_envelope_positive_and_independent_positions():
    result = lm1_lane_simple_span_envelope(
        span_m=15.0,
        lane_number=1,
        lane_width_m=3.0,
        movement_steps=81,
        section_stations=101,
    )
    assert result.max_moment_knm > 0.0
    assert result.max_abs_shear_kn > 0.0
    assert 0.0 <= result.moment_position_m <= 15.0
    assert 0.0 <= result.shear_position_m <= 15.0
    assert result.moment_governing_lead_position_m >= 0.0
    assert result.shear_governing_lead_position_m >= 0.0


def test_equal_distribution_maps_global_effects_to_seven_girders():
    distribution = equal_distribution(7)
    effects = distribute_effects_to_girders(700.0, 350.0, distribution)
    assert len(effects) == 7
    assert all(abs(item.moment_knm - 100.0) < 1e-9 for item in effects)
    assert all(abs(item.shear_kn - 50.0) < 1e-9 for item in effects)
    assert abs(sum(item.moment_knm for item in effects) - 700.0) < 1e-9
    assert abs(sum(item.shear_kn for item in effects) - 350.0) < 1e-9
