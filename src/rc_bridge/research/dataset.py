from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class TrainingRecord:
    span_m: float
    girder_spacing_m: float
    girder_depth_m: float
    deck_thickness_m: float
    fck_mpa: float
    fyk_mpa: float
    steel_area_mm2: float
    permanent_moment_knm: float
    traffic_moment_knm: float
    design_moment_knm: float
    resistance_moment_knm: float
    g_flexure_knm: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def records_to_rows(records: Iterable[TrainingRecord]) -> list[dict[str, float]]:
    return [record.to_dict() for record in records]
