from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationModel,
)


@dataclass(frozen=True)
class GrillageNodeResult:
    node_id: int
    vertical_displacement_m: float
    rotation_x_rad: float
    rotation_y_rad: float
    vertical_reaction_kn: float
    reaction_mx_knm: float
    reaction_my_knm: float


@dataclass(frozen=True)
class GrillageMemberEndResult:
    member_id: int
    node_i: int
    node_j: int
    length_m: float
    i_vertical_force_kn: float
    i_vertical_bending_moment_knm: float
    i_torsion_knm: float
    j_vertical_force_kn: float
    j_vertical_bending_moment_knm: float
    j_torsion_knm: float


@dataclass(frozen=True)
class GrillageAnalysisResult:
    load_case_id: int
    load_case_name: str
    nodes: tuple[GrillageNodeResult, ...]
    members: tuple[GrillageMemberEndResult, ...]
    total_applied_vertical_load_kn: float
    total_vertical_reaction_kn: float
    vertical_equilibrium_residual_kn: float


@dataclass(frozen=True)
class _ElementMechanics:
    beam: VerificationBeam
    length_m: float
    transformation: np.ndarray
    local_stiffness: np.ndarray
    global_dofs: tuple[int, ...]


@dataclass(frozen=True)
class PreparedVerticalGrillageSystem:
    """Reusable stiffness/factorization for repeated load cases on one grillage."""

    structural_signature: tuple[object, ...]
    node_index_by_id: dict[int, int]
    mechanics: tuple[_ElementMechanics, ...]
    stiffness: np.ndarray
    free_dofs: tuple[int, ...]
    constrained_dofs: frozenset[int]
    reduced_lu: tuple[np.ndarray, np.ndarray]


def _selected_load_case(model: VerificationModel, load_case_id: int | None) -> VerificationLoadCase:
    if load_case_id is None:
        if len(model.load_cases) != 1:
            raise ValueError(
                "Grillage analysis requires load_case_id when the model has more than one load case."
            )
        return model.load_cases[0]
    match = next((case for case in model.load_cases if case.load_case_id == load_case_id), None)
    if match is None:
        raise ValueError(f"Unknown grillage load case {load_case_id}.")
    return match


def _node_dofs(node_index: int) -> tuple[int, int, int]:
    start = 3 * node_index
    return start, start + 1, start + 2


def _horizontal_basis(
    model: VerificationModel,
    beam: VerificationBeam,
) -> tuple[float, float, float]:
    nodes = {node.node_id: node for node in model.nodes}
    ni = nodes[beam.node_i]
    nj = nodes[beam.node_j]
    dx = nj.x_m - ni.x_m
    dy = nj.y_m - ni.y_m
    dz = nj.z_m - ni.z_m
    if abs(dz) > 1.0e-9:
        raise ValueError(
            f"Vertical grillage solver requires horizontal members; member {beam.member_id} "
            f"has dz={dz:.6g} m."
        )
    if abs(beam.beta_angle_deg) > 1.0e-9:
        raise ValueError("Vertical grillage solver currently requires beta_angle_deg=0.")
    length = math.hypot(dx, dy)
    if length <= 1.0e-12:
        raise ValueError(f"Grillage member {beam.member_id} has zero plan length.")
    return dx / length, dy / length, length


def _element_transformation(cx: float, cy: float) -> np.ndarray:
    """Map global [w,Rx,Ry] DOFs to local [w,slope,twist] at each end.

    Local x follows I-to-J, local z is global +Z, and local y = z cross x.
    The Euler-Bernoulli slope ``dw/dx`` is the negative of physical rotation
    about local +y. Hence slope = cy*Rx - cx*Ry.
    """
    node_transform = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, cy, -cx],
            [0.0, cx, cy],
        ],
        dtype=float,
    )
    transformation = np.zeros((6, 6), dtype=float)
    transformation[:3, :3] = node_transform
    transformation[3:, 3:] = node_transform
    return transformation


def _local_stiffness(*, length_m: float, ei_kn_m2: float, gj_kn_m2: float) -> np.ndarray:
    length = length_m
    bending = ei_kn_m2 / (length**3)
    torsion = gj_kn_m2 / length
    matrix = np.zeros((6, 6), dtype=float)

    # Bending DOFs [w_i, slope_i, w_j, slope_j].
    bending_dofs = (0, 1, 3, 4)
    bending_matrix = bending * np.array(
        [
            [12.0, 6.0 * length, -12.0, 6.0 * length],
            [6.0 * length, 4.0 * length**2, -6.0 * length, 2.0 * length**2],
            [-12.0, -6.0 * length, 12.0, -6.0 * length],
            [6.0 * length, 2.0 * length**2, -6.0 * length, 4.0 * length**2],
        ],
        dtype=float,
    )
    for row_index, row_dof in enumerate(bending_dofs):
        for column_index, column_dof in enumerate(bending_dofs):
            matrix[row_dof, column_dof] = bending_matrix[row_index, column_index]

    matrix[2, 2] = torsion
    matrix[2, 5] = -torsion
    matrix[5, 2] = -torsion
    matrix[5, 5] = torsion
    return matrix


