from rc_bridge.application.fatigue import FatigueApplicationSettings
from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
)
from rc_bridge.application.project_editor import application_default_project
from rc_bridge.application.session import BridgeApplicationSession


def _session() -> BridgeApplicationSession:
    return BridgeApplicationSession(
        application_default_project(),
        preferences=ApplicationPreferences(
            analysis=AnalysisApplicationSettings(
                grid_spacing_m=15.0,
                traffic_step_m=15.0,
                max_exhaustive_tandem_combinations=20,
            ),
            fatigue=FatigueApplicationSettings(
                movement_step_m=15.0,
                section_step_m=15.0,
                lambda_s=1.0,
                characteristic_fatigue_strength_mpa=1000.0,
                shear_link_lambda_s=1.0,
                shear_link_characteristic_fatigue_strength_mpa=1000.0,
            ),
        ),
    )


def test_session_reuses_unchanged_analysis_and_records_cache_hit() -> None:
    session = _session()

    first = session.run_native_lm1()
    second = session.run_native_lm1()

    assert second is first
    assert session.last_performance_record is not None
    assert session.last_performance_record.operation == "native_lm1"
    assert session.last_performance_record.cache_hit is True

    session.run_extended_actions()
    first_deck = session.run_local_deck_design()
    second_deck = session.run_local_deck_design()

    assert second_deck is first_deck
    assert session.last_performance_record is not None
    assert session.last_performance_record.operation == "local_deck_design"
    assert session.last_performance_record.cache_hit is True


def test_dashboard_supporting_views_use_session_caches() -> None:
    session = _session()
    session.run_native_lm1()

    first_audit = session.permanent_load_audit()
    second_audit = session.permanent_load_audit()
    assert second_audit is first_audit
    assert session.last_performance_record is not None
    assert session.last_performance_record.cache_hit is True

    first_combo = session.combination_summary()
    second_combo = session.combination_summary()
    assert second_combo is first_combo
    assert session.last_performance_record is not None
    assert session.last_performance_record.operation == "combination_summary"
    assert session.last_performance_record.cache_hit is True


def test_step_by_step_trace_and_html_report_share_calculation_records(tmp_path) -> None:
    session = _session()
    session.run_native_lm1()
    session.run_extended_actions()
    session.run_local_deck_design()
    session.run_design_interpretation()
    session.run_fatigue()

    trace = session.calculation_trace()

    assert trace.step_count > 20
    labels = {
        step.label
        for block in trace.blocks
        for step in block.steps
    }
    assert "ULS bending moment" in labels
    assert "Required longitudinal reinforcement" in labels
    assert "One-way slab shear" in labels
    assert any(label.endswith("longitudinal reinforcement fatigue") for label in labels)

    report = session.write_last_lm1_report(tmp_path / "worked_report.html")
    text = report.read_text(encoding="utf-8")

    assert "Step-by-step calculation sheets" in text
    assert "Calculation / substitution" in text
    assert "Native grillage analysis - representative member formulation" in text
    assert "ULS bending moment" in text
    assert "integrated action combinations" in text
    assert "TS=0.75 and UDL=0.4" in text
    assert "Required longitudinal reinforcement" in text
    assert "<math" in text
    assert "<mfrac>" in text
    assert "<msqrt>" in text
    assert "<msub>" in text
    assert "NUMERICAL SUBSTITUTION" not in text
    assert "@page" in text
    assert "size: A4 landscape" in text
    assert "display: table-header-group" in text
    assert "break-inside: avoid" in text
    assert "Summary tables later in the report do not replace these calculations" in text

    pdf = session.write_last_lm1_pdf_report(tmp_path / "worked_report.pdf")
    pdf_bytes = pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 10_000
    cached_trace = session.calculation_trace()
    assert cached_trace is trace
    assert session.last_performance_record is not None
    assert session.last_performance_record.operation == "calculation_trace"
    assert session.last_performance_record.cache_hit is True
