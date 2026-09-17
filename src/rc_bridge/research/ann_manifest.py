from __future__ import annotations

from dataclasses import asdict, dataclass
import json

import numpy as np

from rc_bridge.research.ann_dataset import ANNDatasetSplit


@dataclass(frozen=True)
class ANNArtifactManifest:
    """Portable metadata required to use a trained surrogate safely."""

    schema_version: int
    solver_profile: str
    feature_names: tuple[str, ...]
    target_names: tuple[str, ...]
    feature_mean: tuple[float, ...]
    feature_scale: tuple[float, ...]
    target_mean: tuple[float, ...]
    target_scale: tuple[float, ...]
    model_format: str = "keras"

    def __post_init__(self) -> None:
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive.")
        if not self.solver_profile:
            raise ValueError("solver_profile cannot be empty.")
        if not self.feature_names or not self.target_names:
            raise ValueError("ANN manifest requires feature and target names.")
        if len(self.feature_names) != len(self.feature_mean) or len(self.feature_names) != len(
            self.feature_scale
        ):
            raise ValueError("Feature names and scaling vectors must have equal lengths.")
        if len(self.target_names) != len(self.target_mean) or len(self.target_names) != len(
            self.target_scale
        ):
            raise ValueError("Target names and scaling vectors must have equal lengths.")
        if any(scale <= 0.0 for scale in (*self.feature_scale, *self.target_scale)):
            raise ValueError("ANN manifest scaling factors must be positive.")
        if not self.model_format:
            raise ValueError("model_format cannot be empty.")

    @classmethod
    def from_split(cls, split: ANNDatasetSplit) -> ANNArtifactManifest:
        return cls(
            schema_version=1,
            solver_profile=split.solver_profile,
            feature_names=split.feature_names,
            target_names=split.target_names,
            feature_mean=tuple(float(value) for value in split.feature_standardizer.mean),
            feature_scale=tuple(float(value) for value in split.feature_standardizer.scale),
            target_mean=tuple(float(value) for value in split.target_standardizer.mean),
            target_scale=tuple(float(value) for value in split.target_standardizer.scale),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ANNArtifactManifest:
        data = json.loads(text)
        for name in (
            "feature_names",
            "target_names",
            "feature_mean",
            "feature_scale",
            "target_mean",
            "target_scale",
        ):
            if name in data:
                data[name] = tuple(data[name])
        return cls(**data)

    def standardize_features(self, raw_features: np.ndarray) -> np.ndarray:
        values = np.asarray(raw_features, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.feature_names):
            raise ValueError("Raw feature matrix does not match ANN manifest dimensions.")
        mean = np.asarray(self.feature_mean, dtype=float)
        scale = np.asarray(self.feature_scale, dtype=float)
        return (values - mean) / scale

    def restore_targets(self, standardized_targets: np.ndarray) -> np.ndarray:
        values = np.asarray(standardized_targets, dtype=float)
        if values.ndim != 2 or values.shape[1] != len(self.target_names):
            raise ValueError("Target matrix does not match ANN manifest dimensions.")
        mean = np.asarray(self.target_mean, dtype=float)
        scale = np.asarray(self.target_scale, dtype=float)
        return values * scale + mean
