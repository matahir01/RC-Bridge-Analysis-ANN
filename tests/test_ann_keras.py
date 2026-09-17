import numpy as np
import pytest

from rc_bridge.research.ann_dataset import ANNDatasetSplit, Standardizer
from rc_bridge.research.ann_keras import (
    ANNTrainingConfig,
    inverse_standardized_targets,
    regression_metrics_by_target,
)


def _split() -> ANNDatasetSplit:
    return ANNDatasetSplit(
        solver_profile="test_profile",
        feature_names=("x1", "x2"),
        target_names=("g_m", "g_v", "g_w", "g_d"),
        x_train=np.zeros((2, 2)),
        y_train=np.zeros((2, 4)),
        x_validation=np.zeros((1, 2)),
        y_validation=np.zeros((1, 4)),
        x_test=np.zeros((2, 2)),
        y_test=np.zeros((2, 4)),
        feature_standardizer=Standardizer(
            mean=np.array([10.0, 20.0]),
            scale=np.array([2.0, 4.0]),
        ),
        target_standardizer=Standardizer(
            mean=np.array([100.0, 200.0, 0.20, 30.0]),
            scale=np.array([10.0, 20.0, 0.05, 5.0]),
        ),
    )


def test_ann_training_config_rejects_invalid_hyperparameters() -> None:
    with pytest.raises(ValueError, match="hidden_layers"):
        ANNTrainingConfig(hidden_layers=(64, 0))
    with pytest.raises(ValueError, match="learning_rate"):
        ANNTrainingConfig(learning_rate=0.0)
    with pytest.raises(ValueError, match="patience"):
        ANNTrainingConfig(patience=-1)


def test_inverse_standardized_targets_recovers_engineering_units() -> None:
    split = _split()
    standardized = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],
            [1.0, -1.0, 2.0, -2.0],
        ]
    )
    physical = inverse_standardized_targets(split, standardized)
    assert physical[0] == pytest.approx([100.0, 200.0, 0.20, 30.0])
    assert physical[1] == pytest.approx([110.0, 180.0, 0.30, 20.0])


def test_regression_metrics_are_computed_per_physical_target() -> None:
    truth = np.array(
        [
            [100.0, 200.0, 0.20, 30.0],
            [120.0, 240.0, 0.30, 40.0],
        ]
    )
    prediction = np.array(
        [
            [105.0, 190.0, 0.22, 32.0],
            [115.0, 250.0, 0.28, 38.0],
        ]
    )
    names = ("g_m", "g_v", "g_w", "g_d")
    metrics = regression_metrics_by_target(truth, prediction, names)

    assert metrics["g_m"]["rmse"] == pytest.approx(5.0)
    assert metrics["g_m"]["mae"] == pytest.approx(5.0)
    assert metrics["g_v"]["rmse"] == pytest.approx(10.0)
    assert metrics["g_w"]["mae"] == pytest.approx(0.02)
    assert metrics["g_d"]["mae"] == pytest.approx(2.0)
    assert all("r2" in metrics[name] for name in names)


def test_metric_helper_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="matching 2D arrays"):
        regression_metrics_by_target(
            np.zeros((2, 4)),
            np.zeros((3, 4)),
            ("a", "b", "c", "d"),
        )
