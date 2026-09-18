import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import (
    BridgeGeometry,
    MaterialProperties,
    PermanentActionModel,
    PermanentActionStage,
    PermanentLineAction,
    PermanentLineActionCategory,
    ProjectInput,
    SupportSystem,
    SurfacingLayer,
    TGirderProfile,
)
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.project_bridge import (
    SLSCombinationChoice,
    UniformPermanentLoadInput,
    girder_characteristic_permanent_effects,
    girder_deck_self_weight_kn_m,
    girder_deck_tributary_width_m,
    girder_permanent_load_segments,
    girder_permanent_moments_knm_at,
    girder_superimposed_permanent_loads_kn_m,
    internal_girder_characteristic_permanent_effects,
    internal_girder_deck_self_weight_kn_m,
    physical_girder_self_weight_kn_m,
    project_eurocode_material_input,
    project_internal_girder_combinations_verification,
    project_serviceability_from_combinations,
    run_project_internal_t_girder_verification,
    run_project_lm1_equal_share_verification,
)


def _reference_t_section() -> TGirderDesignInput:
    return TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.20,
        effective_depth_m=1.10,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )


def test_reference_project_material_input_uses_ec2_c35_45_properties() -> None:
    project = ProjectInput()
    materials = project_eurocode_material_input(project)
    assert materials.fck_mpa == pytest.approx(35.0)
    assert materials.fyk_mpa == pytest.approx(500.0)
    assert materials.ecm_mpa == pytest.approx(34077.1461992)
    assert materials.fct_eff_mpa == pytest.approx(3.2099624417)
    assert materials.es_mpa == pytest.approx(200000.0)


def test_project_material_input_respects_explicit_modulus_and_fct_eff() -> None:
    project = ProjectInput(
        materials=MaterialProperties(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            concrete_density_kn_m3=25.0,
            elastic_modulus_mpa=32000.0,
        )
    )
    materials = project_eurocode_material_input(project, fct_eff_mpa=2.5)
    assert materials.ecm_mpa == pytest.approx(32000.0)
    assert materials.fct_eff_mpa == pytest.approx(2.5)


def test_reference_project_internal_girder_deck_self_weight() -> None:
    project = ProjectInput()
    assert internal_girder_deck_self_weight_kn_m(project) == pytest.approx(10.625)




def test_reference_project_edge_girder_tributary_width_and_deck_weight() -> None:
    project = ProjectInput()
    assert girder_deck_tributary_width_m(project, girder_index=1) == pytest.approx(1.25)
    assert girder_deck_tributary_width_m(project, girder_index=7) == pytest.approx(1.25)
    assert girder_deck_tributary_width_m(project, girder_index=4) == pytest.approx(1.70)
    assert girder_deck_self_weight_kn_m(project, girder_index=1) == pytest.approx(7.8125)
    assert girder_deck_self_weight_kn_m(project, girder_index=4) == pytest.approx(10.625)


def test_reference_project_edge_girder_permanent_effects_use_edge_tributary_width() -> None:
    effects = girder_characteristic_permanent_effects(
        ProjectInput(),
        girder_index=1,
    )
    assert effects.moment_knm == pytest.approx(219.7265625)
    assert effects.shear_kn == pytest.approx(58.59375)


def test_reference_project_deck_only_characteristic_effects() -> None:
    project = ProjectInput()
    effects = internal_girder_characteristic_permanent_effects(project)
    assert effects.moment_knm == pytest.approx(298.828125)
    assert effects.shear_kn == pytest.approx(79.6875)


def test_additional_permanent_line_loads_enter_same_effects_path() -> None:
    project = ProjectInput()
    additional = UniformPermanentLoadInput(
        girder_self_weight_kn_m=3.0,
        surfacing_and_finishes_kn_m=1.0,
        assigned_barrier_and_services_kn_m=0.5,
        other_kn_m=0.5,
    )
    effects = internal_girder_characteristic_permanent_effects(
        project,
        additional=additional,
    )
    assert additional.total_additional_kn_m == pytest.approx(5.0)
    assert effects.moment_knm == pytest.approx(439.453125)
    assert effects.shear_kn == pytest.approx(117.1875)


def test_reference_project_lm1_verification_uses_7m_carriageway_and_7_girders() -> None:
    project = ProjectInput()
    result = run_project_lm1_equal_share_verification(
        project,
        movement_steps=21,
        section_stations=31,
    )
    assert result.lane_layout.carriageway_width_m == pytest.approx(7.0)
    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)
    assert len(result.girder_effects) == 7
    assert all("verification_only" in item.method for item in result.girder_effects)


