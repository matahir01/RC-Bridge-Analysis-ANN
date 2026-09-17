import pytest

from rc_bridge.analysis.grillage_effects import native_grillage_traffic_envelope
from rc_bridge.analysis.grillage_solver import solve_vertical_grillage
from rc_bridge.codes.eurocode.combinations import ServiceabilityPsiFactors
from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.export.verification_model import VerificationLoadCase, VerificationModel
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillagePointLoad,
    GrillageSectionProperties,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)
from rc_bridge.workflow.project_grillage import project_internal_girder_combinations_from_grillage


def _project() -> ProjectInput:
    return ProjectInput(
        name="native transverse distribution",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0],
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
        ),
    )


def _longitudinal_section() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Longitudinal",
        area_m2=0.45,
        torsion_constant_m4=0.02,
        iy_m4=0.04,
        iz_m4=0.05,
    )


def _transverse_section() -> GrillageSectionProperties:
    return GrillageSectionProperties(
        name="Transverse",
        area_m2=0.25,
        torsion_constant_m4=0.01,
        iy_m4=0.015,
        iz_m4=0.02,
    )


def _model(load_case: GrillageVerificationLoadCase) -> VerificationModel:
    return build_project_grillage_verification_model(
        _project(),
        longitudinal_sections_by_span=(_longitudinal_section(),),
        transverse_section=_transverse_section(),
        transverse_stations_m=(5.0,),
        load_case=load_case,
    )


def test_symmetric_native_grillage_load_produces_mirrored_girder_envelopes() -> None:
    model = _model(
        GrillageVerificationLoadCase(
            name="symmetric pressure",
            area_loads=(GrillageAreaLoad(0.0, 10.0, -2.5, 2.5, 2.0),),
        )
    )
    analysis = solve_vertical_grillage(model)
    native = native_grillage_traffic_envelope(model, analysis)

    assert native.envelope.girder_count == 3
    left = native.envelope.effect_for_girder(1)
    centre = native.envelope.effect_for_girder(2)
    right = native.envelope.effect_for_girder(3)

    assert left.moment_knm == pytest.approx(right.moment_knm)
    assert left.shear_kn == pytest.approx(right.shear_kn)
    assert left.torsion_knm == pytest.approx(right.torsion_knm)
    assert centre.moment_knm > 0.0
    assert native.details[0].y_m == pytest.approx(-2.0)
    assert native.details[1].y_m == pytest.approx(0.0)
    assert native.details[2].y_m == pytest.approx(2.0)
    assert native.envelope.metadata.source_software == "RC-Bridge native vertical grillage"


def test_eccentric_wheel_shifts_native_girder_demand_toward_loaded_side() -> None:
    model = _model(
        GrillageVerificationLoadCase(
            name="right girder wheel",
            point_loads=(GrillagePointLoad(5.0, 2.0, 100.0, "right girder wheel"),),
        )
    )
    analysis = solve_vertical_grillage(model)
    native = native_grillage_traffic_envelope(model, analysis)

    left = native.envelope.effect_for_girder(1)
    centre = native.envelope.effect_for_girder(2)
    right = native.envelope.effect_for_girder(3)

    assert right.moment_knm > centre.moment_knm
    assert centre.moment_knm > left.moment_knm
    assert right.shear_kn > left.shear_kn
    assert right.moment_knm > 0.0


def test_native_envelope_feeds_existing_project_combination_workflow() -> None:
    project = _project()
    model = _model(
        GrillageVerificationLoadCase(
            name="native characteristic traffic",
            point_loads=(GrillagePointLoad(5.0, 0.0, 100.0, "centre wheel"),),
        )
    )
    native = native_grillage_traffic_envelope(model, solve_vertical_grillage(model))

    combinations = project_internal_girder_combinations_from_grillage(
        project,
        grillage=native.envelope,
        girder_index=2,
        sls_factors=ServiceabilityPsiFactors(psi1_traffic=0.75, psi2_traffic=0.30),
    )

    native_effect = native.envelope.effect_for_girder(2)
    assert combinations.traffic_characteristic == native_effect
    assert "native_grillage_end_envelope" in combinations.traffic_distribution_method
    assert "RC-Bridge native vertical grillage" in combinations.traffic_distribution_method


def test_native_end_envelope_rejects_longitudinal_member_udl_until_section_recovery_exists() -> None:
    base = _model(GrillageVerificationLoadCase(name="no traffic"))
    longitudinal_member_id = min(beam.member_id for beam in base.beams)
    bad_case = VerificationLoadCase(
        load_case_id=1,
        name="longitudinal member UDL",
        uniform_loads=(),
        point_loads=(),
        nodal_loads=(),
    )
    # Rebuild through the project generator so the UDL is applied to all physical girder segments.
    model = _model(
        GrillageVerificationLoadCase(
            name="longitudinal UDL",
            longitudinal_udl_kn_m_by_girder=(5.0, 5.0, 5.0),
        )
    )
    analysis = solve_vertical_grillage(model)

    assert bad_case.load_case_id == 1
    assert longitudinal_member_id > 0
    with pytest.raises(ValueError, match="longitudinal members to be load-free"):
        native_grillage_traffic_envelope(model, analysis)
