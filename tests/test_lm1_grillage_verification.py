import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1LongitudinalRegion,
    LM1RemainingAreaVerificationPlacement,
    build_lm1_grillage_load_case,
    build_project_lm1_grillage_verification_model,
)


def _section(name: str) -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name=name,
        area_m2=0.50,
        torsion_constant_m4=0.04,
        iy_m4=0.03,
        iz_m4=0.08,
    )


def _reference_project(*, girder_count: int = 7, spacing_m: float = 1.70) -> ProjectInput:
    return ProjectInput(
        name="LM1 Grillage Verification",
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=girder_count,
            girder_spacing_m=spacing_m,
        ),
    )


def _reference_placements() -> tuple[
    tuple[LM1LaneVerificationPlacement, ...],
    tuple[LM1RemainingAreaVerificationPlacement, ...],
]:
    full_span = (LM1LongitudinalRegion(0.0, 15.0),)
    lanes = (
        LM1LaneVerificationPlacement(
            lane_number=1,
            y_start_m=-3.5,
            y_end_m=-0.5,
            udl_regions=full_span,
            tandem_lead_x_m=5.0,
        ),
        LM1LaneVerificationPlacement(
            lane_number=2,
            y_start_m=-0.5,
            y_end_m=2.5,
            udl_regions=full_span,
            tandem_lead_x_m=8.0,
        ),
    )
    remaining = (
        LM1RemainingAreaVerificationPlacement(
            y_start_m=2.5,
            y_end_m=3.5,
            udl_regions=full_span,
        ),
    )
    return lanes, remaining


def test_reference_7m_carriageway_generates_two_lanes_remaining_area_and_wheels() -> None:
    project = _reference_project()
    lanes, remaining = _reference_placements()
    load_case = build_lm1_grillage_load_case(
        project,
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    assert len(load_case.area_loads) == 3
    assert sorted(load.pressure_kn_m2 for load in load_case.area_loads) == pytest.approx(
        [2.5, 2.5, 9.0]
    )
    total_udl_force = sum(
        load.pressure_kn_m2
        * (load.x_end_m - load.x_start_m)
        * (load.y_end_m - load.y_start_m)
        for load in load_case.area_loads
    )
    assert total_udl_force == pytest.approx(555.0)

    assert len(load_case.point_loads) == 8
    lane_1_wheels = [load for load in load_case.point_loads if "lane 1" in load.label]
    lane_2_wheels = [load for load in load_case.point_loads if "lane 2" in load.label]
    assert len(lane_1_wheels) == 4
    assert len(lane_2_wheels) == 4
    assert {load.magnitude_kn for load in lane_1_wheels} == {150.0}
    assert {load.magnitude_kn for load in lane_2_wheels} == {100.0}
    assert sorted({load.x_m for load in lane_1_wheels}) == pytest.approx([5.0, 6.2])
    assert sorted({load.y_m for load in lane_1_wheels}) == pytest.approx([-3.0, -1.0])
    assert sorted({load.x_m for load in lane_2_wheels}) == pytest.approx([8.0, 9.2])
    assert sorted({load.y_m for load in lane_2_wheels}) == pytest.approx([0.0, 2.0])


def test_lane_numbering_can_be_reordered_transversely_without_hidden_assumption() -> None:
    project = _reference_project()
    full_span = (LM1LongitudinalRegion(0.0, 15.0),)
    load_case = build_lm1_grillage_load_case(
        project,
        lane_placements=(
            LM1LaneVerificationPlacement(2, -3.5, -0.5, full_span, 5.0),
            LM1LaneVerificationPlacement(1, -0.5, 2.5, full_span, 5.0),
        ),
        remaining_area_placements=(
            LM1RemainingAreaVerificationPlacement(2.5, 3.5, full_span),
        ),
    )

    lane_1_y = sorted({load.y_m for load in load_case.point_loads if "lane 1" in load.label})
    lane_2_y = sorted({load.y_m for load in load_case.point_loads if "lane 2" in load.label})
    assert lane_1_y == pytest.approx([0.0, 2.0])
    assert lane_2_y == pytest.approx([-3.0, -1.0])


def test_carriageway_offset_moves_lm1_transverse_snapshot_with_roadway() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            carriageway_offset_m=0.5,
            girder_count=7,
            girder_spacing_m=1.70,
        )
    )
    full_span = (LM1LongitudinalRegion(0.0, 15.0),)
    load_case = build_lm1_grillage_load_case(
        project,
        lane_placements=(
            LM1LaneVerificationPlacement(1, -3.0, 0.0, full_span, 5.0),
            LM1LaneVerificationPlacement(2, 0.0, 3.0, full_span, 5.0),
        ),
        remaining_area_placements=(
            LM1RemainingAreaVerificationPlacement(3.0, 4.0, full_span),
        ),
    )
    assert min(load.y_start_m for load in load_case.area_loads) == pytest.approx(-3.0)
    assert max(load.y_end_m for load in load_case.area_loads) == pytest.approx(4.0)


def test_invalid_lm1_transverse_coverage_is_rejected() -> None:
    project = _reference_project()
    full_span = (LM1LongitudinalRegion(0.0, 15.0),)
    with pytest.raises(ValueError, match="contiguous"):
        build_lm1_grillage_load_case(
            project,
            lane_placements=(
                LM1LaneVerificationPlacement(1, -3.5, -0.5, full_span, 5.0),
                LM1LaneVerificationPlacement(2, 0.0, 3.0, full_span, 5.0),
            ),
            remaining_area_placements=(
                LM1RemainingAreaVerificationPlacement(3.0, 4.0, full_span),
            ),
        )


def test_lm1_snapshot_builds_full_grillage_for_eight_girders() -> None:
    project = _reference_project(girder_count=8, spacing_m=1.40)
    lanes, remaining = _reference_placements()
    model = build_project_lm1_grillage_verification_model(
        project,
        longitudinal_sections_by_span=(_section("Longitudinal"),),
        transverse_section=_section("Transverse"),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    assert model.metadata["girder_count"] == "8"
    assert model.metadata["traffic_model"].startswith("EN 1991-2 LM1")
    assert model.metadata["lane_placement"].startswith("explicit transverse strips")
    assert any(node.x_m == pytest.approx(5.0) for node in model.nodes)
    assert any(node.x_m == pytest.approx(6.2) for node in model.nodes)
    assert any(node.x_m == pytest.approx(8.0) for node in model.nodes)
    assert any(node.x_m == pytest.approx(9.2) for node in model.nodes)
