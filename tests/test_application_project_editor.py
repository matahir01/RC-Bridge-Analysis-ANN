import pytest

from rc_bridge.application.project_editor import (
    ProjectBasicFields,
    application_default_project,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    IGirderProfile,
    PermanentActionModel,
    PermanentLineAction,
    PermanentLineActionCategory,
    ProjectInput,
    SectionType,
)


def test_application_default_project_has_complete_physical_profile() -> None:
    project = application_default_project()

    assert project.geometry.girder_profile is not None
    assert project.geometry.section_type == SectionType.RECTANGULAR
    assert project.geometry.girder_profile.total_depth_m == pytest.approx(0.95)
    assert project.geometry.girder_profile.width_m == pytest.approx(0.40)


def test_basic_editor_round_trip_preserves_unedited_project_actions() -> None:
    project = ProjectInput(
        permanent_actions=PermanentActionModel(
            line_actions=[
                PermanentLineAction(
                    name="barrier",
                    magnitude_kn_m=10.0,
                    y_m=5.0,
                    category=PermanentLineActionCategory.BARRIER,
                )
            ]
        )
    )
    fields = ProjectBasicFields.from_project(project)
    assert fields.section_type == SectionType.T
    assert fields.t_total_depth_m is None

    analysable = application_default_project()
    edited = ProjectBasicFields.from_project(analysable).apply(analysable)
    assert edited == analysable


def test_basic_editor_builds_i_profile_and_revalidates_geometry() -> None:
    base = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.I,
            girder_profile=IGirderProfile(
                top_flange_width_m=0.70,
                top_flange_thickness_m=0.15,
                web_width_m=0.30,
                web_depth_m=0.60,
                bottom_flange_width_m=0.60,
                bottom_flange_thickness_m=0.20,
            ),
        )
    )
    fields = ProjectBasicFields.from_project(base)
    edited = ProjectBasicFields(
        **{
            **fields.__dict__,
            "name": "Edited I girder",
            "i_web_depth_m": 0.62,
        }
    ).apply(base)

    assert edited.name == "Edited I girder"
    assert isinstance(edited.geometry.girder_profile, IGirderProfile)
    assert edited.geometry.girder_depth_m == pytest.approx(0.97)
