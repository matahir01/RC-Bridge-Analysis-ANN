import pytest

from rc_bridge.analysis.elastic_deflection import (
    simply_supported_deflection_from_moment_diagram_mm,
)
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import (
    build_governing_lm1_search_verification_packages,
    generate_lm1_search_placements,
    native_lm1_girder_moment_diagram,
    run_project_native_lm1_grillage_search,
)
from rc_bridge.workflow.project_bridge import (
    ProjectGirderCombinationSet,
    SLSCombinationChoice,
    girder_permanent_moments_knm_at,
)
from rc_bridge.workflow.project_native_lm1 import native_lm1_service_moment_diagram


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


def _continuous_project() -> ProjectInput:
    return ProjectInput(
        name="Continuous automated LM1 search",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            deck_width_m=11.0,
            carriageway_width_m=7.0,
            girder_count=8,
            girder_spacing_m=1.40,
            support_system=SupportSystem.CONTINUOUS,
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


def test_search_generator_positions_lane_tandems_independently() -> None:
    placements = generate_lm1_search_placements(_project(), longitudinal_step_m=15.0)

    assert any(
        len({position for _, position in placement.tandem_lead_positions_m}) > 1
        for placement in placements
    )
    assert any(placement.tandem_lead_x_m is None for placement in placements)
    assert any(placement.tandem_lead_x_m is not None for placement in placements)


def test_continuous_search_generates_spanwise_udl_patterns() -> None:
    placements = generate_lm1_search_placements(
        _continuous_project(),
        longitudinal_step_m=20.0,
    )
    signatures = {
        tuple((region.x_start_m, region.x_end_m) for region in placement.common_udl_regions)
        for placement in placements
    }

    assert signatures == {
        ((0.0, 10.0),),
        ((10.0, 20.0),),
        ((0.0, 10.0), (10.0, 20.0)),
    }


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
    assert result.tandem_combinations_exhaustive
    assert result.udl_pattern_count == 1
    assert result.search_strategy == "exhaustive-independent-tandem+full-length-udl"
    assert len(result.deflections) == 8

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
        deflection = result.deflection_for_girder(girder.girder_index)
        assert deflection.value_mm >= 0.0
        assert deflection.case_id in {case.placement.case_id for case in result.cases}

        diagram = native_lm1_girder_moment_diagram(
            result,
            girder_index=girder.girder_index,
            case_id=deflection.case_id,
        )
        assert diagram.stations_m[0] == pytest.approx(0.0)
        assert diagram.stations_m[-1] == pytest.approx(15.0)
        case = next(
            item for item in result.cases if item.placement.case_id == deflection.case_id
        )
        beam = next(
            item
            for item in case.model.beams
            if abs(
                next(node for node in case.model.nodes if node.node_id == item.node_i).y_m
                - girder.y_m
            )
            <= 1.0e-9
            and abs(
                next(node for node in case.model.nodes if node.node_id == item.node_j).y_m
                - girder.y_m
            )
            <= 1.0e-9
        )
        material = next(
            item for item in case.model.materials if item.material_id == beam.material_id
        )
        section = next(
            item for item in case.model.sections if item.section_id == beam.section_id
        )
        integrated = simply_supported_deflection_from_moment_diagram_mm(
            stations_m=diagram.stations_m,
            moments_knm=diagram.moments_knm,
            elastic_modulus_mpa=material.elastic_modulus_kn_m2 / 1000.0,
            second_moment_mm4=section.iy_m4 * 1.0e12,
        )
        assert integrated.maximum_absolute_deflection_mm == pytest.approx(
            deflection.value_mm,
            rel=1.0e-8,
            abs=1.0e-9,
        )


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


def test_native_service_deflection_combines_permanent_and_colocated_traffic_fields() -> None:
    project = _project()
    result = run_project_native_lm1_grillage_search(
        project,
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=15.0,
    )
    girder = result.girders[3]
    permanent = LoadEffects(moment_knm=300.0, shear_kn=80.0)
    traffic = LoadEffects(
        moment_knm=girder.moment_knm.value,
        shear_kn=girder.shear_kn.value,
        torsion_knm=girder.torsion_knm.value,
    )
    factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    combinations = ProjectGirderCombinationSet(
        girder_index=4,
        permanent_characteristic=permanent,
        traffic_characteristic=traffic,
        persistent_uls=persistent_uls(permanent, traffic),
        characteristic_sls=characteristic_sls(permanent, traffic),
        frequent_sls=frequent_sls(permanent, traffic, factors),
        quasi_permanent_sls=quasi_permanent_sls(permanent, traffic, factors),
        traffic_distribution_method="native test",
    )

    traced = native_lm1_service_moment_diagram(
        project,
        result,
        combinations=combinations,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        span_m=15.0,
        benchmark_source="software-test fixture",
    )

    assert traced is not None
    diagram, service_moment = traced
    governing = result.deflection_for_girder(4)
    traffic_diagram = native_lm1_girder_moment_diagram(
        result,
        girder_index=4,
        case_id=governing.case_id,
    )
    permanent_moments = girder_permanent_moments_knm_at(
        project,
        girder_index=4,
        stations_m=diagram.stations_m,
    )
    for permanent_moment, actual, traffic_moment in zip(
        permanent_moments,
        diagram.moments_knm,
        traffic_diagram.moments_knm,
        strict=True,
    ):
        expected = permanent_moment - 0.30 * traffic_moment
        assert actual == pytest.approx(expected)
    assert min(traffic_diagram.moments_knm) < 0.0
    assert max(diagram.moments_knm) > max(permanent_moments)
    assert service_moment == pytest.approx(max(abs(value) for value in diagram.moments_knm))
    assert f"case {governing.case_id}" in diagram.source
    assert "software-test fixture" in diagram.source
