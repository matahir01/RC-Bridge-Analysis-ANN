import pytest

from rc_bridge.analysis.grillage_solver import solve_vertical_grillage
from rc_bridge.analysis.grillage_station_response import (
    longitudinal_station_end_response,
)
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNodalLoad,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)


def _model(*, point_load: bool) -> VerificationModel:
    e_kn_m2 = 30.0e6
    iy_m4 = 1.0e6 / e_kn_m2
    uniform_loads = ()
    nodal_loads = (VerificationNodalLoad(node_id=2, fz_kn=-100.0),)
    if not point_load:
        uniform_loads = (
            VerificationUniformLoad(1, "GZ", -20.0),
            VerificationUniformLoad(2, "GZ", -20.0),
        )
        nodal_loads = ()
    return VerificationModel(
        name="station response beam",
        nodes=(
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 5.0, 0.0, 0.0),
            VerificationNode(3, 10.0, 0.0, 0.0),
        ),
        materials=(VerificationMaterial(1, "Concrete", e_kn_m2),),
        sections=(
            VerificationSection(
                section_id=1,
                name="Beam",
                area_m2=0.40,
                torsion_constant_m4=0.01,
                iy_m4=iy_m4,
                iz_m4=0.05,
            ),
        ),
        beams=(
            VerificationBeam(1, 1, 2, 1, 1),
            VerificationBeam(2, 2, 3, 1, 1),
        ),
        supports=(
            VerificationSupport(1, uz=True, rx=True),
            VerificationSupport(3, uz=True),
        ),
        load_cases=(
            VerificationLoadCase(
                1,
                "LOAD",
                uniform_loads=uniform_loads,
                nodal_loads=nodal_loads,
            ),
        ),
    )


def test_station_response_recovers_udl_moment_and_shear_signs() -> None:
    model = _model(point_load=False)
    analysis = solve_vertical_grillage(model)

    left_support = longitudinal_station_end_response(
        model,
        analysis.members,
        target_y_m=0.0,
        x_m=0.0,
        side="right",
        span_start_m=0.0,
        span_end_m=10.0,
    )
    mid_left = longitudinal_station_end_response(
        model,
        analysis.members,
        target_y_m=0.0,
        x_m=5.0,
        side="left",
        span_start_m=0.0,
        span_end_m=10.0,
    )
    mid_right = longitudinal_station_end_response(
        model,
        analysis.members,
        target_y_m=0.0,
        x_m=5.0,
        side="right",
        span_start_m=0.0,
        span_end_m=10.0,
    )

    assert left_support.moment_knm == pytest.approx(0.0, abs=1.0e-9)
    assert left_support.shear_kn == pytest.approx(100.0)
    assert mid_left.moment_knm == pytest.approx(250.0)
    assert mid_right.moment_knm == pytest.approx(250.0)
    assert mid_left.shear_kn == pytest.approx(0.0, abs=1.0e-9)
    assert mid_right.shear_kn == pytest.approx(0.0, abs=1.0e-9)


def test_station_response_preserves_point_load_shear_jump() -> None:
    model = _model(point_load=True)
    analysis = solve_vertical_grillage(model)

    left = longitudinal_station_end_response(
        model,
        analysis.members,
        target_y_m=0.0,
        x_m=5.0,
        side="left",
        span_start_m=0.0,
        span_end_m=10.0,
    )
    right = longitudinal_station_end_response(
        model,
        analysis.members,
        target_y_m=0.0,
        x_m=5.0,
        side="right",
        span_start_m=0.0,
        span_end_m=10.0,
    )

    assert left.moment_knm == pytest.approx(250.0)
    assert right.moment_knm == pytest.approx(250.0)
    assert left.shear_kn == pytest.approx(50.0)
    assert right.shear_kn == pytest.approx(-50.0)
