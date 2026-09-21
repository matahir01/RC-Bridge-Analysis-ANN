from pathlib import Path

from rc_bridge.application.reporting import native_lm1_html_report
from rc_bridge.application.verification_files import (
    write_consolidated_governing_lm1_verification_files,
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
    assert "genuine STAAD external evidence" in report
    assert "MIDAS" in report and "deferred to V2" in report


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


def test_application_writes_one_consolidated_midas_and_staad_file(tmp_path) -> None:
    project = _project()
    search = _search()
    written = write_consolidated_governing_lm1_verification_files(
        project,
        search,
        tmp_path,
        base_name="application_bridge_governing",
    )

    assert written.midas_mct.exists()
    assert written.staad_std.exists()
    assert written.midas_mct.parent == tmp_path
    assert written.staad_std.parent == tmp_path
    assert set(written.case_ids) == set(search.governing_case_ids)

    mct = written.midas_mct.read_text(encoding="utf-8")
    std = written.staad_std.read_text(encoding="utf-8")
    for case_id in search.governing_case_ids:
        assert f"LM1_CASE_{case_id:04d}" in mct
        assert f"LM1_CASE_{case_id:04d}" in std
