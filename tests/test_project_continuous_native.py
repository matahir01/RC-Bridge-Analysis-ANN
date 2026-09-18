import pytest

from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import (
    BridgeGeometry,
    PermanentActionStage,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
)
from rc_bridge.workflow.eurocode_layered_girder import LayeredGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.project_construction import PermanentGrillageStageInput
from rc_bridge.workflow.project_continuous_detailing import (
    ContinuousLongitudinalDetailingInput,
    run_project_continuous_native_detailing,
)
from rc_bridge.workflow.project_continuous_design import (
    ContinuousShearDesignInput,
    NegativeSupportRectangularDesignInput,
    PositiveCompositeTSectionDesignInput,
    run_continuous_eurocode_uls_design,
)
from rc_bridge.workflow.project_continuous_native import (
    run_project_continuous_native_lm1_envelope,
)
from rc_bridge.workflow.project_continuous_native_deflection import (
    run_project_continuous_native_service_deflection,
)
from rc_bridge.workflow.project_continuous_native_fatigue import (
    ContinuousTopSteelFatigueInput,
    run_project_continuous_native_fatigue,
)
from rc_bridge.workflow.project_continuous_native_torsion import (
    check_project_continuous_native_matched_shear_torsion,
)
from rc_bridge.workflow.project_native_fatigue import (
    NativeFLM3FatigueDesignInput,
    run_project_native_flm3_continuous_grillage_search,
)
from rc_bridge.workflow.project_torsion import TorsionCellInput


def _project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.40, depth_m=0.95),
        )
    )


def _crossbeam() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="verified construction crossbeam",
        area_m2=0.25,
        torsion_constant_m4=0.01,
        iy_m4=0.02,
        iz_m4=0.03,
    )


def _stages() -> tuple[PermanentGrillageStageInput, ...]:
    return (
        PermanentGrillageStageInput(
            stage=PermanentActionStage.PRECAST_GIRDER,
            basis="unpropped precast girders with verified crossbeams",
            transverse_section=_crossbeam(),
        ),
        PermanentGrillageStageInput(
            stage=PermanentActionStage.DECK_CONSTRUCTION,
            basis="wet deck on unchanged continuity with verified crossbeams",
            transverse_section=_crossbeam(),
        ),
        PermanentGrillageStageInput(
            stage=PermanentActionStage.SUPERIMPOSED,
            basis="final composite bridge",
        ),
    )


def _run(girder_index: int = 2):
    return run_project_continuous_native_lm1_envelope(
        _project(),
        girder_index=girder_index,
        construction_stages=_stages(),
        unchanged_supports_and_continuity_basis=(
            "two-span continuity and supports active throughout the analysed sequence"
        ),
        sls_factors=ServiceabilityPsiFactors(
            psi1_traffic=0.75,
            psi2_traffic=0.0,
        ),
        stations_per_span=3,
        longitudinal_step_m=10.0,
        max_exhaustive_tandem_combinations=20,
    )


def test_native_continuous_envelope_integrates_staged_g_and_full_width_lm1() -> None:
    result = _run()

    assert result.construction.final_response.total_applied_vertical_load_kn < 0.0
    assert result.traffic.cases
    assert result.envelope.max_positive_uls_moment_knm > 0.0
    assert result.envelope.min_negative_uls_moment_knm < 0.0
    assert result.envelope.max_abs_uls_shear_kn > 0.0
    assert "native full-width" in result.envelope.traffic_distribution_method
    assert any(abs(trace.global_position_m - 10.0) <= 1.0e-9 for trace in result.trace)
    assert any(trace.traffic_minimum_moment_knm < 0.0 for trace in result.trace)


def test_native_continuous_envelope_retains_both_internal_support_sides() -> None:
    result = _run()
    support = [
        station
        for station in result.envelope.stations
        if abs(station.global_position_m - 10.0) <= 1.0e-9
    ]
    assert len(support) == 2
    assert {item.section_side for item in support} == {"left", "right"}
    assert support[0].permanent_moment_knm == pytest.approx(
        support[1].permanent_moment_knm, rel=1.0e-8
    )


