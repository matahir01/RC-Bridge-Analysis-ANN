from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO

from rc_bridge.codes.common import LoadEffects


@dataclass(frozen=True)
class GrillageImportMetadata:
    source_software: str
    model_name: str
    load_case: str
    method: str = "imported_grillage_envelope"
    force_unit: str = "kN"
    moment_unit: str = "kNm"

    def __post_init__(self) -> None:
        if not self.source_software.strip():
            raise ValueError("source_software is required.")
        if not self.model_name.strip():
            raise ValueError("model_name is required.")
        if not self.load_case.strip():
            raise ValueError("load_case is required.")
        if self.force_unit != "kN" or self.moment_unit != "kNm":
            raise ValueError(
                "The first grillage import format accepts only kN forces and kNm moments; "
                "convert externally or add an explicit unit-conversion layer."
            )


@dataclass(frozen=True)
class ImportedGirderEffect:
    girder_index: int
    effects: LoadEffects

    def __post_init__(self) -> None:
        if self.girder_index <= 0:
            raise ValueError("girder_index must be positive.")
        if self.effects.moment_knm < 0.0:
            raise ValueError("Imported envelope moment must be non-negative.")
        if self.effects.shear_kn < 0.0:
            raise ValueError("Imported envelope shear must be non-negative.")


@dataclass(frozen=True)
class ImportedGrillageEnvelope:
    metadata: GrillageImportMetadata
    girder_effects: tuple[ImportedGirderEffect, ...]

    def __post_init__(self) -> None:
        if not self.girder_effects:
            raise ValueError("At least one imported girder effect is required.")
        indices = [item.girder_index for item in self.girder_effects]
        if len(set(indices)) != len(indices):
            raise ValueError("Duplicate girder indices are not allowed in a grillage import.")
        expected = list(range(1, len(indices) + 1))
        if sorted(indices) != expected:
            raise ValueError(
                "Imported girder indices must form a complete consecutive set starting at 1."
            )

    @property
    def girder_count(self) -> int:
        return len(self.girder_effects)

    def effect_for_girder(self, girder_index: int) -> LoadEffects:
        for item in self.girder_effects:
            if item.girder_index == girder_index:
                return item.effects
        raise IndexError(f"Girder {girder_index} is not present in the imported envelope.")


_REQUIRED_COLUMNS = {"girder_index", "moment_knm", "shear_kn"}
_OPTIONAL_COLUMNS = {"torsion_knm"}


def parse_grillage_effects_csv(
    text: str,
    *,
    metadata: GrillageImportMetadata,
    expected_girder_count: int | None = None,
) -> ImportedGrillageEnvelope:
    """Parse direct per-girder grillage envelope results from CSV text.

    Required columns are ``girder_index,moment_knm,shear_kn``. Optional
    ``torsion_knm`` is accepted and defaults to zero. Values represent envelope
    magnitudes for one named characteristic load case; signs and load
    combinations should be resolved in the source analysis before import.
    """
    reader = csv.DictReader(StringIO(text))
    fieldnames = set(reader.fieldnames or [])
    missing = _REQUIRED_COLUMNS - fieldnames
    if missing:
        raise ValueError(f"Missing required grillage CSV columns: {sorted(missing)}")
    unexpected = fieldnames - _REQUIRED_COLUMNS - _OPTIONAL_COLUMNS
    if unexpected:
        raise ValueError(f"Unexpected grillage CSV columns: {sorted(unexpected)}")

    effects: list[ImportedGirderEffect] = []
    for row_number, row in enumerate(reader, start=2):
        try:
            girder_index = int(row["girder_index"])
            moment_knm = float(row["moment_knm"])
            shear_kn = float(row["shear_kn"])
            torsion_text = row.get("torsion_knm") or "0"
            torsion_knm = float(torsion_text)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric value in grillage CSV row {row_number}.") from exc

        effects.append(
            ImportedGirderEffect(
                girder_index=girder_index,
                effects=LoadEffects(
                    moment_knm=moment_knm,
                    shear_kn=shear_kn,
                    torsion_knm=torsion_knm,
                ),
            )
        )

    envelope = ImportedGrillageEnvelope(metadata=metadata, girder_effects=tuple(effects))
    if expected_girder_count is not None and envelope.girder_count != expected_girder_count:
        raise ValueError(
            "Imported grillage girder count does not match the project: "
            f"{envelope.girder_count} != {expected_girder_count}."
        )
    return envelope
