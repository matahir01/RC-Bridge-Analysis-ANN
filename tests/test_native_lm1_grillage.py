import json

import pytest

from rc_bridge.core.models import BridgeGeometry, ProjectInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_verification import (
    LM1LaneVerificationPlacement,
    LM1LongitudinalRegion,
    LM1RemainingAreaVerificationPlacement,
)
from rc_bridge.workflow.native_lm1_grillage import run_project_native_lm1_grillage_snapshot


def _project() -> ProjectInput:
    return ProjectInput(
        name="Eight girder native LM1",
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


def _placements():
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
            tandem_lead_x_m=7.0,
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


def test_native_lm1_snapshot_respects_editable_eight_girder_layout() -> None:
    lanes, remaining = _placements()
    result = run_project_native_lm1_grillage_snapshot(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    assert result.girder_count == 8
    assert [item.girder_index for item in result.girder_envelope.details] == list(range(1, 9))
    assert result.girder_envelope.details[0].y_m == pytest.approx(-4.9)
    assert result.girder_envelope.details[-1].y_m == pytest.approx(4.9)
    assert result.analysis.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1.0e-7)

    moments = [
        result.girder_envelope.envelope.effect_for_girder(index).moment_knm
        for index in range(1, 9)
    ]
    assert max(moments) > min(moments)
    assert all(moment > 0.0 for moment in moments)


def test_native_lm1_external_package_uses_same_model_and_preserves_layout_metadata() -> None:
    lanes, remaining = _placements()
    result = run_project_native_lm1_grillage_snapshot(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    manifest = json.loads(result.verification_package.manifest_json)
    assert manifest["node_count"] == len(result.model.nodes)
    assert manifest["member_count"] == len(result.model.beams)
    assert manifest["metadata"]["girder_count"] == "8"
    assert manifest["metadata"]["girder_spacing_m"] == "1.4"
    assert manifest["metadata"]["deck_width_m"] == "11"
    assert manifest["metadata"]["lm1_lane_strips"] == "lane1:-3.5:-0.5|lane2:-0.5:2.5"
    assert "*NODE" in result.verification_package.midas_mct
    assert "MEMBER INCIDENCES" in result.verification_package.staad_std


def test_native_lm1_snapshot_is_not_labelled_as_a_governing_search_result() -> None:
    lanes, remaining = _placements()
    result = run_project_native_lm1_grillage_snapshot(
        _project(),
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        lane_placements=lanes,
        remaining_area_placements=remaining,
    )

    assert "snapshot" in result.analysis.load_case_name.lower()
    assert result.girder_envelope.envelope.metadata.method == "native_grillage_end_envelope"
