import math

from rc_bridge.analysis.loads import PointLoad, deck_self_weight_per_girder_kn_m
from rc_bridge.analysis.point_loads import moment_envelope, section_response, simply_supported_reactions
from rc_bridge.core.sections import RectangularSection, TSection


def test_deck_self_weight_for_reference_spacing() -> None:
    # 250 mm deck, 1.70 m tributary width, 25 kN/m3 concrete.
    assert deck_self_weight_per_girder_kn_m(0.25, 1.70, 25.0) == 10.625


def test_central_point_load_reactions_and_moment() -> None:
    span = 10.0
    load = PointLoad(100.0, 5.0)
    ra, rb = simply_supported_reactions(span, [load])
    assert math.isclose(ra, 50.0)
    assert math.isclose(rb, 50.0)

    response = section_response(span, [load], 5.0)
    assert math.isclose(response.moment_knm, 250.0)

    max_m, x = moment_envelope(span, [load], stations=101)
    assert math.isclose(max_m, 250.0)
    assert math.isclose(x, 5.0)


def test_rectangular_section_properties() -> None:
    section = RectangularSection(width_m=0.3, depth_m=0.9)
    assert math.isclose(section.area_m2, 0.27)
    assert math.isclose(section.second_moment_m4, 0.3 * 0.9**3 / 12.0)


def test_t_section_properties_are_positive() -> None:
    section = TSection(
        flange_width_m=1.70,
        flange_thickness_m=0.25,
        web_width_m=0.30,
        total_depth_m=1.20,
    )
    assert section.area_m2 > 0
    assert 0 < section.centroid_from_top_m < section.total_depth_m
    assert section.second_moment_m4 > 0
