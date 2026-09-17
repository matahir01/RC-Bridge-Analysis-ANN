import pytest

from rc_bridge.core.models import BridgeGeometry, IGirderProfile, ProjectInput, SectionType
from rc_bridge.workflow.project_bridge import internal_girder_characteristic_permanent_effects
from rc_bridge.workflow.section_loading import (
    girder_profile_self_weight_kn_m,
    permanent_load_input_from_profile,
)


def _project_with_i_profile() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.I,
            girder_profile=IGirderProfile(
                top_flange_width_m=0.60,
                top_flange_thickness_m=0.15,
                web_width_m=0.20,
                web_depth_m=0.65,
                bottom_flange_width_m=0.50,
                bottom_flange_thickness_m=0.15,
            ),
        )
    )


def test_benchmark_without_profile_does_not_invent_girder_self_weight() -> None:
    with pytest.raises(ValueError, match="profile dimensions are required"):
        girder_profile_self_weight_kn_m(ProjectInput())


def test_i_profile_area_drives_girder_self_weight() -> None:
    project = _project_with_i_profile()
    assert project.geometry.girder_profile_area_m2 == pytest.approx(0.295)
    assert girder_profile_self_weight_kn_m(project) == pytest.approx(7.375)


def test_profile_self_weight_flows_into_characteristic_permanent_effects() -> None:
    project = _project_with_i_profile()
    additional = permanent_load_input_from_profile(project)
    assert additional.girder_self_weight_kn_m == pytest.approx(7.375)

    effects = internal_girder_characteristic_permanent_effects(
        project,
        additional=additional,
    )
    assert effects.moment_knm == pytest.approx(506.25)
    assert effects.shear_kn == pytest.approx(135.0)


def test_profile_load_builder_keeps_other_dead_loads_explicit() -> None:
    project = _project_with_i_profile()
    additional = permanent_load_input_from_profile(
        project,
        surfacing_and_finishes_kn_m=1.5,
        assigned_barrier_and_services_kn_m=0.5,
        other_kn_m=0.25,
    )
    assert additional.total_additional_kn_m == pytest.approx(9.625)