def test_existing_continuous_uls_design_accepts_native_envelope() -> None:
    result = run_continuous_eurocode_uls_design(
        _run().envelope,
        positive_section=PositiveCompositeTSectionDesignInput(
            effective_flange_width_m=1.50,
            flange_thickness_m=0.175,
            web_width_m=0.40,
            effective_depth_from_top_m=1.10,
            provided_bottom_steel_area_mm2=7000.0,
        ),
        negative_section=NegativeSupportRectangularDesignInput(
            compression_width_m=0.40,
            effective_depth_from_bottom_m=1.10,
            provided_top_steel_area_mm2=6500.0,
        ),
        shear_section=ContinuousShearDesignInput(
            web_width_m=0.40,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
            provided_asw_per_s_mm2_per_m=1600.0,
        ),
        fck_mpa=35.0,
        fyk_mpa=500.0,
    )

    assert result.positive_design_moment_knm > 0.0
    assert result.negative_design_moment_knm > 0.0
    assert result.design_shear_kn > 0.0



def test_native_continuous_service_deflection_combines_staged_g_and_lm1() -> None:
    production = _run()
    result = run_project_continuous_native_service_deflection(
        _project(),
        construction=production.construction,
        traffic=production.traffic,
        girder_index=2,
        traffic_factor=0.75,
        allowable_deflection_mm=40.0,
    )

    assert result.calculated_max_abs_deflection_mm > 0.0
    assert result.calculated_max_abs_deflection_mm >= (
        result.permanent_only_max_abs_deflection_mm
    )
    assert 0.0 < result.governing_global_position_m < 20.0
    assert result.utilization == pytest.approx(
        result.calculated_max_abs_deflection_mm / 40.0
    )
    assert result.g_deflection_mm == pytest.approx(
        40.0 - result.calculated_max_abs_deflection_mm
    )
    assert "interior displacement extrema" in result.status


def test_native_continuous_zero_traffic_factor_returns_permanent_only() -> None:
    production = _run()
    result = run_project_continuous_native_service_deflection(
        _project(),
        construction=production.construction,
        traffic=production.traffic,
        girder_index=2,
        traffic_factor=0.0,
        allowable_deflection_mm=40.0,
    )

    assert result.governing_case_id is None
    assert result.calculated_max_abs_deflection_mm == pytest.approx(
        result.permanent_only_max_abs_deflection_mm,
        rel=1.0e-12,
        abs=1.0e-12,
    )



def test_continuous_native_shear_torsion_keeps_v_and_t_colocated() -> None:
    production = _run(girder_index=1)
    result = check_project_continuous_native_matched_shear_torsion(
        _project(),
        production=production,
        section=ContinuousShearDesignInput(
            web_width_m=0.40,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
            provided_asw_per_s_mm2_per_m=1600.0,
        ),
        torsion_cell=TorsionCellInput(
            ak_m2=0.10,
            uk_m=1.40,
            tef_m=0.15,
        ),
    )

    assert result.evaluated_points
    assert result.governing_torsion.design_torsion_knm >= 0.0
    assert result.governing_interaction.interaction.utilization >= 0.0
    point = result.governing_interaction
    assert point.member_end in {"I", "J"}
    assert point.side in {"left", "right"}
    assert point.gamma_g in {1.0, 1.35}
    assert "same section" in result.status



