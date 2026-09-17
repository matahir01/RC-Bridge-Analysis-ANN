import pytest

from rc_bridge.design.bs5400_detailing import check_beam_detailing_bs5400


def test_bs5400_beam_detailing_checks_minimum_maximum_and_spacing() -> None:
    result = check_beam_detailing_bs5400(
        average_breadth_excluding_compression_flange_m=0.30,
        effective_depth_m=1.10,
        gross_concrete_area_m2=0.45,
        provided_main_steel_mm2=6500.0,
        reinforcement_grade_mpa=460.0,
        side_face_depth_m=0.95,
        side_face_breadth_m=0.30,
        provided_side_face_steel_each_face_mm2=200.0,
        maximum_aggregate_size_mm=20.0,
        provided_clear_bar_spacing_mm=40.0,
        provided_tension_bar_spacing_mm=200.0,
        provided_link_spacing_mm=300.0,
    )

    assert result.minimum_main_steel_mm2 == pytest.approx(495.0)
    assert result.maximum_main_steel_mm2 == pytest.approx(18000.0)
    assert result.minimum_side_face_steel_each_face_mm2 == pytest.approx(165.0)
    assert result.minimum_clear_bar_spacing_mm == pytest.approx(25.0)
    assert result.maximum_link_spacing_mm == pytest.approx(825.0)
    assert result.passes


def test_bs5400_detailing_flags_insufficient_side_face_steel() -> None:
    result = check_beam_detailing_bs5400(
        average_breadth_excluding_compression_flange_m=0.30,
        effective_depth_m=1.10,
        gross_concrete_area_m2=0.45,
        provided_main_steel_mm2=6500.0,
        reinforcement_grade_mpa=460.0,
        side_face_depth_m=0.95,
        side_face_breadth_m=0.30,
        provided_side_face_steel_each_face_mm2=100.0,
        maximum_aggregate_size_mm=20.0,
        provided_clear_bar_spacing_mm=40.0,
        provided_tension_bar_spacing_mm=200.0,
        provided_link_spacing_mm=300.0,
    )
    assert result.side_face_reinforcement_required
    assert not result.side_face_steel_ok
    assert not result.passes


def test_bs5400_minimum_main_steel_does_not_silently_map_grade_500() -> None:
    with pytest.raises(ValueError, match="Grade 460 or Grade 250"):
        check_beam_detailing_bs5400(
            average_breadth_excluding_compression_flange_m=0.30,
            effective_depth_m=1.10,
            gross_concrete_area_m2=0.45,
            provided_main_steel_mm2=6500.0,
            reinforcement_grade_mpa=500.0,
            side_face_depth_m=0.95,
            side_face_breadth_m=0.30,
            provided_side_face_steel_each_face_mm2=200.0,
            maximum_aggregate_size_mm=20.0,
            provided_clear_bar_spacing_mm=40.0,
            provided_tension_bar_spacing_mm=200.0,
            provided_link_spacing_mm=300.0,
        )
