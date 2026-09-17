from __future__ import annotations

from dataclasses import asdict, dataclass

from rc_bridge.design.eurocode_cracking import CrackWidthResult
from rc_bridge.design.eurocode_deflection import DeflectionResult
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)


@dataclass(frozen=True)
class ServiceabilityTrainingRecord:
    solver_profile: str
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

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def serviceability_record_from_results(
    girder_index: int,
    service_moment_knm: float,
    crack: CrackWidthResult,
    deflection: DeflectionResult,
    *,
    verification: DeterministicSolverVerification,
) -> ServiceabilityTrainingRecord:
    if girder_index <= 0:
        raise ValueError("girder_index must be positive.")
    if service_moment_knm < 0:
        raise ValueError("Service moment cannot be negative.")
    verification.require_ann_ready(expected_profile=SolverProfile.EUROCODE_1G)

    return ServiceabilityTrainingRecord(
        solver_profile=SolverProfile.EUROCODE_1G.value,
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
    )


def require_verified_serviceability_records(
    records: list[ServiceabilityTrainingRecord],
) -> None:
    expected = SolverProfile.EUROCODE_1G.value
    if any(record.solver_profile != expected for record in records):
        raise ValueError(
            "ANN serviceability dataset contains records from an unexpected or unverified solver profile."
        )
