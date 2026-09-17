from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpanPointLoad:
    magnitude_kn: float
    position_m: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.magnitude_kn < 0.0:
            raise ValueError("Point-load magnitude cannot be negative.")
        if self.position_m < 0.0:
            raise ValueError("Point-load position cannot be negative.")


@dataclass(frozen=True)
class BeamSpan:
    length_m: float
    ei_kn_m2: float
    udl_kn_m: float = 0.0
    point_loads: tuple[SpanPointLoad, ...] = ()

    def __post_init__(self) -> None:
        if self.length_m <= 0.0 or self.ei_kn_m2 <= 0.0:
            raise ValueError("Beam-span length and EI must be positive.")
        if self.udl_kn_m < 0.0:
            raise ValueError("UDL cannot be negative.")
        if any(load.position_m > self.length_m for load in self.point_loads):
            raise ValueError("Point load lies outside its beam span.")


@dataclass(frozen=True)
class BeamNodeResult:
    node_index: int
    vertical_displacement_m: float
    rotation_rad: float
    vertical_reaction_kn: float
    moment_reaction_knm: float


@dataclass(frozen=True)
class BeamMemberResult:
    span_index: int
    left_shear_kn: float
    left_moment_knm: float
    right_shear_kn: float
    right_moment_knm: float
    raw_element_end_forces: tuple[float, float, float, float]


@dataclass(frozen=True)
class BeamSectionResponse:
    x_m: float
    shear_kn: float
    moment_knm: float


@dataclass(frozen=True)
class BeamSpanEnvelope:
    span_index: int
    max_sagging_moment_knm: float
    max_sagging_position_m: float
    min_hogging_moment_knm: float
    min_hogging_position_m: float
    max_abs_shear_kn: float
    max_abs_shear_position_m: float


@dataclass(frozen=True)
class ContinuousBeamResult:
    nodes: tuple[BeamNodeResult, ...]
    members: tuple[BeamMemberResult, ...]
    displacements: tuple[float, ...]
    load_vector: tuple[float, ...]
    reaction_vector: tuple[float, ...]
    status: str


def ei_kn_m2_from_mpa_mm4(elastic_modulus_mpa: float, second_moment_mm4: float) -> float:
    """Convert E [MPa] × I [mm4] to EI [kN m2]."""
    if elastic_modulus_mpa <= 0.0 or second_moment_mm4 <= 0.0:
        raise ValueError("Elastic modulus and second moment must be positive.")
    return elastic_modulus_mpa * second_moment_mm4 * 1e-9


def beam_element_stiffness(ei_kn_m2: float, length_m: float) -> np.ndarray:
    """Euler-Bernoulli beam stiffness for [v_i, theta_i, v_j, theta_j]."""
    if ei_kn_m2 <= 0.0 or length_m <= 0.0:
        raise ValueError("EI and element length must be positive.")
    length = length_m
    return (ei_kn_m2 / length**3) * np.array(
        [
            [12.0, 6.0 * length, -12.0, 6.0 * length],
            [6.0 * length, 4.0 * length**2, -6.0 * length, 2.0 * length**2],
            [-12.0, -6.0 * length, 12.0, -6.0 * length],
            [6.0 * length, 2.0 * length**2, -6.0 * length, 4.0 * length**2],
        ],
        dtype=float,
    )


def _udl_consistent_load(udl_kn_m: float, length_m: float) -> np.ndarray:
    """Equivalent nodal load for a downward full-span UDL; v is positive upward."""
    return np.array(
        [
            -udl_kn_m * length_m / 2.0,
            -udl_kn_m * length_m**2 / 12.0,
            -udl_kn_m * length_m / 2.0,
            udl_kn_m * length_m**2 / 12.0,
        ],
        dtype=float,
    )


def _point_load_consistent_load(load: SpanPointLoad, length_m: float) -> np.ndarray:
    """Equivalent nodal load from the cubic Hermite beam shape functions."""
    xi = load.position_m / length_m
    shape = np.array(
        [
            1.0 - 3.0 * xi**2 + 2.0 * xi**3,
            length_m * (xi - 2.0 * xi**2 + xi**3),
            3.0 * xi**2 - 2.0 * xi**3,
            length_m * (-xi**2 + xi**3),
        ],
        dtype=float,
    )
    return -load.magnitude_kn * shape


def beam_span_consistent_load(span: BeamSpan) -> np.ndarray:
    load = _udl_consistent_load(span.udl_kn_m, span.length_m)
    for point in span.point_loads:
        load = load + _point_load_consistent_load(point, span.length_m)
    return load