def _hermite_shape(length_m: float, position_m: float) -> np.ndarray:
    xi = position_m / length_m
    return np.array(
        [
            1.0 - 3.0 * xi**2 + 2.0 * xi**3,
            length_m * (xi - 2.0 * xi**2 + xi**3),
            3.0 * xi**2 - 2.0 * xi**3,
            length_m * (-xi**2 + xi**3),
        ],
        dtype=float,
    )


def _point_vertical_local_load(
    *,
    length_m: float,
    position_m: float,
    magnitude_kn: float,
) -> np.ndarray:
    if position_m < -1.0e-9 or position_m > length_m + 1.0e-9:
        raise ValueError("Grillage member point load lies outside its member.")
    position = min(max(position_m, 0.0), length_m)
    shape = _hermite_shape(length_m, position)
    vector = np.zeros(6, dtype=float)
    vector[[0, 1, 3, 4]] = magnitude_kn * shape
    return vector


def _uniform_vertical_local_load(
    *,
    length_m: float,
    start_m: float,
    end_m: float,
    magnitude_kn_m: float,
) -> np.ndarray:
    if start_m < -1.0e-9 or end_m > length_m + 1.0e-9 or end_m <= start_m:
        raise ValueError("Grillage member UDL bounds are invalid.")
    # Four-point Gauss integration is exact for the cubic Hermite shape functions.
    gauss_x, gauss_w = np.polynomial.legendre.leggauss(4)
    midpoint = 0.5 * (start_m + end_m)
    half_range = 0.5 * (end_m - start_m)
    integrated = np.zeros(4, dtype=float)
    for coordinate, weight in zip(gauss_x, gauss_w, strict=True):
        x = midpoint + half_range * float(coordinate)
        integrated += float(weight) * _hermite_shape(length_m, x)
    integrated *= half_range * magnitude_kn_m
    vector = np.zeros(6, dtype=float)
    vector[[0, 1, 3, 4]] = integrated
    return vector


def _member_load_vector(
    model: VerificationModel,
    load_case: VerificationLoadCase,
    beam: VerificationBeam,
    *,
    length_m: float,
) -> np.ndarray:
    vector = np.zeros(6, dtype=float)
    material = next(item for item in model.materials if item.material_id == beam.material_id)
    section = next(item for item in model.sections if item.section_id == beam.section_id)

    if load_case.self_weight_gz_factor != 0.0:
        self_weight = (
            section.area_m2
            * material.weight_density_kn_m3
            * load_case.self_weight_gz_factor
        )
        vector += _uniform_vertical_local_load(
            length_m=length_m,
            start_m=0.0,
            end_m=length_m,
            magnitude_kn_m=self_weight,
        )

    for load in load_case.uniform_loads:
        if load.member_id != beam.member_id:
            continue
        if load.direction != "GZ":
            raise ValueError("Native grillage solver currently supports member UDL only in GZ.")
        start = 0.0 if load.start_m is None else load.start_m
        end = length_m if load.end_m is None else load.end_m
        vector += _uniform_vertical_local_load(
            length_m=length_m,
            start_m=start,
            end_m=end,
            magnitude_kn_m=load.magnitude_kn_m,
        )

    for load in load_case.point_loads:
        if load.member_id != beam.member_id:
            continue
        if load.direction != "GZ":
            raise ValueError("Native grillage solver currently supports member point loads only in GZ.")
        vector += _point_vertical_local_load(
            length_m=length_m,
            position_m=load.distance_from_i_m,
            magnitude_kn=load.magnitude_kn,
        )
    return vector


def _element_mechanics(
    model: VerificationModel,
    beam: VerificationBeam,
    node_index_by_id: dict[int, int],
) -> _ElementMechanics:
    cx, cy, length = _horizontal_basis(model, beam)
    material = next(item for item in model.materials if item.material_id == beam.material_id)
    section = next(item for item in model.sections if item.section_id == beam.section_id)
    e_kn_m2 = material.elastic_modulus_kn_m2
    g_kn_m2 = e_kn_m2 / (2.0 * (1.0 + material.poisson_ratio))
    local_stiffness = _local_stiffness(
        length_m=length,
        ei_kn_m2=e_kn_m2 * section.iy_m4,
        gj_kn_m2=g_kn_m2 * section.torsion_constant_m4,
    )
    transformation = _element_transformation(cx, cy)
    i_dofs = _node_dofs(node_index_by_id[beam.node_i])
    j_dofs = _node_dofs(node_index_by_id[beam.node_j])
    return _ElementMechanics(
        beam=beam,
        length_m=length,
        transformation=transformation,
        local_stiffness=local_stiffness,
        global_dofs=(*i_dofs, *j_dofs),
    )


