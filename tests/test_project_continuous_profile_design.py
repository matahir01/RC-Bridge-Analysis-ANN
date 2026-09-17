import pytest

from rc_bridge.core.models import (
    BridgeGeometry,
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    TGirderProfile,
)
from rc_bridge.workflow.project_continuous_design import (
    NegativeSupportFlangedDesignInput,
    NegativeSupportRectangularDesignInput,
    negative_support_design_input_from_project,
)


def test_i_girder_hogging_uses_actual_bottom_flange() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.I,
            girder_profile=IGirderProfile(
                top_flange_width_m=0.70,
                top_flange_thickness_m=0.15,
                web_width_m=0.30,
                web_depth_m=0.62,
                bottom_flange_width_m=0.65,
                bottom_flange_thickness_m=0.18,
            ),
        )
    )

    result = negative_support_design_input_from_project(
        project,
        effective_depth_from_bottom_m=1.12,
        provided_top_steel_area_mm2=6500.0,
    )

    assert isinstance(result, NegativeSupportFlangedDesignInput)
    assert result.bottom_flange_width_m == pytest.approx(0.65)
    assert result.bottom_flange_thickness_m == pytest.approx(0.18)
    assert result.web_width_m == pytest.approx(0.30)


def test_t_girder_hogging_uses_lower_stem_width_not_top_flange() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.T,
            girder_profile=TGirderProfile(
                flange_width_m=0.70,
                flange_thickness_m=0.15,
                web_width_m=0.30,
                total_depth_m=0.95,
            ),
        )
    )

    result = negative_support_design_input_from_project(
        project,
        effective_depth_from_bottom_m=1.12,
        provided_top_steel_area_mm2=6500.0,
    )

    assert isinstance(result, NegativeSupportRectangularDesignInput)
    assert result.compression_width_m == pytest.approx(0.30)


def test_rectangular_girder_hogging_uses_full_member_width() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.45, depth_m=0.95),
        )
    )

    result = negative_support_design_input_from_project(
        project,
        effective_depth_from_bottom_m=1.12,
        provided_top_steel_area_mm2=6500.0,
    )

    assert isinstance(result, NegativeSupportRectangularDesignInput)
    assert result.compression_width_m == pytest.approx(0.45)


def test_hogging_profile_adapter_refuses_unknown_benchmark_profile() -> None:
    with pytest.raises(ValueError, match="Physical girder profile"):
        negative_support_design_input_from_project(
            ProjectInput(),
            effective_depth_from_bottom_m=1.12,
            provided_top_steel_area_mm2=6500.0,
        )
