from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from rc_bridge.codes.eurocode.materials import secant_elastic_modulus_mpa
from rc_bridge.core.models import DesignCode, ProjectInput
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNodalLoad,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)


@dataclass(frozen=True)
class GrillageSectionProperties:
    """Explicit frame-section properties used by an external grillage verification model."""

    name: str
    area_m2: float
    torsion_constant_m4: float
    iy_m4: float
    iz_m4: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Grillage section name cannot be empty.")
        if min(self.area_m2, self.torsion_constant_m4, self.iy_m4, self.iz_m4) <= 0.0:
            raise ValueError("Grillage section area and inertias must be positive.")


@dataclass(frozen=True)
class GrillagePointLoad:
    """One downward point load positioned in the bridge plan."""

    x_m: float
    y_m: float
    magnitude_kn: float
    label: str = "point load"

    def __post_init__(self) -> None:
        if self.magnitude_kn < 0.0:
            raise ValueError("Grillage point-load magnitude cannot be negative.")
        if not self.label.strip():
            raise ValueError("Grillage point-load label cannot be empty.")


@dataclass(frozen=True)
class GrillageVerificationLoadCase:
    name: str
    point_loads: tuple[GrillagePointLoad, ...] = ()
    longitudinal_udl_kn_m_by_girder: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Grillage verification load-case name cannot be empty.")
        if self.longitudinal_udl_kn_m_by_girder is not None and any(
            value < 0.0 for value in self.longitudinal_udl_kn_m_by_girder
        ):
            raise ValueError("Grillage longitudinal UDL values cannot be negative.")


def _elastic_modulus_mpa(project: ProjectInput) -> float:
    if project.materials.elastic_modulus_mpa is not None:
        return float(project.materials.elastic_modulus_mpa)
    if project.design_code == DesignCode.EUROCODE:
        return secant_elastic_modulus_mpa(float(project.materials.fck_mpa))
    raise ValueError(
        "Grillage verification export requires explicit elastic_modulus_mpa for this code profile."
    )


def _support_stations(project: ProjectInput) -> tuple[float, ...]:
    stations = [0.0]
    x = 0.0
    for length in project.geometry.span_lengths_m:
        x += float(length)
        stations.append(x)
    return tuple(stations)


def _station_grid(
    project: ProjectInput,
    transverse_stations_m: tuple[float, ...],
) -> tuple[float, ...]:
    support_stations = _support_stations(project)
    total_length = support_stations[-1]
    supplied = tuple(float(value) for value in transverse_stations_m)
    if any(value < -1e-9 or value > total_length + 1e-9 for value in supplied):
        raise ValueError("A grillage transverse station lies outside the bridge length.")
    return tuple(sorted(set((*support_stations, *supplied))))


def _girder_y_coordinates(project: ProjectInput) -> tuple[float, ...]:
    count = int(project.geometry.girder_count)
    spacing = float(project.geometry.girder_spacing_m)
    width = float(project.geometry.deck_width_m)
    edge = float(project.geometry.nominal_edge_overhang_m)
    first = -width / 2.0 + edge
    return tuple(first + index * spacing for index in range(count))


def _span_index_at_x(project: ProjectInput, x_m: float) -> int:
    boundaries = _support_stations(project)
    if x_m < boundaries[0] - 1e-9 or x_m > boundaries[-1] + 1e-9:
        raise ValueError("Grillage member midpoint lies outside the bridge length.")
    if abs(x_m - boundaries[-1]) <= 1e-9:
        return len(boundaries) - 2
    return min(max(bisect_right(boundaries, x_m) - 1, 0), len(boundaries) - 2)


def _bracket(values: tuple[float, ...], value: float) -> tuple[int, int, float]:
    if value < values[0] - 1e-9 or value > values[-1] + 1e-9:
        raise ValueError("Point load lies outside the grillage node envelope.")
    for index, coordinate in enumerate(values):
        if abs(value - coordinate) <= 1e-9:
            return index, index, 0.0
    upper = bisect_right(values, value)
    lower = upper - 1
    ratio = (value - values[lower]) / (values[upper] - values[lower])
    return lower, upper, ratio


def _point_load_node_weights(
    x_stations_m: tuple[float, ...],
    y_girders_m: tuple[float, ...],
    load: GrillagePointLoad,
    girder_count: int,
) -> dict[int, float]:
    xi, xj, tx = _bracket(x_stations_m, load.x_m)
    yi, yj, ty = _bracket(y_girders_m, load.y_m)

    x_weights = ((xi, 1.0),) if xi == xj else ((xi, 1.0 - tx), (xj, tx))
    y_weights = ((yi, 1.0),) if yi == yj else ((yi, 1.0 - ty), (yj, ty))
    weights: dict[int, float] = {}
    for x_index, wx in x_weights:
        for y_index, wy in y_weights:
            node_id = x_index * girder_count + y_index + 1
            weights[node_id] = weights.get(node_id, 0.0) + wx * wy
    return weights


