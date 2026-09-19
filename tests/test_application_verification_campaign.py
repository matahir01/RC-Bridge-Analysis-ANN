import json

from rc_bridge.application.extended_actions import ExtendedActionSettings
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
            actions=ExtendedActionSettings(
                braking_enabled=True,
                braking_alpha_q1=1.0,
                braking_alpha_Q1=1.0,
                thermal_enabled=True,
                thermal_uniform_expansion_delta_c=30.0,
                thermal_uniform_contraction_delta_c=20.0,
                pedestrian_enabled=True,
                left_footway_width_m=1.5,
                right_footway_width_m=1.5,
                lm2_enabled=True,
                lm2_longitudinal_step_m=15.0,
                lm2_transverse_step_m=5.0,
                barrier_impact_enabled=True,
                wind_enabled=True,
                wind_basic_velocity_m_s=40.0,
                wind_vertical_force_coefficient=0.10,
                construction_enabled=True,
                construction_execution_udl_kn_m2=1.0,
            ),
            fatigue=FatigueApplicationSettings(
                movement_step_m=15.0,
                section_step_m=15.0,
                axle_load_factor=1.0,
                lambda_s=1.0,
                characteristic_fatigue_strength_mpa=1000.0,
                shear_link_lambda_s=1.0,
                shear_link_characteristic_fatigue_strength_mpa=1000.0,
            ),
        ),
    )


def test_full_application_verification_campaign_exports_all_available_action_families(
    tmp_path,
) -> None:
    session = _session()
    session.run_native_lm1()
    session.run_extended_actions()
    session.run_local_deck_design()
    session.run_design_interpretation()
    session.run_fatigue()

    campaign = session.export_verification_campaign(tmp_path / "verification")

    families = set(campaign.families)
    assert "LM1 characteristic" in families
    assert "permanent actions" in families
    assert "gr2 frequent LM1" in families
    assert "pedestrian" in families
    assert "LM2" in families
    assert "vertical wind" in families
    assert "construction stage" in families
    assert "FLM3 fatigue" in families
    assert campaign.model_count >= 8
    assert campaign.manifest_json.exists()
    assert campaign.action_summary_json.exists()

    manifest = json.loads(campaign.manifest_json.read_text(encoding="utf-8"))
    assert manifest["model_count"] == campaign.model_count
    assert manifest["family_counts"]["LM1 characteristic"] == 1
    assert manifest["family_counts"]["permanent actions"] == 1
    assert "scalar_or_kinematic_verification_records" in manifest["coverage"]

    summary = json.loads(campaign.action_summary_json.read_text(encoding="utf-8"))
    assert "braking_acceleration" in summary
    assert "thermal" in summary
    assert "wind" in summary
    assert "barrier_accidental" in summary
    assert "integrated_action_combinations" in summary
    assert "local_deck" in summary

    std_files = [
        path
        for model in campaign.models
        for path in model.files
        if path.suffix.lower() == ".std"
    ]
    assert std_files
    for path in std_files:
        text = path.read_text(encoding="utf-8")
        assert "MATERIAL VerificationConcrete MEMB " in text
        assert "PERFORM ANALYSIS" in text
        assert text.rstrip().endswith("FINISH")


def test_full_campaign_requires_full_analysis_workflow(tmp_path) -> None:
    session = _session()
    session.run_native_lm1()

    try:
        session.export_verification_campaign(tmp_path / "verification")
    except RuntimeError as exc:
        assert "Additional actions" in str(exc)
    else:
        raise AssertionError("Full verification campaign must not silently omit actions.")
