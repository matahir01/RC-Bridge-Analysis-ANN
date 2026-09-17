import pytest

from rc_bridge.analysis.moving_loads import AxleTrain
from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.workflow.project_continuous import (
    ProjectContinuousLoadCase,
    ProjectContinuousMovingLoadCase,
    run_project_continuous_load_case,
    run_project_continuous_moving_train,
)
from rc_bridge.workflow.project_continuous_deflection import (
    check_project_continuous_deflection,
    check_project_continuous_moving_deflection,
)


def _project() -> ProjectInput:
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        )
    )


def _analysis():
    return run_project_continuous_load_case(
        _project(),
        ProjectContinuousLoadCase(
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            udl_kn_m_by_span=(20.0, 20.0),
            name="service load case",
        ),
    )


def _moving_analysis():
    return run_project_continuous_moving_train(
        _project(),
        ProjectContinuousMovingLoadCase(
            train=AxleTrain(axle_loads_kn=(100.0,), axle_offsets_m=(0.0,)),
            ei_kn_m2_by_span=(1.0e6, 1.0e6),
            movement_steps=81,
            section_stations=81,
            name="moving service train",
        ),
    )


def test_continuous_deflection_check_reports_margin_and_location() -> None:
    analysis = _analysis()
    calculated_mm = analysis.max_abs_vertical_displacement_m * 1000.0
    result = check_project_continuous_deflection(
        analysis,
        allowable_deflection_mm=calculated_mm + 5.0,
    )

    assert result.calculated_max_abs_deflection_mm == pytest.approx(calculated_mm)
    assert result.g_deflection_mm == pytest.approx(5.0)
    assert result.utilization == pytest.approx(calculated_mm / (calculated_mm + 5.0))
    assert result.passes is True
    assert result.governing_span_index == analysis.max_abs_vertical_displacement_span_index
    assert result.governing_local_position_m == pytest.approx(
        analysis.max_abs_vertical_displacement_local_position_m
    )
    assert result.governing_global_position_m == pytest.approx(
        analysis.max_abs_vertical_displacement_global_position_m
    )
    assert result.load_case_name == "service load case"


def test_continuous_deflection_check_fails_when_explicit_limit_is_exceeded() -> None:
    analysis = _analysis()
    calculated_mm = analysis.max_abs_vertical_displacement_m * 1000.0
    result = check_project_continuous_deflection(
        analysis,
        allowable_deflection_mm=calculated_mm / 2.0,
    )

    assert result.utilization == pytest.approx(2.0)
    assert result.g_deflection_mm == pytest.approx(-calculated_mm / 2.0)
    assert result.passes is False


def test_moving_deflection_check_reports_governing_train_position() -> None:
    analysis = _moving_analysis()
    calculated_mm = analysis.envelope.max_abs_displacement_m * 1000.0
    result = check_project_continuous_moving_deflection(
        analysis,
        allowable_deflection_mm=calculated_mm + 2.0,
    )

    assert result.calculated_max_abs_deflection_mm == pytest.approx(calculated_mm)
    assert result.g_deflection_mm == pytest.approx(2.0)
    assert result.passes is True
    assert result.governing_span_index == analysis.envelope.max_abs_displacement_span_index
    assert result.governing_local_position_m == pytest.approx(
        analysis.envelope.max_abs_displacement_local_position_m
    )
    assert result.governing_global_position_m == pytest.approx(
        analysis.envelope.max_abs_displacement_global_position_m
    )
    assert result.governing_lead_position_m == pytest.approx(
        analysis.envelope.max_abs_displacement_lead_position_m
    )
    assert result.load_case_name == "moving service train"


def test_continuous_deflection_check_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        check_project_continuous_deflection(
            _analysis(),
            allowable_deflection_mm=0.0,
        )

    with pytest.raises(ValueError, match="positive"):
        check_project_continuous_moving_deflection(
            _moving_analysis(),
            allowable_deflection_mm=0.0,
        )
