from __future__ import annotations

from dataclasses import asdict, dataclass

from rc_bridge.design.eurocode_cracking import CrackWidthResult
from rc_bridge.design.eurocode_deflection import DeflectionResult


@dataclass(frozen=True)
class ServiceabilityTrainingRecord:
    girder_index: int
    service_moment_knm: float
    crack_width_mm: float
    crack_limit_mm: float
    g_crack_mm: float
    crack_utilization: float
    deflection_mm: float
    deflection_limit_mm: float
    g_deflection_mm: float
    deflection_utilization: float
    verified_solver: bool

    def to_dict(self) -> dict[str, float | int | bool]:
        return asdict(self)


def serviceability_record_from_results(
    girder_index: int,
    service_moment_knm: float,
    crack: CrackWidthResult,
    deflection: DeflectionResult,
    *,
    verified_solver: bool,
) -> ServiceabilityTrainingRecord:
    if girder_index <= 0:
        raise ValueError("girder_index must be positive.")
    if service_moment_knm < 0:
        raise ValueError("Service moment cannot be negative.")

    return ServiceabilityTrainingRecord(
        girder_index=girder_index,
        service_moment_knm=service_moment_knm,
        crack_width_mm=crack.crack_width_mm,
        crack_limit_mm=crack.crack_limit_mm,
        g_crack_mm=crack.g_crack_mm,
        crack_utilization=crack.utilization,
        deflection_mm=deflection.interpolated_deflection_mm,
        deflection_limit_mm=deflection.allowable_deflection_mm,
        g_deflection_mm=deflection.g_deflection_mm,
        deflection_utilization=deflection.utilization,
        verified_solver=verified_solver,
    )


def require_verified_serviceability_records(
    records: list[ServiceabilityTrainingRecord],
) -> None:
    if any(not record.verified_solver for record in records):
        raise ValueError(
            "ANN training dataset contains unverified serviceability solver records."
        )