def test_selected_internal_girder_combination_set_is_consistent() -> None:
    project = ProjectInput()
    sls_factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    result = project_internal_girder_combinations_verification(
        project,
        girder_index=4,
        sls_factors=sls_factors,
        movement_steps=21,
        section_stations=31,
    )

    g = result.permanent_characteristic
    q = result.traffic_characteristic
    assert g.moment_knm == pytest.approx(298.828125)
    assert q.moment_knm > 0.0
    assert q.shear_kn > 0.0

    assert result.characteristic_sls.effects.moment_knm == pytest.approx(
        g.moment_knm + q.moment_knm
    )
    assert result.frequent_sls.effects.moment_knm == pytest.approx(
        g.moment_knm + 0.75 * q.moment_knm
    )
    assert result.quasi_permanent_sls.effects.moment_knm == pytest.approx(
        g.moment_knm + 0.30 * q.moment_knm
    )
    assert result.persistent_uls.effects.moment_knm > result.characteristic_sls.effects.moment_knm
    assert "verification_only" in result.traffic_distribution_method


def test_project_serviceability_selection_tracks_explicit_combinations() -> None:
    project = ProjectInput()
    factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    combinations = project_internal_girder_combinations_verification(
        project,
        girder_index=4,
        sls_factors=factors,
        movement_steps=21,
        section_stations=31,
    )
    selection = project_serviceability_from_combinations(
        combinations,
        span_m=15.0,
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
    )

    assert selection.crack_combination_name == "EN 1990 frequent SLS"
    assert selection.deflection_combination_name == "EN 1990 quasi-permanent SLS"
    assert selection.input.service_moment_knm == pytest.approx(
        combinations.frequent_sls.effects.moment_knm
    )
    expected_udl = 8.0 * combinations.quasi_permanent_sls.effects.moment_knm / 15.0**2
    assert selection.input.equivalent_full_span_udl_kn_m == pytest.approx(expected_udl)
    assert "equivalent full-span UDL" in selection.deflection_method


def test_project_t_girder_verification_runs_end_to_end() -> None:
    project = ProjectInput()
    factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    result = run_project_internal_t_girder_verification(
        project,
        girder_index=4,
        section=_reference_t_section(),
        sls_factors=factors,
        crack_combination=SLSCombinationChoice.FREQUENT,
        deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
        crack_limit_mm=0.30,
        allowable_deflection_mm=60.0,
        movement_steps=21,
        section_stations=31,
    )

    assert "verification_only" in result.combinations.traffic_distribution_method
    assert result.materials.ecm_mpa > 0.0
    assert result.design.uls_combination.effects.moment_knm == pytest.approx(
        result.combinations.persistent_uls.effects.moment_knm
    )
    assert result.design.uls_combination.effects.shear_kn == pytest.approx(
        result.combinations.persistent_uls.effects.shear_kn
    )
    assert result.design.uls_design.flexure.resistance_knm > 0.0
    assert result.design.uls_design.shear.design_shear_kn > 0.0
    assert result.design.crack.crack_width_mm >= 0.0
    assert result.design.deflection.interpolated_deflection_mm >= 0.0


def test_project_t_girder_verification_rejects_depth_inconsistent_with_project() -> None:
    project = ProjectInput()
    factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    section = TGirderDesignInput(
        effective_flange_width_m=1.70,
        flange_thickness_m=0.175,
        web_width_m=0.30,
        total_depth_m=1.15,
        effective_depth_m=1.05,
        steel_area_mm2=6500.0,
        bar_diameter_mm=32.0,
        bar_spacing_mm=150.0,
        cover_mm=50.0,
    )
    with pytest.raises(ValueError, match="total depth"):
        run_project_internal_t_girder_verification(
            project,
            girder_index=4,
            section=section,
            sls_factors=factors,
            crack_combination=SLSCombinationChoice.FREQUENT,
            deflection_combination=SLSCombinationChoice.QUASI_PERMANENT,
            crack_limit_mm=0.30,
            allowable_deflection_mm=60.0,
            movement_steps=11,
            section_stations=21,
        )


def test_selected_girder_combination_helper_rejects_edge_girders() -> None:
    project = ProjectInput()
    sls_factors = ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30)
    with pytest.raises(ValueError, match="internal girders only"):
        project_internal_girder_combinations_verification(
            project,
            girder_index=1,
            sls_factors=sls_factors,
        )


def test_project_equal_share_verification_rejects_continuous_system() -> None:
    project = ProjectInput()
    project.geometry.support_system = SupportSystem.CONTINUOUS
    with pytest.raises(ValueError, match="simple spans only"):
        run_project_lm1_equal_share_verification(project)


def test_physical_surfacing_band_uses_exact_girder_tributary_overlap() -> None:
    project = ProjectInput(
        permanent_actions=PermanentActionModel(
            surfacing_layers=[
                SurfacingLayer(
                    name="Carriageway asphalt",
                    thickness_m=0.08,
                    density_kn_m3=23.0,
                    y_start_m=-3.5,
                    y_end_m=3.5,
                )
            ]
        )
    )

    edge = girder_superimposed_permanent_loads_kn_m(project, girder_index=1)
    internal = girder_superimposed_permanent_loads_kn_m(project, girder_index=4)

    assert edge[0] == pytest.approx(0.0)
    assert internal[0] == pytest.approx(0.08 * 23.0 * 1.70)


