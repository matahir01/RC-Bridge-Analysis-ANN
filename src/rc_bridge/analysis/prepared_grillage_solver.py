from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import csc_matrix, lil_matrix
from scipy.sparse.linalg import splu

from rc_bridge.analysis.grillage_solver import (
    GrillageAnalysisResult,
    GrillageMemberEndResult,
    GrillageNodeResult,
    _element_mechanics,
    _member_load_vector,
    _node_dofs,
    _selected_load_case,
)
from rc_bridge.export.verification_model import VerificationModel


def vertical_grillage_structure_signature(model: VerificationModel) -> tuple[object, ...]:
    """Return the load-independent identity of a vertical grillage model.

    Load-case names, loads, metadata and the top-level model name are deliberately
    excluded. Models with the same nodes/materials/sections/members/supports can
    reuse one sparse stiffness factorization.
    """

    return (
        model.nodes,
        model.materials,
        model.sections,
        model.beams,
        model.supports,
    )


@dataclass(frozen=True)
class PreparedVerticalGrillage:
    """Load-independent sparse grillage system ready for repeated load solves."""

    structure_signature: tuple[object, ...]
    node_index_by_id: dict[int, int]
    mechanics: tuple[object, ...]
    stiffness: csc_matrix
    constrained_dofs: frozenset[int]
    free_dofs: tuple[int, ...]
    reduced_factorization: object

    @property
    def dof_count(self) -> int:
        return self.stiffness.shape[0]


def prepare_vertical_grillage(
    model: VerificationModel,
    *,
    load_case_id: int | None = None,
) -> PreparedVerticalGrillage:
    """Assemble and factorize the load-independent grillage stiffness once."""

    # The selected case is needed only because the legacy element helper also
    # computes an equivalent load vector. Its stiffness/transformation are load
    # independent and are the values retained below.
    load_case = _selected_load_case(model, load_case_id)
    node_index_by_id = {
        node.node_id: index for index, node in enumerate(model.nodes)
    }
    dof_count = 3 * len(model.nodes)
    stiffness = lil_matrix((dof_count, dof_count), dtype=float)

    mechanics = tuple(
        _element_mechanics(
            model,
            beam,
            load_case,
            node_index_by_id,
        )
        for beam in model.beams
    )
    for element in mechanics:
        dofs = element.global_dofs
        global_stiffness = (
            element.transformation.T
            @ element.local_stiffness
            @ element.transformation
        )
        for local_row, global_row in enumerate(dofs):
            for local_col, global_col in enumerate(dofs):
                value = float(global_stiffness[local_row, local_col])
                if value != 0.0:
                    stiffness[global_row, global_col] += value

    constrained: set[int] = set()
    for support in model.supports:
        if support.rz:
            raise ValueError("Native vertical grillage solver does not model Rz restraint.")
        w_dof, rx_dof, ry_dof = _node_dofs(
            node_index_by_id[support.node_id]
        )
        if support.uz:
            constrained.add(w_dof)
        if support.rx:
            constrained.add(rx_dof)
        if support.ry:
            constrained.add(ry_dof)

    if not constrained:
        raise ValueError("Grillage model has no restraints in the active vertical DOFs.")
    free = tuple(index for index in range(dof_count) if index not in constrained)
    stiffness_csc = stiffness.tocsc()
    reduced = stiffness_csc[list(free), :][:, list(free)].tocsc()
    try:
        factorization = splu(reduced)
    except RuntimeError as exc:
        raise ValueError(
            "Grillage stiffness matrix is singular; check vertical/rotational supports, "
            "member connectivity and torsional mechanisms."
        ) from exc

    return PreparedVerticalGrillage(
        structure_signature=vertical_grillage_structure_signature(model),
        node_index_by_id=node_index_by_id,
        mechanics=mechanics,
        stiffness=stiffness_csc,
        constrained_dofs=frozenset(constrained),
        free_dofs=free,
        reduced_factorization=factorization,
    )