def test_continuous_native_fatigue_checks_top_and_bottom_steel_through_reversal() -> None:
    production = _run()
    final_stage = production.construction.stages[-1].input
    fatigue_search = run_project_native_flm3_continuous_grillage_search(
        _project(),
        transverse_stations_m=production.design_stations_m,
        longitudinal_sections_by_span=final_stage.longitudinal_sections_by_span,
        transverse_section=final_stage.transverse_section,
        stiffness_modifiers=final_stage.stiffness_modifiers,
        vehicle_centre_y_m=0.0,
        movement_step_m=10.0,
        section_step_m=5.0,
    )
    result = run_project_continuous_native_fatigue(
        _project(),
        production=production,
        fatigue_search=fatigue_search,
        girder_index=2,
        bottom_section=LayeredGirderDesignInput(
            composite_slab_width_m=1.50,
            effective_depth_m=1.10,
            steel_area_mm2=7000.0,
            bar_diameter_mm=32.0,
            bar_spacing_mm=150.0,
            cover_mm=50.0,
        ),
        top_section=ContinuousTopSteelFatigueInput(
            effective_deck_width_m=1.50,
            steel_area_mm2=6500.0,
            steel_depth_from_bottom_m=1.10,
        ),
        fatigue_design=NativeFLM3FatigueDesignInput(
            lambda_s=0.90,
            characteristic_fatigue_strength_mpa=162.5,
        ),
    )

    assert result.stations
    assert result.governing_bottom_reinforcement.bottom_reinforcement.utilization >= 0.0
    assert result.governing_top_reinforcement.top_reinforcement.utilization >= 0.0
    assert any(item.minimum_total_moment_knm < 0.0 for item in result.stations)
    assert any(item.maximum_total_moment_knm > 0.0 for item in result.stations)
    support_sides = {
        item.side
        for item in result.stations
        if abs(item.x_m - 10.0) <= 1.0e-9
    }
    assert support_sides == {"left", "right"}
    assert "moment jumps" in result.status



def test_continuous_native_detailing_generates_top_bottom_and_link_zones() -> None:
    production = _run()
    result = run_project_continuous_native_detailing(
        _project(),
        production=production,
        detailing=ContinuousLongitudinalDetailingInput(
            bottom_composite_slab_width_m=1.50,
            bottom_effective_depth_from_top_m=1.10,
            bottom_cover_mm=50.0,
            top_effective_deck_width_m=1.50,
            top_effective_depth_from_bottom_m=1.10,
            top_cover_mm=50.0,
        ),
    )

    assert result.bottom_zones
    assert result.top_zones
    assert result.link_zones
    assert result.bottom_continuous_core.bar_count >= 2
    assert result.top_continuous_core.bar_count >= 2
    assert all(
        zone.arrangement.bar_count >= zone.continuous_bar_count
        for zone in (*result.bottom_zones, *result.top_zones)
    )
    assert all(
        0.0 <= zone.anchored_start_m <= zone.x_start_m
        and zone.x_end_m <= zone.anchored_end_m <= 20.0
        for zone in (*result.bottom_zones, *result.top_zones)
    )
    assert any(item.positive_design_moment_knm > 0.0 for item in result.stations)
    assert any(item.negative_design_moment_knm > 0.0 for item in result.stations)


def test_continuous_detailing_can_include_matched_torsion_cage() -> None:
    production = _run(girder_index=1)
    torsion = check_project_continuous_native_matched_shear_torsion(
        _project(),
        production=production,
        section=ContinuousShearDesignInput(
            web_width_m=0.40,
            effective_depth_m=1.05,
            longitudinal_steel_area_mm2=6500.0,
            provided_asw_per_s_mm2_per_m=1600.0,
        ),
        torsion_cell=TorsionCellInput(
            ak_m2=0.10,
            uk_m=1.40,
            tef_m=0.15,
        ),
    )
    result = run_project_continuous_native_detailing(
        _project(),
        production=production,
        detailing=ContinuousLongitudinalDetailingInput(
            bottom_composite_slab_width_m=1.50,
            bottom_effective_depth_from_top_m=1.10,
            bottom_cover_mm=50.0,
            top_effective_deck_width_m=1.50,
            top_effective_depth_from_bottom_m=1.10,
            top_cover_mm=50.0,
        ),
        torsion=torsion,
    )

    assert result.torsion_cage is not None
    assert result.torsion_cage.links.satisfies_shear
    assert result.torsion_cage.links.satisfies_torsion
