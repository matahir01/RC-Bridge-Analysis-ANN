from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    ImportedGirderEffect,
    ImportedGrillageEnvelope,
)
from rc_bridge.analysis.grillage_solver import GrillageAnalysisResult
from rc_bridge.codes.common import LoadEffects
from rc_bridge.export.verification_model import VerificationBeam, VerificationModel


@dataclass(frozen=True)
class NativeGirderEnvelopeDetail:
    """Trace the governing native end result behind one per-girder envelope."""

    girder_index: int
    y_m: float
    effects: LoadEffects
    governing_moment_member_id: int
    governing_shear_member_id: int
    governing_torsion_member_id: int


@dataclass(frozen=True)
class NativeGrillageEnvelopeResult:
    """Native grillage envelope plus compatibility view for existing design workflows."""

    envelope: ImportedGrillageEnvelope
    details: tuple[NativeGirderEnvelopeDetail, ...]


def _member_plan_vector(
    model: VerificationModel,
    beam: VerificationBeam,
) -> tuple[float, float, float, float]:
    nodes = {node.node_id: node for node in model.nodes}
    ni = nodes[beam.node_i]
    nj = nodes[beam.node_j]
    return nj.x_m - ni.x_m, nj.y_m - ni.y_m, ni.y_m, nj.y_m


def _longitudinal_groups(
    model: VerificationModel,
    *,
    tolerance: float,
) -> tuple[tuple[float, tuple[VerificationBeam, ...]], ...]:
    groups: dict[float, list[VerificationBeam]] = {}
    for beam in model.beams:
        dx, dy, y_i, y_j = _member_plan_vector(model, beam)
        if abs(dy) <= tolerance and abs(dx) > tolerance:
            y = 0.5 * (y_i + y_j)
            matched_key = next(
                (key for key in groups if abs(key - y) <= tolerance),
                None,
            )
            key = y if matched_key is None else matched_key
            groups.setdefault(key, []).append(beam)
        elif abs(dx) <= tolerance and abs(dy) > tolerance:
            continue
        else:
            raise ValueError(
                "Native per-girder envelope currently requires an orthogonal grillage; "
                f"member {beam.member_id} is diagonal or degenerate in plan."
            )
    if not groups:
        raise ValueError("Native grillage envelope found no longitudinal girder members.")

    nodes = {node.node_id: node for node in model.nodes}
    ordered: list[tuple[float, tuple[VerificationBeam, ...]]] = []
    for y, beams in sorted(groups.items()):
        ordered.append(
            (
                y,
                tuple(
                    sorted(
                        beams,
                        key=lambda beam: min(
                            nodes[beam.node_i].x_m,
                            nodes[beam.node_j].x_m,
                        ),
                    )
                ),
            )
        )
    return tuple(ordered)


def _require_end_envelope_compatible_traffic_loads(
    model: VerificationModel,
    *,
    longitudinal_member_ids: set[int],
    load_case_id: int,
) -> None:
    load_case = next(
        (case for case in model.load_cases if case.load_case_id == load_case_id),
        None,
    )
    if load_case is None:
        raise ValueError(f"Unknown native grillage load case {load_case_id}.")
    if abs(load_case.self_weight_gz_factor) > 1.0e-12:
        raise ValueError(
            "Native per-girder end envelope does not yet admit self-weight; use the existing "
            "permanent-load workflow until distributed-load section recovery is implemented."
        )
    loaded_longitudinal = {
        load.member_id
        for load in (*load_case.uniform_loads, *load_case.point_loads)
        if load.member_id in longitudinal_member_ids
    }
    if loaded_longitudinal:
        ids = ", ".join(str(value) for value in sorted(loaded_longitudinal))
        raise ValueError(
            "Native per-girder end envelope currently requires longitudinal members to be "
            "load-free between grid stations; loaded longitudinal member IDs: " + ids
        )


def native_grillage_traffic_envelope(
    model: VerificationModel,
    analysis: GrillageAnalysisResult,
    *,
    coordinate_tolerance: float = 1.0e-9,
) -> NativeGrillageEnvelopeResult:
    """Reduce a native traffic grillage solution to per-girder M/V/T envelope magnitudes.

    This first envelope generation is exact for the LM1-style native traffic model,
    where deck pressure and tandem wheels are transferred through nodal or transverse-
    member loading and longitudinal girder segments are load-free between generated
    x stations. In that case longitudinal member force fields have no interior load
    discontinuity/extremum missed by their end actions.

    Distributed/self-weight loading on longitudinal members is rejected until exact
    section-force recovery is added; permanent loading stays in the existing project
    permanent-load workflow.
    """
    if coordinate_tolerance <= 0.0:
        raise ValueError("coordinate_tolerance must be positive.")
    if analysis.load_case_id not in {case.load_case_id for case in model.load_cases}:
        raise ValueError("Native grillage analysis load case is not present in the model.")

    groups = _longitudinal_groups(model, tolerance=coordinate_tolerance)
    longitudinal_ids = {
        beam.member_id for _, beams in groups for beam in beams
    }
    _require_end_envelope_compatible_traffic_loads(
        model,
        longitudinal_member_ids=longitudinal_ids,
        load_case_id=analysis.load_case_id,
    )

    result_by_member = {item.member_id: item for item in analysis.members}
    if set(result_by_member) != {beam.member_id for beam in model.beams}:
        raise ValueError("Native grillage analysis/member model identities are inconsistent.")

    imported_effects: list[ImportedGirderEffect] = []
    details: list[NativeGirderEnvelopeDetail] = []
    for girder_index, (y_m, beams) in enumerate(groups, start=1):
        moment_candidates: list[tuple[float, int]] = []
        shear_candidates: list[tuple[float, int]] = []
        torsion_candidates: list[tuple[float, int]] = []
        for beam in beams:
            result = result_by_member[beam.member_id]
            moment_candidates.extend(
                (
                    (abs(result.i_vertical_bending_moment_knm), beam.member_id),
                    (abs(result.j_vertical_bending_moment_knm), beam.member_id),
                )
            )
            shear_candidates.extend(
                (
                    (abs(result.i_vertical_force_kn), beam.member_id),
                    (abs(result.j_vertical_force_kn), beam.member_id),
                )
            )
            torsion_candidates.extend(
                (
                    (abs(result.i_torsion_knm), beam.member_id),
                    (abs(result.j_torsion_knm), beam.member_id),
                )
            )

        moment, moment_member = max(moment_candidates)
        shear, shear_member = max(shear_candidates)
        torsion, torsion_member = max(torsion_candidates)
        effects = LoadEffects(
            moment_knm=moment,
            shear_kn=shear,
            torsion_knm=torsion,
        )
        imported_effects.append(
            ImportedGirderEffect(girder_index=girder_index, effects=effects)
        )
        details.append(
            NativeGirderEnvelopeDetail(
                girder_index=girder_index,
                y_m=y_m,
                effects=effects,
                governing_moment_member_id=moment_member,
                governing_shear_member_id=shear_member,
                governing_torsion_member_id=torsion_member,
            )
        )

    metadata = GrillageImportMetadata(
        source_software="RC-Bridge native vertical grillage",
        model_name=model.name,
        load_case=analysis.load_case_name,
        method="native_grillage_end_envelope",
    )
    return NativeGrillageEnvelopeResult(
        envelope=ImportedGrillageEnvelope(
            metadata=metadata,
            girder_effects=tuple(imported_effects),
        ),
        details=tuple(details),
    )