def test_partial_surfacing_retains_longitudinal_extent_and_exact_response() -> None:
    project = ProjectInput(
        permanent_actions=PermanentActionModel(
            surfacing_layers=[
                SurfacingLayer(
                    name="Half-span finish",
                    thickness_m=0.10,
                    density_kn_m3=20.0,
                    y_start_m=-5.5,
                    y_end_m=5.5,
                    x_start_m=0.0,
                    x_end_m=7.5,
                )
            ]
        )
    )

    segments = girder_permanent_load_segments(
        project,
        girder_index=4,
        included_stages=(PermanentActionStage.SUPERIMPOSED,),
    )
    assert len(segments) == 1
    assert segments[0].magnitude_kn_m == pytest.approx(3.4)
    assert segments[0].x_start_m == pytest.approx(0.0)
    assert segments[0].x_end_m == pytest.approx(7.5)
    summary = girder_superimposed_permanent_loads_kn_m(project, girder_index=4)
    assert summary[0] == pytest.approx(1.7)

    effects = girder_characteristic_permanent_effects(
        project,
        girder_index=4,
        included_stages=(PermanentActionStage.SUPERIMPOSED,),
    )
    assert effects.moment_knm == pytest.approx(53.7890625)
    assert effects.shear_kn == pytest.approx(19.125)


def test_permanent_moment_field_and_stage_selection_remain_explicit() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            girder_profile=TGirderProfile(
                flange_width_m=0.60,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            )
        )
    )

    segments = girder_permanent_load_segments(project, girder_index=4)
    assert {segment.stage for segment in segments} == {
        PermanentActionStage.PRECAST_GIRDER,
        PermanentActionStage.DECK_CONSTRUCTION,
    }
    moments = girder_permanent_moments_knm_at(
        project,
        girder_index=4,
        stations_m=(0.0, 7.5, 15.0),
        included_stages=(PermanentActionStage.PRECAST_GIRDER,),
    )
    assert moments == pytest.approx((0.0, 232.03125, 0.0))


def test_project_rejects_permanent_action_beyond_bridge_length() -> None:
    with pytest.raises(ValueError, match="outside the bridge length"):
        ProjectInput(
            permanent_actions=PermanentActionModel(
                line_actions=[
                    PermanentLineAction(
                        name="Overlong service",
                        magnitude_kn_m=1.0,
                        y_m=0.0,
                        category=PermanentLineActionCategory.SERVICES,
                        x_end_m=15.1,
                    )
                ]
            )
        )


def test_positioned_barriers_and_services_conserve_line_load() -> None:
    project = ProjectInput(
        permanent_actions=PermanentActionModel(
            line_actions=[
                PermanentLineAction(
                    name="Left barrier",
                    magnitude_kn_m=10.0,
                    y_m=-5.3,
                    category=PermanentLineActionCategory.BARRIER,
                ),
                PermanentLineAction(
                    name="Service duct",
                    magnitude_kn_m=4.0,
                    y_m=0.25,
                    category=PermanentLineActionCategory.SERVICES,
                ),
                PermanentLineAction(
                    name="Median fixture",
                    magnitude_kn_m=2.0,
                    y_m=0.0,
                    category=PermanentLineActionCategory.OTHER,
                ),
            ]
        )
    )

    assigned = [
        girder_superimposed_permanent_loads_kn_m(project, girder_index=index)
        for index in range(1, 8)
    ]

    assert sum(item[1] for item in assigned) == pytest.approx(14.0)
    assert sum(item[2] for item in assigned) == pytest.approx(2.0)
    assert assigned[0][1] == pytest.approx(10.0)


def test_physical_permanent_categories_reject_explicit_double_counting() -> None:
    project = ProjectInput(
        permanent_actions=PermanentActionModel(
            surfacing_layers=[
                SurfacingLayer(
                    name="Deck-wide finish",
                    thickness_m=0.05,
                    density_kn_m3=22.0,
                    y_start_m=-5.5,
                    y_end_m=5.5,
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="double count physical surfacing"):
        girder_characteristic_permanent_effects(
            project,
            girder_index=4,
            additional=UniformPermanentLoadInput(surfacing_and_finishes_kn_m=1.0),
        )



def test_physical_girder_profile_self_weight_enters_permanent_effects() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            girder_profile=TGirderProfile(
                flange_width_m=0.60,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            )
        )
    )

    assert physical_girder_self_weight_kn_m(project) == pytest.approx(8.25)
    effects = internal_girder_characteristic_permanent_effects(project)
    assert effects.moment_knm == pytest.approx(530.859375)
    assert effects.shear_kn == pytest.approx(141.5625)


def test_profile_self_weight_cannot_be_double_counted_as_explicit_line_load() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            girder_profile=TGirderProfile(
                flange_width_m=0.60,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            )
        )
    )

    with pytest.raises(ValueError, match="conflicts with the value derived"):
        internal_girder_characteristic_permanent_effects(
            project,
            additional=UniformPermanentLoadInput(
                girder_self_weight_kn_m=8.00,
            ),
        )
