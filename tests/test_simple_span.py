from rc_bridge.analysis.simple_span import udl_simple_span


def test_udl_simple_span():
    result = udl_simple_span(span_m=10.0, udl_kn_m=20.0)
    assert result.reaction_left_kn == 100.0
    assert result.reaction_right_kn == 100.0
    assert result.max_moment_knm == 250.0
    assert result.max_shear_kn == 100.0