def solve_prepared_vertical_grillage(
    prepared: PreparedVerticalGrillage,
    model: VerificationModel,
    *,
    load_case_id: int | None = None,
) -> GrillageAnalysisResult:
    """Solve a new load case using an existing sparse stiffness factorization."""

    if vertical_grillage_structure_signature(model) != prepared.structure_signature:
        raise ValueError(
            "Prepared grillage structure does not match the supplied model. "
            "Nodes, materials, sections, members and supports must be identical."
        )
    load_case = _selected_load_case(model, load_case_id)
    loads = np.zeros(prepared.dof_count, dtype=float)
    local_equivalent_loads: list[np.ndarray] = []

    for element in prepared.mechanics:
        local_load = _member_load_vector(
            model,
            load_case,
            element.beam,
            length_m=element.length_m,
        )
        local_equivalent_loads.append(local_load)
        dofs = np.array(element.global_dofs, dtype=int)
        loads[dofs] += element.transformation.T @ local_load

    for load in load_case.nodal_loads:
        if abs(load.fx_kn) > 1.0e-12 or abs(load.fy_kn) > 1.0e-12:
            raise ValueError(
                "Native vertical grillage solver does not model in-plane nodal forces."
            )
        if abs(load.mz_knm) > 1.0e-12:
            raise ValueError(
                "Native vertical grillage solver does not model nodal Mz drilling moment."
            )
        w_dof, rx_dof, ry_dof = _node_dofs(
            prepared.node_index_by_id[load.node_id]
        )
        loads[w_dof] += load.fz_kn
        loads[rx_dof] += load.mx_knm
        loads[ry_dof] += load.my_knm

    displacement = np.zeros(prepared.dof_count, dtype=float)
    free = list(prepared.free_dofs)
    displacement[free] = prepared.reduced_factorization.solve(loads[free])
    residual = np.asarray(prepared.stiffness @ displacement).reshape(-1) - loads

    node_results: list[GrillageNodeResult] = []
    for node_index, node in enumerate(model.nodes):
        w_dof, rx_dof, ry_dof = _node_dofs(node_index)
        node_results.append(
            GrillageNodeResult(
                node_id=node.node_id,
                vertical_displacement_m=float(displacement[w_dof]),
                rotation_x_rad=float(displacement[rx_dof]),
                rotation_y_rad=float(displacement[ry_dof]),
                vertical_reaction_kn=(
                    float(residual[w_dof])
                    if w_dof in prepared.constrained_dofs
                    else 0.0
                ),
                reaction_mx_knm=(
                    float(residual[rx_dof])
                    if rx_dof in prepared.constrained_dofs
                    else 0.0
                ),
                reaction_my_knm=(
                    float(residual[ry_dof])
                    if ry_dof in prepared.constrained_dofs
                    else 0.0
                ),
            )
        )

    member_results: list[GrillageMemberEndResult] = []
    for element, local_load in zip(
        prepared.mechanics,
        local_equivalent_loads,
        strict=True,
    ):
        dofs = np.array(element.global_dofs, dtype=int)
        local_displacement = element.transformation @ displacement[dofs]
        local_end_action = (
            element.local_stiffness @ local_displacement - local_load
        )
        member_results.append(
            GrillageMemberEndResult(
                member_id=element.beam.member_id,
                node_i=element.beam.node_i,
                node_j=element.beam.node_j,
                length_m=element.length_m,
                i_vertical_force_kn=float(local_end_action[0]),
                i_vertical_bending_moment_knm=float(-local_end_action[1]),
                i_torsion_knm=float(local_end_action[2]),
                j_vertical_force_kn=float(local_end_action[3]),
                j_vertical_bending_moment_knm=float(-local_end_action[4]),
                j_torsion_knm=float(local_end_action[5]),
            )
        )

    total_applied_vertical = float(sum(loads[0::3]))
    total_vertical_reaction = float(
        sum(result.vertical_reaction_kn for result in node_results)
    )
    return GrillageAnalysisResult(
        load_case_id=load_case.load_case_id,
        load_case_name=load_case.name,
        nodes=tuple(node_results),
        members=tuple(member_results),
        total_applied_vertical_load_kn=total_applied_vertical,
        total_vertical_reaction_kn=total_vertical_reaction,
        vertical_equilibrium_residual_kn=(
            total_vertical_reaction + total_applied_vertical
        ),
    )
