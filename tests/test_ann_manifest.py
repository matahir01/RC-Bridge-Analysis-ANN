import numpy as np
import pytest

from rc_bridge.research.ann_dataset import ANNDatasetSplit, Standardizer
from rc_bridge.research.ann_manifest import ANNArtifactManifest


def _split() -> ANNDatasetSplit:
    return ANNDatasetSplit(
        solver_profile="eurocode_test_profile",
        feature_names=("span_m", "fck_mpa"),
        target_names=("g_flexure_knm", "g_shear_kn"),
        x_train=np.zeros((2, 2)),
        y_train=np.zeros((2, 2)),
        x_validation=np.zeros((1, 2)),
        y_validation=np.zeros((1, 2)),
        x_test=np.zeros((1, 2)),
        y_test=np.zeros((1, 2)),
        feature_standardizer=Standardizer(
            mean=np.array([15.0, 35.0]),
            scale=np.array([2.0, 5.0]),
        ),
        target_standardizer=Standardizer(
            mean=np.array([300.0, 120.0]),
            scale=np.array([50.0, 20.0]),
        ),
    )


def test_manifest_round_trip_preserves_solver_and_scalers() -> None:
    manifest = ANNArtifactManifest.from_split(_split())
    restored = ANNArtifactManifest.from_json(manifest.to_json())

    assert restored == manifest
    assert restored.solver_profile == "eurocode_test_profile"
    assert restored.feature_names == ("span_m", "fck_mpa")
    assert restored.target_names == ("g_flexure_knm", "g_shear_kn")


def test_manifest_standardizes_features_and_restores_targets() -> None:
    manifest = ANNArtifactManifest.from_split(_split())
    raw = np.array([[17.0, 30.0]])
    standardized = manifest.standardize_features(raw)
    assert standardized[0] == pytest.approx([1.0, -1.0])

    physical_targets = manifest.restore_targets(np.array([[1.0, -2.0]]))
    assert physical_targets[0] == pytest.approx([350.0, 80.0])


def test_manifest_rejects_dimension_mismatch() -> None:
    manifest = ANNArtifactManifest.from_split(_split())
    with pytest.raises(ValueError, match="feature matrix"):
        manifest.standardize_features(np.zeros((1, 3)))
    with pytest.raises(ValueError, match="Target matrix"):
        manifest.restore_targets(np.zeros((1, 3)))
