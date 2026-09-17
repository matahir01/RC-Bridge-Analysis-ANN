import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import (
    build_governing_lm1_search_verification_packages,
    generate_lm1_search_placements,
    run_project_native_lm1_grillage_search,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Automated LM1 search",
        geometry=BridgeGeometry(
            span_lengths_m=[15.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=8,
            girder_spacing_m=1.40,
        ),
    )


def _longitudinal() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.025,
        iy_m4=0.05,
        iz_m4=0.08,
    )


def _transverse() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.012,
        iy_m4=0.018,
        iz_m4=0.025,
    )


def test_search_generator_moves_remainder_to_both_edges_and_permutes_lane_numbers() -> None:
    placements = generate_lm1_search_placements(_project(), longitudinal_step_m=15.0)

    transverse_signatures = {
        (
            tuple(
                (lane.lane_number, lane.y_start_m, lane.y_end_m)
                for lane in placement.lane_placements
            ),
            tuple(
                (strip.y_start_m, strip.y_end_m)
                for strip in placement.remaining_area_placements
            ),
        )
        for placement in placements
    }

    # 7 m carriageway -> two 3 m lanes plus 1 m remaining area.
    # Two remainder edges x two permutations of lane 1/lane 2.
    assert len(transverse_signatures) == 4
    assert any(signature[1] == ((-3.5, -2.5),) for signature in transverse_signatures)
    assert any(signature[1] == ((2.5, 3.5),) for signature in transverse_signatures)
    assert any(signature[0][0][0] == 1 for signature in transverse_signatures)
    assert any(signature[0][0][0] == 2 for signature in transverse_signatures)


def test_search_envelopes_moment_shear_and_torsion_independently_for_every_girder() -> None:
    result = run_project_native_lm1_grillage_search(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=7.5,
    )

    assert result.evaluated_case_count > 4
    assert len(result.girders) == 8
    assert [girder.girder_index for girder in result.girders] == list(range(1, 9))

    for girder in result.girders:
        case_effects = [
            case.girder_envelope.details[girder.girder_index - 1]
            for case in result.cases
        ]
        assert girder.moment_knm.value == pytest.approx(
            max(item.effects.moment_knm for item in case_effects)
        )
        assert girder.shear_kn.value == pytest.approx(
            max(item.effects.shear_kn for item in case_effects)
        )
        assert girder.torsion_knm.value == pytest.approx(
            max(item.effects.torsion_knm for item in case_effects)
        )
        assert girder.moment_knm.case_id in {
            case.placement.case_id for case in result.cases
        }
        assert girder.shear_kn.case_id in {
            case.placement.case_id for case in result.cases
        }
        assert girder.torsion_knm.case_id in {
            case.placement.case_id for case in result.cases
        }


def test_governing_cases_can_be_exported_as_identical_midas_and_staad_models() -> None:
    result = run_project_native_lm1_grillage_search(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=15.0,
    )
    packages = build_governing_lm1_search_verification_packages(result)

    assert set(packages) == set(result.governing_case_ids)
    assert packages
    for package in packages.values():
        assert "*NODE" in package.midas_mct
        assert "MEMBER INCIDENCES" in package.staad_std
