import pytest

from rc_bridge.application.session import (
    BridgeApplicationSession,
    longitudinal_grid_stations,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Session bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[6.0],
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.40, depth_m=0.95),
        ),
    )


def test_application_grid_preserves_supports_and_spacing() -> None:
    project = ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[4.0, 6.0],
            support_system="continuous",
        )
    )
    stations = longitudinal_grid_stations(project, maximum_spacing_m=3.0)

    assert 0.0 in stations
    assert 4.0 in stations
    assert 10.0 in stations
    assert max(b - a for a, b in zip(stations, stations[1:], strict=True)) <= 3.0


def test_application_session_runs_reports_and_exports(tmp_path) -> None:
    session = BridgeApplicationSession(_project())
    result = session.run_native_lm1(
        grid_spacing_m=3.0,
        longitudinal_step_m=6.0,
        max_exhaustive_tandem_combinations=20,
    )
    report = session.write_last_lm1_report(tmp_path / "report.html")
    packages = session.export_last_lm1_verification(tmp_path / "verification")

    assert result.evaluated_case_count > 0
    assert report.exists()
    assert packages
    assert session.last_lm1_search is result


def test_application_session_requires_physical_profile() -> None:
    session = BridgeApplicationSession(ProjectInput())
    with pytest.raises(ValueError, match="complete physical"):
        session.run_native_lm1(
            grid_spacing_m=5.0,
            longitudinal_step_m=15.0,
            max_exhaustive_tandem_combinations=20,
        )