def _structural_signature(model: VerificationModel) -> tuple[object, ...]:
    """Return the load-independent model identity used by prepared systems."""

    return (
        model.nodes,
        model.materials,
        model.sections,
        model.beams,
        model.supports,
    )


def prepare_vertical_grillage(model: VerificationModel) -> PreparedVerticalGrillageSystem:
    """Assemble and factorize the load-independent vertical grillage stiffness once."""

    node_index_by_id = {node.node_id: index for index, node in enumerate(model.nodes)}
    dof_count = 3 * len(model.nodes)
    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    mechanics = tuple(
        _element_mechanics(model, beam, node_index_by_id)
        for beam in model.beams
    )
    for element in mechanics:
        dofs = np.array(element.global_dofs, dtype=int)
        global_stiffness = (
            element.transformation.T
            @ element.local_stiffness
            @ element.transformation
        )
        stiffness[np.ix_(dofs, dofs)] += global_stiffness

    constrained: set[int] = set()
    for support in model.supports:
        if support.rz:
            raise ValueError("Native vertical grillage solver does not model Rz restraint.")
        w_dof, rx_dof, ry_dof = _node_dofs(node_index_by_id[support.node_id])
        if support.uz:
            constrained.add(w_dof)
        if support.rx:
            constrained.add(rx_dof)
        if support.ry:
            constrained.add(ry_dof)

    free = tuple(index for index in range(dof_count) if index not in constrained)
    if not constrained:
        raise ValueError("Grillage model has no restraints in the active vertical DOFs.")
    reduced = stiffness[np.ix_(free, free)]
    if np.linalg.matrix_rank(reduced) < reduced.shape[0]:
        raise ValueError(
            "Grillage stiffness matrix is singular; check vertical/rotational supports, "
            "member connectivity and torsional mechanisms."
        )
    return PreparedVerticalGrillageSystem(
        structural_signature=_structural_signature(model),
        node_index_by_id=node_index_by_id,
        mechanics=mechanics,
        stiffness=stiffness,
        free_dofs=free,
        constrained_dofs=frozenset(constrained),
        reduced_lu=lu_factor(reduced),
    )


def solve_vertical_grillage(
    model: VerificationModel,
    *,
    load_case_id: int | None = None,
    prepared: PreparedVerticalGrillageSystem | None = None,
) -> GrillageAnalysisResult:
    """Solve vertical bending/torsion, optionally reusing a prepared stiffness system.

    Reusing a prepared system is mathematically identical to a fresh solve when model
    geometry, material/section stiffness, connectivity and supports are unchanged.
    Only the load vector is rebuilt for each case, which is the intended path for
    moving-load searches containing thousands of LM1 placements.
    """

    load_case = _selected_load_case(model, load_case_id)
    system = prepared or prepare_vertical_grillage(model)
    if system.structural_signature != _structural_signature(model):
        raise ValueError(
            "Prepared grillage system does not match the model geometry/stiffness/supports."
        )

    node_index_by_id = system.node_index_by_id
    dof_count = 3 * len(model.nodes)
    loads = np.zeros(dof_count, dtype=float)
    local_loads: dict[int, np.ndarray] = {}

    for element in system.mechanics:
        dofs = np.array(element.global_dofs, dtype=int)
        local_load = _member_load_vector(
            model,
            load_case,
            element.beam,
            length_m=element.length_m,
        )
        local_loads[element.beam.member_id] = local_load
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
        w_dof, rx_dof, ry_dof = _node_dofs(node_index_by_id[load.node_id])
        loads[w_dof] += load.fz_kn
        loads[rx_dof] += load.mx_knm
        loads[ry_dof] += load.my_knm

    displacement = np.zeros(dof_count, dtype=float)
    free = system.free_dofs
    displacement[list(free)] = lu_solve(system.reduced_lu, loads[list(free)])
    residual = system.stiffness @ displacement - loads

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
                    if w_dof in system.constrained_dofs
                    else 0.0
                ),
                reaction_mx_knm=(
                    float(residual[rx_dof])
                    if rx_dof in system.constrained_dofs
                    else 0.0
                ),
                reaction_my_knm=(
                    float(residual[ry_dof])
                    if ry_dof in system.constrained_dofs
                    else 0.0
                ),
            )
        )

    member_results: list[GrillageMemberEndResult] = []
    for element in system.mechanics:
        dofs = np.array(element.global_dofs, dtype=int)
        local_displacement = element.transformation @ displacement[dofs]
        local_end_action = (
            element.local_stiffness @ local_displacement
            - local_loads[element.beam.member_id]
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
    equilibrium_residual = total_vertical_reaction + total_applied_vertical
    return GrillageAnalysisResult(
        load_case_id=load_case.load_case_id,
        load_case_name=load_case.name,
        nodes=tuple(node_results),
        members=tuple(member_results),
        total_applied_vertical_load_kn=total_applied_vertical,
        total_vertical_reaction_kn=total_vertical_reaction,
        vertical_equilibrium_residual_kn=equilibrium_residual,
    )
