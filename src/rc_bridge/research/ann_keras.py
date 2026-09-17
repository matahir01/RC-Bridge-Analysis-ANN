from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np

from rc_bridge.research.ann_dataset import ANNDatasetSplit


@dataclass(frozen=True)
class ANNTrainingConfig:
    """Configurable dense-network settings for the multi-limit surrogate."""

    hidden_layers: tuple[int, ...] = (64, 64)
    activation: str = "relu"
    learning_rate: float = 1e-3
    epochs: int = 500
    batch_size: int = 32
    patience: int = 30
    min_delta: float = 1e-6
    seed: int = 42
    verbose: int = 0

    def __post_init__(self) -> None:
        if not self.hidden_layers or any(width <= 0 for width in self.hidden_layers):
            raise ValueError("hidden_layers must contain positive layer widths.")
        if not self.activation:
            raise ValueError("activation cannot be empty.")
        if self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive.")
        if self.epochs <= 0 or self.batch_size <= 0 or self.patience < 0:
            raise ValueError("epochs/batch_size must be positive and patience non-negative.")
        if self.min_delta < 0.0:
            raise ValueError("min_delta cannot be negative.")
        if self.verbose < 0:
            raise ValueError("verbose cannot be negative.")


@dataclass(frozen=True)
class ANNTrainingResult:
    model: object
    history: dict[str, list[float]]
    physical_test_metrics: dict[str, dict[str, float]]
    standardized_test_predictions: np.ndarray
    physical_test_predictions: np.ndarray


def _require_tensorflow():
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise RuntimeError(
            "TensorFlow is required only for ANN training. Install the project's "
            "optional research dependencies before calling the Keras trainer."
        ) from exc
    return tf


def inverse_standardized_targets(
    split: ANNDatasetSplit,
    standardized_values: np.ndarray,
) -> np.ndarray:
    values = np.asarray(standardized_values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(split.target_names):
        raise ValueError("Standardized target matrix does not match ANN target dimensions.")
    return values * split.target_standardizer.scale + split.target_standardizer.mean


def regression_metrics_by_target(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_names: tuple[str, ...],
) -> dict[str, dict[str, float]]:
    truth = np.asarray(y_true, dtype=float)
    predicted = np.asarray(y_pred, dtype=float)
    if truth.shape != predicted.shape or truth.ndim != 2:
        raise ValueError("Truth and prediction matrices must be matching 2D arrays.")
    if truth.shape[1] != len(target_names):
        raise ValueError("target_names does not match the regression output dimension.")

    metrics: dict[str, dict[str, float]] = {}
    for index, name in enumerate(target_names):
        residual = predicted[:, index] - truth[:, index]
        mse = float(np.mean(residual**2))
        mae = float(np.mean(np.abs(residual)))
        denominator = float(np.sum((truth[:, index] - np.mean(truth[:, index])) ** 2))
        numerator = float(np.sum(residual**2))
        if denominator > 0.0:
            r2 = 1.0 - numerator / denominator
        else:
            r2 = 1.0 if numerator == 0.0 else float("nan")
        metrics[name] = {
            "rmse": sqrt(mse),
            "mae": mae,
            "r2": r2,
        }
    return metrics


def build_keras_surrogate(
    *,
    input_dimension: int,
    output_dimension: int,
    config: ANNTrainingConfig | None = None,
):
    """Build and compile the dense Keras surrogate without importing TF globally."""
    if input_dimension <= 0 or output_dimension <= 0:
        raise ValueError("ANN input and output dimensions must be positive.")
    cfg = config or ANNTrainingConfig()
    tf = _require_tensorflow()
    tf.keras.utils.set_random_seed(cfg.seed)

    layers = [tf.keras.layers.Input(shape=(input_dimension,))]
    layers.extend(
        tf.keras.layers.Dense(width, activation=cfg.activation)
        for width in cfg.hidden_layers
    )
    layers.append(tf.keras.layers.Dense(output_dimension, activation="linear"))
    model = tf.keras.Sequential(layers)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=cfg.learning_rate),
        loss="mse",
        metrics=["mae"],
    )
    return model


def train_keras_surrogate(
    split: ANNDatasetSplit,
    *,
    config: ANNTrainingConfig | None = None,
) -> ANNTrainingResult:
    """Train the four-output ANN and evaluate it in physical engineering units."""
    cfg = config or ANNTrainingConfig()
    if split.x_train.shape[0] == 0 or split.y_train.shape[0] == 0:
        raise ValueError("ANN training split cannot be empty.")
    if split.x_test.shape[0] == 0 or split.y_test.shape[0] == 0:
        raise ValueError("ANN test split cannot be empty.")
    if split.x_train.shape[0] != split.y_train.shape[0]:
        raise ValueError("ANN training feature/target row counts do not match.")

    tf = _require_tensorflow()
    model = build_keras_surrogate(
        input_dimension=split.x_train.shape[1],
        output_dimension=split.y_train.shape[1],
        config=cfg,
    )

    has_validation = split.x_validation.shape[0] > 0
    monitor = "val_loss" if has_validation else "loss"
    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor=monitor,
            patience=cfg.patience,
            min_delta=cfg.min_delta,
            restore_best_weights=True,
        )
    ]
    fit_kwargs: dict[str, object] = {
        "x": split.x_train,
        "y": split.y_train,
        "epochs": cfg.epochs,
        "batch_size": cfg.batch_size,
        "callbacks": callbacks,
        "verbose": cfg.verbose,
        "shuffle": True,
    }
    if has_validation:
        fit_kwargs["validation_data"] = (split.x_validation, split.y_validation)

    history_object = model.fit(**fit_kwargs)
    standardized_prediction = np.asarray(
        model.predict(split.x_test, verbose=0),
        dtype=float,
    )
    physical_prediction = inverse_standardized_targets(split, standardized_prediction)
    physical_truth = inverse_standardized_targets(split, split.y_test)
    metrics = regression_metrics_by_target(
        physical_truth,
        physical_prediction,
        split.target_names,
    )

    history = {
        key: [float(value) for value in values]
        for key, values in history_object.history.items()
    }
    return ANNTrainingResult(
        model=model,
        history=history,
        physical_test_metrics=metrics,
        standardized_test_predictions=standardized_prediction,
        physical_test_predictions=physical_prediction,
    )
