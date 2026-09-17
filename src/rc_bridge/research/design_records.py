from __future__ import annotations

from dataclasses import asdict, dataclass

from rc_bridge.design.girder_design import GirderDesignResult
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)


@dataclass(frozen=True)
class GirderTrainingRecord:
    solver_profile: str
    girder_index: int
    span_m: float
    girder_spacing_m: float
    girder_depth_m: float
    effective_depth_m: float
    web_width_m: float
    fck_mpa: float
    fyk_mpa: float
    provided_steel_area_mm2: float
    design_moment_knm: float
    design_shear_kn: float
    moment_resistance_knm: float
    concrete_shear_resistance_kn: float
    required_steel_area_mm2: float
    required_shear_steel_mm2_per_m: float
    flexure_utilization: float
    shear_utilization_concrete_only: float
    g_flexure_knm: float
    g_shear_kn: float

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


def training_record_from_design(
    design: GirderDesignResult,
    *,
    span_m: float,
    girder_spacing_m: float,
    girder_depth_m: float,
    effective_depth_m: float,
    web_width_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    provided_steel_area_mm2: float,
    verification: DeterministicSolverVerification,
) -> GirderTrainingRecord:
    """Convert a verified Eurocode deterministic design into ANN-ready outputs."""
    verification.require_ann_ready(expected_profile=SolverProfile.EUROCODE_1G)

    shear_steel = 0.0
    if design.shear.shear_reinforcement is not None:
        shear_steel = design.shear.shear_reinforcement.asw_per_s_mm2_per_m

    return GirderTrainingRecord(
        solver_profile=SolverProfile.EUROCODE_1G.value,
        girder_index=design.girder_index,
        span_m=span_m,
        girder_spacing_m=girder_spacing_m,
        girder_depth_m=girder_depth_m,
        effective_depth_m=effective_depth_m,
        web_width_m=web_width_m,
        fck_mpa=fck_mpa,
        fyk_mpa=fyk_mpa,
        provided_steel_area_mm2=provided_steel_area_mm2,
        design_moment_knm=design.design_effects.moment_knm,
        design_shear_kn=abs(design.design_effects.shear_kn),
        moment_resistance_knm=design.flexure.resistance_knm,
        concrete_shear_resistance_kn=design.shear.concrete_resistance_kn,
        required_steel_area_mm2=design.flexure.required_steel_area_mm2,
        required_shear_steel_mm2_per_m=shear_steel,
        flexure_utilization=design.flexure.utilization,
        shear_utilization_concrete_only=design.shear.utilization_concrete_only,
        g_flexure_knm=design.flexure.g_flexure_knm,
        g_shear_kn=design.shear.g_shear_concrete_kn,
    )


def require_verified_records(records: list[GirderTrainingRecord]) -> None:
    """Reject records that do not carry the expected Eurocode solver provenance."""
    expected = SolverProfile.EUROCODE_1G.value
    if any(record.solver_profile != expected for record in records):
        raise ValueError(
            "ANN girder dataset contains records from an unexpected or unverified solver profile."
        )
