from pathlib import Path

from rc_bridge.application.reporting import native_lm1_html_report
from rc_bridge.application.verification_files import (
    write_governing_lm1_verification_packages,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
)
from rc_bridge.workflow.lm1_grillage_search import (
    run_project_native_lm1_grillage_search,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Application bridge",
        geometry=BridgeGeometry(
            span_lengths_m=[6.0],
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
            girder_depth_m=0.95,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.40, depth_m=0.95),
        ),
    )


def _search():
    return run_project_native_lm1_grillage_search(
        _project(),
        transverse_stations_m=(0.0, 3.0, 6.0),
        longitudinal_step_m=6.0,
        max_exhaustive_tandem_combinations=20,
    )


def test_application_report_contains_traceable_governing_results() -> None:
    report = native_lm1_html_report(_project(), _search())

    assert "<!doctype html>" in report
    assert "Application bridge" in report
    assert "Native LM1 search" in report
    assert "Verification boundary" in report
    assert "independent structural validation" in report


def test_application_writes_exact_governing_verification_packages(tmp_path) -> None:
    search = _search()
    written = write_governing_lm1_verification_packages(
        search,
        tmp_path,
        base_name="application_bridge",
    )

    assert written
    case_ids = {item.case_id for item in written}
    assert case_ids == set(search.governing_case_ids)
    for package in written:
        suffixes = {path.suffix for path in package.files}
        assert ".mct" in suffixes
        assert ".std" in suffixes
        assert ".json" in suffixes
        assert ".csv" in suffixes
        for path in package.files:
            assert isinstance(path, Path)
            assert path.exists()
            assert path.read_text(encoding="utf-8")
