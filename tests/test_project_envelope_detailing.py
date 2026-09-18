import pytest

from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.eurocode_girder import TGirderDesignInput
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.lm1_grillage_search import run_project_native_lm1_grillage_search
from rc_bridge.workflow.project_envelope_detailing import (
    ULSDetailingEnvelopePoint,
    native_lm1_uls_detailing_envelope,
    run_project_t_girder_envelope_detailing,
)


def _section() -> TGirderDesignInput:
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


def test_envelope_detailing_creates_curtailment_and_link_spacing_zones() -> None:
    project = ProjectInput()
    span = 15.0
    envelope = tuple(
        ULSDetailingEnvelopePoint(
            x_m=x,
            permanent_moment_knm=0.0,
            permanent_shear_kn=0.0,
            traffic_moment_knm=moment,
            traffic_shear_kn=shear,
            design_moment_knm=moment,
            design_shear_kn=abs(shear),
            moment_case_id=1,
            moment_member_id=10,
            shear_case_id=2,
            shear_member_id=20,
        )
        for x, moment, shear in (
            (0.0, 0.0, 520.0),
            (1.0, 140.0, 450.0),
            (2.0, 280.0, 380.0),
            (3.0, 420.0, 310.0),
            (4.0, 560.0, 240.0),
            (5.0, 680.0, 170.0),
            (6.0, 780.0, 100.0),
            (7.0, 840.0, 30.0),
            (7.5, 850.0, 0.0),
            (8.0, 840.0, -30.0),
            (9.0, 780.0, -100.0),
            (10.0, 680.0, -170.0),
            (11.0, 560.0, -240.0),
            (12.0, 420.0, -310.0),
            (13.0, 280.0, -380.0),
            (14.0, 140.0, -450.0),
            (15.0, 0.0, -520.0),
        )
    )

    result = run_project_t_girder_envelope_detailing(
        project,
        section=_section(),
        envelope=envelope,
    )

    assert result.tension_shift_m == pytest.approx(0.99)
    assert len(result.longitudinal_zones) >= 2
    assert len(result.link_zones) >= 2
    assert {
        zone.arrangement.bar_diameter_mm for zone in result.longitudinal_zones
    } == {result.longitudinal_zones[0].arrangement.bar_diameter_mm}
    assert {
        (zone.arrangement.link_diameter_mm, zone.arrangement.leg_count)
        for zone in result.link_zones
    } == {
        (
            result.link_zones[0].arrangement.link_diameter_mm,
            result.link_zones[0].arrangement.leg_count,
        )
    }
    support_spacing = result.stations[0].selected_links.spacing_mm
    midspan = min(result.stations, key=lambda item: abs(item.x_m - span / 2.0))
    assert support_spacing <= midspan.selected_links.spacing_mm
    peak_zone = max(
        result.longitudinal_zones,
        key=lambda item: item.arrangement.provided_area_mm2,
    )
    assert peak_zone.anchored_start_m <= peak_zone.x_start_m
    assert peak_zone.anchored_end_m >= peak_zone.x_end_m


def test_native_lm1_detailing_envelope_recovers_stationwise_uls_response() -> None:
    project = ProjectInput()
    search = run_project_native_lm1_grillage_search(
        project,
        longitudinal_sections_by_span=(_longitudinal(),),
        transverse_section=_transverse(),
        transverse_stations_m=(7.5,),
        longitudinal_step_m=15.0,
    )

    envelope = native_lm1_uls_detailing_envelope(
        project,
        search=search,
        girder_index=4,
        station_step_m=1.0,
    )

    assert envelope[0].x_m == pytest.approx(0.0)
    assert envelope[-1].x_m == pytest.approx(15.0)
    assert max(item.design_moment_knm for item in envelope) > 0.0
    assert max(item.design_shear_kn for item in envelope) > 0.0
    assert all(item.moment_case_id > 0 for item in envelope)
    assert all(item.shear_case_id > 0 for item in envelope)
    midspan = min(envelope, key=lambda item: abs(item.x_m - 7.5))
    assert midspan.design_moment_knm > envelope[0].design_moment_knm
    assert envelope[0].design_shear_kn > midspan.design_shear_kn
