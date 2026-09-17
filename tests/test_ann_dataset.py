import numpy as np
import pytest

from rc_bridge.research.ann_dataset import (
    TARGET_NAMES,
    feature_names_for_profile,
    records_to_matrices,
    split_and_standardize_records,
)
from rc_bridge.research.multilimit_records import MultiLimitTrainingRecord
from rc_bridge.research.verification import SolverProfile


def _record(index: int, profile: SolverProfile = SolverProfile.EUROCODE_1G):
    value = float(index)
    is_eurocode = profile == SolverProfile.EUROCODE_1G
    return MultiLimitTrainingRecord(
        solver_profile=profile.value,
        girder_index=4,
        span_m=12.0 + 0.2 * value,
        girder_spacing_m=1.5 + 0.01 * value,
        girder_depth_m=0.8 + 0.01 * value,
        deck_thickness_m=0.22 + 0.001 * value,
        effective_depth_m=0.95 + 0.01 * value,
        web_width_m=0.25 + 0.002 * value,
        fck_mpa=30.0 + value if is_eurocode else None,
        fcu_mpa=None if is_eurocode else 35.0 + value,
        fyk_mpa=500.0,
        longitudinal_steel_area_mm2=4500.0 + 50.0 * value,
        provided_shear_steel_mm2_per_m=700.0 + 10.0 * value,
        permanent_moment_knm=300.0 + 5.0 * value,
        traffic_moment_knm=500.0 + 8.0 * value,
        design_moment_knm=1100.0 + 10.0 * value,
        design_shear_kn=250.0 + 2.0 * value,
        moment_resistance_knm=1500.0 + 12.0 * value,
        shear_resistance_kn=400.0 + 4.0 * value,
        crack_width_mm=0.10 + 0.001 * value,
        crack_limit_mm=0.30,
        deflection_mm=18.0 + 0.1 * value,
        deflection_limit_mm=60.0,
        flexure_utilization=0.70 + 0.001 * value,
        shear_utilization=0.60 + 0.001 * value,
        crack_utilization=0.33 + 0.001 * value,
        deflection_utilization=0.30 + 0.001 * value,
        g_flexure_knm=400.0 + 2.0 * value,
        g_shear_kn=150.0 + 2.0 * value,
        g_crack_mm=0.20 - 0.001 * value,
        g_deflection_mm=42.0 - 0.1 * value,
        g_fatigue=None,
        g_torsion=None,
        traffic_distribution_method="verified_test_distribution",
        crack_combination_name="test crack combination",
        deflection_combination_name="test deflection combination",
    )


def test_profile_features_use_code_specific_concrete_strength() -> None:
    eurocode = feature_names_for_profile(SolverProfile.EUROCODE_1G)
    bs5400 = feature_names_for_profile(SolverProfile.BS5400_BD37_01)
    assert "fck_mpa" in eurocode
    assert "fcu_mpa" not in eurocode
    assert "fcu_mpa" in bs5400
    assert "fck_mpa" not in bs5400


def test_records_to_matrices_carries_four_limit_state_targets() -> None:
    records = [_record(index) for index in range(6)]
    x, y, features, targets = records_to_matrices(
        records,
        profile=SolverProfile.EUROCODE_1G,
    )
    assert x.shape == (6, len(features))
    assert y.shape == (6, 4)
    assert targets == TARGET_NAMES
    assert np.all(np.isfinite(x))
    assert np.all(np.isfinite(y))


def test_split_is_reproducible_and_standardizes_from_training_subset_only() -> None:
    records = [_record(index) for index in range(20)]
    first = split_and_standardize_records(
        records,
        profile=SolverProfile.EUROCODE_1G,
        seed=17,
    )
    second = split_and_standardize_records(
        records,
        profile=SolverProfile.EUROCODE_1G,
        seed=17,
    )

    assert first.x_train.shape[0] == 14
    assert first.x_validation.shape[0] == 3
    assert first.x_test.shape[0] == 3
    assert np.allclose(first.x_train, second.x_train)
    assert np.allclose(first.y_test, second.y_test)
    assert np.allclose(first.x_train.mean(axis=0), 0.0, atol=1e-12)
    assert np.allclose(first.y_train.mean(axis=0), 0.0, atol=1e-12)


def test_dataset_rejects_mixed_solver_profiles() -> None:
    records = [_record(0), _record(1, SolverProfile.BS5400_BD37_01)]
    with pytest.raises(ValueError, match="requested solver profile"):
        records_to_matrices(records, profile=SolverProfile.EUROCODE_1G)