def solve_continuous_beam(
    spans: tuple[BeamSpan, ...],
    *,
    vertical_support_nodes: tuple[int, ...] | None = None,
    rotational_support_nodes: tuple[int, ...] = (),
) -> ContinuousBeamResult:
    """Solve a prismatic-per-span continuous Euler-Bernoulli beam by stiffness.

    Each ``BeamSpan`` is one physical span between adjacent bridge/support nodes.
    When ``vertical_support_nodes`` is omitted, every span boundary is vertically
    restrained, which is the normal multi-span continuous bridge-girder idealization.

    Sign convention:
    - input UDL/point loads are positive downward magnitudes;
    - vertical displacement is positive upward;
    - support reaction is positive upward;
    - recovered member bending moment is positive sagging, negative hogging.
    """
    if not spans:
        raise ValueError("At least one beam span is required.")

    node_count = len(spans) + 1
    dof_count = 2 * node_count
    support_nodes = (
        tuple(range(node_count)) if vertical_support_nodes is None else vertical_support_nodes
    )
    all_support_nodes = (*support_nodes, *rotational_support_nodes)
    if any(node < 0 or node >= node_count for node in all_support_nodes):
        raise ValueError("Support-node index lies outside the beam model.")
    if len(set(support_nodes)) != len(support_nodes):
        raise ValueError("Duplicate vertical support nodes are not allowed.")
    if len(set(rotational_support_nodes)) != len(rotational_support_nodes):
        raise ValueError("Duplicate rotational support nodes are not allowed.")

    stiffness = np.zeros((dof_count, dof_count), dtype=float)
    loads = np.zeros(dof_count, dtype=float)
    element_data: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []

    for span_index, span in enumerate(spans):
        dofs = np.array(
            [
                2 * span_index,
                2 * span_index + 1,
                2 * (span_index + 1),
                2 * (span_index + 1) + 1,
            ],
            dtype=int,
        )
        local_stiffness = beam_element_stiffness(span.ei_kn_m2, span.length_m)
        local_load = beam_span_consistent_load(span)
        stiffness[np.ix_(dofs, dofs)] += local_stiffness
        loads[dofs] += local_load
        element_data.append((dofs, local_stiffness, local_load))

    restrained = {2 * node for node in support_nodes}
    restrained.update(2 * node + 1 for node in rotational_support_nodes)
    if not restrained:
        raise ValueError("At least one beam degree of freedom must be restrained.")
    free = [dof for dof in range(dof_count) if dof not in restrained]

    displacement = np.zeros(dof_count, dtype=float)
    if free:
        reduced_stiffness = stiffness[np.ix_(free, free)]
        reduced_load = loads[free]
        try:
            displacement[free] = np.linalg.solve(reduced_stiffness, reduced_load)
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                "Beam stiffness matrix is singular; check supports and connectivity."
            ) from exc

    reactions = stiffness @ displacement - loads

    members: list[BeamMemberResult] = []
    for span_index, (dofs, local_stiffness, local_load) in enumerate(element_data):
        raw = local_stiffness @ displacement[dofs] - local_load
        members.append(
            BeamMemberResult(
                span_index=span_index,
                left_shear_kn=float(raw[0]),
                left_moment_knm=float(-raw[1]),
                right_shear_kn=float(-raw[2]),
                right_moment_knm=float(raw[3]),
                raw_element_end_forces=tuple(float(value) for value in raw),
            )
        )

    nodes = tuple(
        BeamNodeResult(
            node_index=node,
            vertical_displacement_m=float(displacement[2 * node]),
            rotation_rad=float(displacement[2 * node + 1]),
            vertical_reaction_kn=float(reactions[2 * node]),
            moment_reaction_knm=float(reactions[2 * node + 1]),
        )
        for node in range(node_count)
    )

    return ContinuousBeamResult(
        nodes=nodes,
        members=tuple(members),
        displacements=tuple(float(value) for value in displacement),
        load_vector=tuple(float(value) for value in loads),
        reaction_vector=tuple(float(value) for value in reactions),
        status=(
            "Code-neutral Euler-Bernoulli continuous-beam stiffness solution; "
            "bridge load generation and transverse distribution remain separate"
        ),
    )


def member_section_response(
    span: BeamSpan,
    member: BeamMemberResult,
    x_m: float,
) -> BeamSectionResponse:
    """Recover physical shear and sagging-positive moment within one solved span."""
    if member.span_index < 0:
        raise ValueError("member span index cannot be negative.")
    if not 0.0 <= x_m <= span.length_m:
        raise ValueError("Section location must lie within the span.")

    shear = member.left_shear_kn - span.udl_kn_m * x_m
    moment = (
        member.left_moment_knm
        + member.left_shear_kn * x_m
        - span.udl_kn_m * x_m**2 / 2.0
    )
    for load in span.point_loads:
        if load.position_m <= x_m:
            shear -= load.magnitude_kn
            moment -= load.magnitude_kn * (x_m - load.position_m)

    return BeamSectionResponse(
        x_m=x_m,
        shear_kn=shear,
        moment_knm=moment,
    )


def member_span_envelope(
    span: BeamSpan,
    member: BeamMemberResult,
    *,
    stations: int = 401,
) -> BeamSpanEnvelope:
    """Scan one solved span for sagging/hogging moment and absolute shear extrema."""
    if stations < 2:
        raise ValueError("At least two envelope stations are required.")

    locations = {span.length_m * index / (stations - 1) for index in range(stations)}
    locations.update(load.position_m for load in span.point_loads)
    responses = [member_section_response(span, member, x_m) for x_m in sorted(locations)]

    sagging = max(responses, key=lambda item: item.moment_knm)
    hogging = min(responses, key=lambda item: item.moment_knm)
    shear = max(responses, key=lambda item: abs(item.shear_kn))
    return BeamSpanEnvelope(
        span_index=member.span_index,
        max_sagging_moment_knm=sagging.moment_knm,
        max_sagging_position_m=sagging.x_m,
        min_hogging_moment_knm=hogging.moment_knm,
        min_hogging_position_m=hogging.x_m,
        max_abs_shear_kn=abs(shear.shear_kn),
        max_abs_shear_position_m=shear.x_m,
    )
