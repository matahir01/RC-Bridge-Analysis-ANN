from __future__ import annotations

from dataclasses import asdict, dataclass

from rc_bridge.design.girder_design import GirderDesignResult


@dataclass(frozen=True)
class GirderTrainingRecord:
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
    verified_solver: bool

    def to_dict(self) -> dict[str, float | int | bool]:
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
    verified_solver: bool,
) -> GirderTrainingRecord:
    """Convert a deterministic design result into ANN-ready continuous outputs.

    Unverified results may be serialized for debugging, but downstream training
    code must reject records where verified_solver is False.
    """
    shear_steel = 0.0
    if design.shear.shear_reinforcement is not None:
        shear_steel = design.shear.shear_reinforcement.asw_per_s_mm2_per_m

    return GirderTrainingRecord(
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
        verified_solver=verified_solver,
    )


def require_verified_records(records: list[GirderTrainingRecord]) -> None:
    if any(not record.verified_solver for record in records):
        raise ValueError("ANN training dataset contains unverified deterministic solver records.")