def build_project_grillage_verification_model(
    project: ProjectInput,
    *,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...],
    transverse_section: GrillageSectionProperties,
    transverse_stations_m: tuple[float, ...],
    load_case: GrillageVerificationLoadCase,
) -> VerificationModel:
    """Build a full bridge beam-grillage model for independent software verification.

    Longitudinal and transverse section properties are explicit inputs. Point loads
    are mapped to adjacent grillage nodes by bilinear geometric interpolation; this
    preserves force and plan position but is not itself a production transverse-
    distribution method. Longitudinal UDLs, when supplied, are explicit per girder.
    """
    span_count = len(project.geometry.span_lengths_m)
    girder_count = int(project.geometry.girder_count)
    if len(longitudinal_sections_by_span) != span_count:
        raise ValueError("One longitudinal grillage section is required per physical span.")
    if load_case.longitudinal_udl_kn_m_by_girder is not None and len(
        load_case.longitudinal_udl_kn_m_by_girder
    ) != girder_count:
        raise ValueError("Longitudinal grillage UDL vector must match the girder count.")

    x_stations = _station_grid(project, transverse_stations_m)
    y_girders = _girder_y_coordinates(project)
    e_kn_m2 = _elastic_modulus_mpa(project) * 1000.0
    material = VerificationMaterial(
        material_id=1,
        name="VerificationConcrete",
        elastic_modulus_kn_m2=e_kn_m2,
        poisson_ratio=0.2,
        weight_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )

    longitudinal_sections = tuple(
        VerificationSection(
            section_id=index + 1,
            name=section.name,
            area_m2=section.area_m2,
            torsion_constant_m4=section.torsion_constant_m4,
            iy_m4=section.iy_m4,
            iz_m4=section.iz_m4,
        )
        for index, section in enumerate(longitudinal_sections_by_span)
    )
    transverse_section_id = span_count + 1
    transverse_verification_section = VerificationSection(
        section_id=transverse_section_id,
        name=transverse_section.name,
        area_m2=transverse_section.area_m2,
        torsion_constant_m4=transverse_section.torsion_constant_m4,
        iy_m4=transverse_section.iy_m4,
        iz_m4=transverse_section.iz_m4,
    )

    nodes = tuple(
        VerificationNode(
            node_id=x_index * girder_count + girder_index + 1,
            x_m=x,
            y_m=y,
            z_m=0.0,
        )
        for x_index, x in enumerate(x_stations)
        for girder_index, y in enumerate(y_girders)
    )

    beams: list[VerificationBeam] = []
    longitudinal_member_ids: list[list[int]] = [[] for _ in range(girder_count)]
    member_id = 1
    for x_index in range(len(x_stations) - 1):
        midpoint = (x_stations[x_index] + x_stations[x_index + 1]) / 2.0
        span_index = _span_index_at_x(project, midpoint)
        for girder_index in range(girder_count):
            node_i = x_index * girder_count + girder_index + 1
            node_j = (x_index + 1) * girder_count + girder_index + 1
            beams.append(
                VerificationBeam(
                    member_id=member_id,
                    node_i=node_i,
                    node_j=node_j,
                    material_id=1,
                    section_id=span_index + 1,
                )
            )
            longitudinal_member_ids[girder_index].append(member_id)
            member_id += 1

    for x_index in range(len(x_stations)):
        for girder_index in range(girder_count - 1):
            node_i = x_index * girder_count + girder_index + 1
            node_j = node_i + 1
            beams.append(
                VerificationBeam(
                    member_id=member_id,
                    node_i=node_i,
                    node_j=node_j,
                    material_id=1,
                    section_id=transverse_section_id,
                )
            )
            member_id += 1

    support_station_set = set(_support_stations(project))
    support_station_indices = [
        index for index, x in enumerate(x_stations) if x in support_station_set
    ]
    supports: list[VerificationSupport] = []
    for x_index in support_station_indices:
        for girder_index in range(girder_count):
            node_id = x_index * girder_count + girder_index + 1
            ux = x_index == support_station_indices[0] and girder_index in {0, girder_count - 1}
            uy = x_index == support_station_indices[0] and girder_index == 0
            supports.append(VerificationSupport(node_id=node_id, ux=ux, uy=uy, uz=True))

    uniform_loads: list[VerificationUniformLoad] = []
    if load_case.longitudinal_udl_kn_m_by_girder is not None:
        for girder_index, magnitude in enumerate(load_case.longitudinal_udl_kn_m_by_girder):
            if magnitude == 0.0:
                continue
            uniform_loads.extend(
                VerificationUniformLoad(
                    member_id=current_member_id,
                    direction="GZ",
                    magnitude_kn_m=-float(magnitude),
                )
                for current_member_id in longitudinal_member_ids[girder_index]
            )

    nodal_forces: dict[int, float] = {}
    for point in load_case.point_loads:
        weights = _point_load_node_weights(x_stations, y_girders, point, girder_count)
        for node_id, weight in weights.items():
            nodal_forces[node_id] = nodal_forces.get(node_id, 0.0) - point.magnitude_kn * weight
    nodal_loads = tuple(
        VerificationNodalLoad(node_id=node_id, fz_kn=fz)
        for node_id, fz in sorted(nodal_forces.items())
        if abs(fz) > 1e-12
    )

    verification_case = VerificationLoadCase(
        load_case_id=1,
        name=load_case.name,
        uniform_loads=tuple(uniform_loads),
        nodal_loads=nodal_loads,
    )
    return VerificationModel(
        name=f"{project.name} - full grillage - {load_case.name}",
        nodes=nodes,
        materials=(material,),
        sections=(*longitudinal_sections, transverse_verification_section),
        beams=tuple(beams),
        supports=tuple(supports),
        load_cases=(verification_case,),
        metadata={
            "source": "RC-Bridge-Analysis-ANN",
            "purpose": "full_bridge_grillage_verification",
            "design_code": project.design_code.value,
            "girder_count": str(girder_count),
            "station_count": str(len(x_stations)),
            "transverse_stiffness_basis": "explicit caller-supplied A, J, Iy and Iz",
            "longitudinal_stiffness_basis": "explicit caller-supplied A, J, Iy and Iz per span",
            "point_load_mapping": "bilinear geometric interpolation to adjacent grillage nodes",
            "point_load_mapping_scope": (
                "equilibrium-preserving export mapping only; not a production transverse-distribution model"
            ),
            "longitudinal_udl_basis": "explicit caller-supplied line load per girder",
            "self_weight_basis": "not activated unless included in supplied longitudinal line loads",
        },
    )
