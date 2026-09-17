from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np

from rc_bridge.research.multilimit_records import MultiLimitTrainingRecord
from rc_bridge.research.verification import SolverProfile


TARGET_NAMES = (
    "g_flexure_knm",
    "g_shear_kn",
    "g_crack_mm",
    "g_deflection_mm",
)

COMMON_FEATURE_NAMES = (
    "span_m",
    "girder_spacing_m",
    "girder_depth_m",
    "deck_thickness_m",
    "effective_depth_m",
    "web_width_m",
    "fyk_mpa",
    "longitudinal_steel_area_mm2",
    "provided_shear_steel_mm2_per_m",
    "permanent_moment_knm",
    "traffic_moment_knm",
)


def feature_names_for_profile(profile: SolverProfile) -> tuple[str, ...]:
    concrete_strength = (
        "fck_mpa" if profile == SolverProfile.EUROCODE_1G else "fcu_mpa"
    )
    return (*COMMON_FEATURE_NAMES[:6], concrete_strength, *COMMON_FEATURE_NAMES[6:])


@dataclass(frozen=True)
class Standardizer:
    mean: np.ndarray
    scale: np.ndarray

    def transform(self, values: np.ndarray) -> np.ndarray:
        if values.ndim != 2 or values.shape[1] != self.mean.shape[0]:
            raise ValueError("Values do not match the fitted standardizer dimensions.")
        return (values - self.mean) / self.scale


@dataclass(frozen=True)
class ANNDatasetSplit:
    solver_profile: str
    feature_names: tuple[str, ...]
    target_names: tuple[str, ...]
    x_train: np.ndarray
    y_train: np.ndarray
    x_validation: np.ndarray
    y_validation: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    feature_standardizer: Standardizer
    target_standardizer: Standardizer


def _numeric_value(record: MultiLimitTrainingRecord, name: str) -> float:
    value = getattr(record, name)
    if value is None:
        raise ValueError(
            f"ANN field {name!r} is missing for solver profile {record.solver_profile!r}."
        )
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"ANN field {name!r} must be finite.")
    return numeric


def records_to_matrices(
    records: list[MultiLimitTrainingRecord],
    *,
    profile: SolverProfile,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], tuple[str, ...]]:
    if not records:
        raise ValueError("At least one multi-limit training record is required.")

    expected = profile.value
    if any(record.solver_profile != expected for record in records):
        raise ValueError("All ANN records must use the requested solver profile.")

    feature_names = feature_names_for_profile(profile)
    x = np.asarray(
        [[_numeric_value(record, name) for name in feature_names] for record in records],
        dtype=float,
    )
    y = np.asarray(
        [[_numeric_value(record, name) for name in TARGET_NAMES] for record in records],
        dtype=float,
    )
    return x, y, feature_names, TARGET_NAMES


def fit_standardizer(values: np.ndarray) -> Standardizer:
    if values.ndim != 2 or values.shape[0] == 0:
        raise ValueError("Standardization requires a non-empty 2D array.")
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale = np.where(scale > 0.0, scale, 1.0)
    return Standardizer(mean=mean, scale=scale)


def split_and_standardize_records(
    records: list[MultiLimitTrainingRecord],
    *,
    profile: SolverProfile,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    seed: int = 42,
) -> ANNDatasetSplit:
    """Create deterministic train/validation/test matrices for the ANN surrogate.

    Standardizers are fitted on the training subset only, then applied to the
    validation and test subsets to avoid data leakage.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must lie between 0 and 1.")
    if not 0.0 <= validation_fraction < 1.0:
        raise ValueError("validation_fraction must lie between 0 and 1.")
    if train_fraction + validation_fraction >= 1.0:
        raise ValueError("Train and validation fractions must leave a non-zero test set.")

    x, y, feature_names, target_names = records_to_matrices(records, profile=profile)
    sample_count = x.shape[0]
    if sample_count < 3:
        raise ValueError("At least three records are required for train/validation/test splitting.")

    rng = np.random.default_rng(seed)
    order = rng.permutation(sample_count)
    x = x[order]
    y = y[order]

    train_count = max(1, int(sample_count * train_fraction))
    validation_count = int(sample_count * validation_fraction)
    if validation_fraction > 0.0:
        validation_count = max(1, validation_count)
    if train_count + validation_count >= sample_count:
        validation_count = max(0, sample_count - train_count - 1)

    validation_end = train_count + validation_count
    x_train_raw = x[:train_count]
    y_train_raw = y[:train_count]
    x_validation_raw = x[train_count:validation_end]
    y_validation_raw = y[train_count:validation_end]
    x_test_raw = x[validation_end:]
    y_test_raw = y[validation_end:]

    feature_standardizer = fit_standardizer(x_train_raw)
    target_standardizer = fit_standardizer(y_train_raw)

    return ANNDatasetSplit(
        solver_profile=profile.value,
        feature_names=feature_names,
        target_names=target_names,
        x_train=feature_standardizer.transform(x_train_raw),
        y_train=target_standardizer.transform(y_train_raw),
        x_validation=feature_standardizer.transform(x_validation_raw),
        y_validation=target_standardizer.transform(y_validation_raw),
        x_test=feature_standardizer.transform(x_test_raw),
        y_test=target_standardizer.transform(y_test_raw),
        feature_standardizer=feature_standardizer,
        target_standardizer=target_standardizer,
    )
