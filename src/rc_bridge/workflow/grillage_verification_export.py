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
    VerificationPointLoad,
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
class GrillageAreaLoad:
    """Uniform downward pressure over one rectangular deck patch."""

    x_start_m: float
    x_end_m: float
    y_start_m: float
    y_end_m: float
    pressure_kn_m2: float
    label: str = "area load"

    def __post_init__(self) -> None:
        if self.x_end_m <= self.x_start_m:
            raise ValueError("Area-load x bounds must define a positive loaded length.")
        if self.y_end_m <= self.y_start_m:
            raise ValueError("Area-load y bounds must define a positive loaded width.")
        if self.pressure_kn_m2 < 0.0:
            raise ValueError("Area-load pressure cannot be negative.")
        if not self.label.strip():
            raise ValueError("Area-load label cannot be empty.")


@dataclass(frozen=True)
class GrillageVerificationLoadCase:
    name: str
    point_loads: tuple[GrillagePointLoad, ...] = ()
    area_loads: tuple[GrillageAreaLoad, ...] = ()
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


def _merge_coordinates(values: tuple[float, ...], *, tolerance: float = 1.0e-9) -> tuple[float, ...]:
    merged: list[float] = []
    for value in sorted(values):
        if not merged or abs(value - merged[-1]) > tolerance:
            merged.append(value)
    return tuple(merged)


def _station_grid(
    project: ProjectInput,
    transverse_stations_m: tuple[float, ...],
    point_loads: tuple[GrillagePointLoad, ...],
    area_loads: tuple[GrillageAreaLoad, ...],
) -> tuple[float, ...]:
    support_stations = _support_stations(project)
    total_length = support_stations[-1]
    supplied = tuple(float(value) for value in transverse_stations_m)
    point_positions = tuple(float(load.x_m) for load in point_loads)
    patch_boundaries = tuple(
        coordinate
        for load in area_loads
        for coordinate in (float(load.x_start_m), float(load.x_end_m))
    )
    all_positions = (*supplied, *point_positions, *patch_boundaries)
    if any(value < -1e-9 or value > total_length + 1e-9 for value in all_positions):
        raise ValueError("A grillage station or load boundary lies outside the bridge length.")
    return _merge_coordinates((*support_stations, *all_positions))


def _girder_y_coordinates(project: ProjectInput) -> tuple[float, ...]:
    count = int(project.geometry.girder_count)
    spacing = float(project.geometry.girder_spacing_m)
    width = float(project.geometry.deck_width_m)
    edge = float(project.geometry.nominal_edge_overhang_m)
    first = -width / 2.0 + edge
    return tuple(first + index * spacing for index in range(count))


def _transverse_y_coordinates(
    project: ProjectInput,
    area_loads: tuple[GrillageAreaLoad, ...],
) -> tuple[float, ...]:
    half_width = float(project.geometry.deck_width_m) / 2.0
    patch_boundaries = tuple(
        coordinate
        for load in area_loads
        for coordinate in (float(load.y_start_m), float(load.y_end_m))
    )
    if any(value < -half_width - 1e-9 or value > half_width + 1e-9 for value in patch_boundaries):
        raise ValueError("An area-load transverse boundary lies outside the physical deck width.")
    return _merge_coordinates((-half_width, *_girder_y_coordinates(project), *patch_boundaries, half_width))


def _span_index_at_x(project: ProjectInput, x_m: float) -> int:
    boundaries = _support_stations(project)
    if x_m < boundaries[0] - 1e-9 or x_m > boundaries[-1] + 1e-9:
        raise ValueError("Grillage member midpoint lies outside the bridge length.")
    if abs(x_m - boundaries[-1]) <= 1e-9:
        return len(boundaries) - 2
    return min(max(bisect_right(boundaries, x_m) - 1, 0), len(boundaries) - 2)


def _coordinate_index(values: tuple[float, ...], value: float) -> int:
    for index, coordinate in enumerate(values):
        if abs(value - coordinate) <= 1e-9:
            return index
    raise ValueError("Required grillage coordinate was not generated.")


def build_project_grillage_verification_model(
    project: ProjectInput,
    *,
    longitudinal_sections_by_span: tuple[GrillageSectionProperties, ...],
    transverse_section: GrillageSectionProperties,
    transverse_stations_m: tuple[float, ...],
    load_case: GrillageVerificationLoadCase,
) -> VerificationModel:
    """Build a full bridge beam-grillage model for independent software verification.

    Longitudinal and transverse section properties are explicit inputs. Every point-load
    x-coordinate and every area-load boundary is inserted as an exact grid line. The
    transverse grid extends to the physical deck edges, so loads on deck overhangs are
    transferred through transverse cantilever strips rather than moved inward.
    """
    span_count = len(project.geometry.span_lengths_m)
    girder_count = int(project.geometry.girder_count)
    if len(longitudinal_sections_by_span) != span_count:
        raise ValueError("One longitudinal grillage section is required per physical span.")
    if load_case.longitudinal_udl_kn_m_by_girder is not None and len(
        load_case.longitudinal_udl_kn_m_by_girder
    ) != girder_count:
        raise ValueError("Longitudinal grillage UDL vector must match the girder count.")

    x_stations = _station_grid(
        project,
        transverse_stations_m,
        load_case.point_loads,
        load_case.area_loads,
    )
    y_girders = _girder_y_coordinates(project)
    y_lines = _transverse_y_coordinates(project, load_case.area_loads)
    y_line_count = len(y_lines)
    girder_y_indices = tuple(_coordinate_index(y_lines, value) for value in y_girders)
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

    def node_id(x_index: int, y_index: int) -> int:
        return x_index * y_line_count + y_index + 1

    nodes = tuple(
        VerificationNode(
            node_id=node_id(x_index, y_index),
            x_m=x,
            y_m=y,
            z_m=0.0,
        )
        for x_index, x in enumerate(x_stations)
        for y_index, y in enumerate(y_lines)
    )

    beams: list[VerificationBeam] = []
    longitudinal_member_ids: list[list[int]] = [[] for _ in range(girder_count)]
    transverse_member_ids: dict[tuple[int, int], int] = {}
    member_id = 1
    for x_index in range(len(x_stations) - 1):
        midpoint = (x_stations[x_index] + x_stations[x_index + 1]) / 2.0
        span_index = _span_index_at_x(project, midpoint)
        for girder_index, y_index in enumerate(girder_y_indices):
            beams.append(
                VerificationBeam(
                    member_id=member_id,
                    node_i=node_id(x_index, y_index),
                    node_j=node_id(x_index + 1, y_index),
                    material_id=1,
                    section_id=span_index + 1,
                )
            )
            longitudinal_member_ids[girder_index].append(member_id)
            member_id += 1

    for x_index in range(len(x_stations)):
        for y_index in range(y_line_count - 1):
            transverse_member_ids[(x_index, y_index)] = member_id
            beams.append(
                VerificationBeam(
                    member_id=member_id,
                    node_i=node_id(x_index, y_index),
                    node_j=node_id(x_index, y_index + 1),
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
        for girder_index, y_index in enumerate(girder_y_indices):
            current_node_id = node_id(x_index, y_index)
            ux = x_index == support_station_indices[0]
            uy = x_index == support_station_indices[0] and girder_index == 0
            supports.append(VerificationSupport(node_id=current_node_id, ux=ux, uy=uy, uz=True))

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

    point_loads: list[VerificationPointLoad] = []
    nodal_force_by_node: dict[int, float] = {}
    half_deck_width = float(project.geometry.deck_width_m) / 2.0
    for point in load_case.point_loads:
        if point.y_m < -half_deck_width - 1e-9 or point.y_m > half_deck_width + 1e-9:
            raise ValueError("Point load lies outside the physical deck width.")
        x_index = _coordinate_index(x_stations, point.x_m)
        exact_y_index = next(
            (index for index, coordinate in enumerate(y_lines) if abs(point.y_m - coordinate) <= 1e-9),
            None,
        )
        if exact_y_index is not None:
            current_node_id = node_id(x_index, exact_y_index)
            nodal_force_by_node[current_node_id] = (
                nodal_force_by_node.get(current_node_id, 0.0) - point.magnitude_kn
            )
            continue
        segment_index = next(
            (
                index
                for index in range(y_line_count - 1)
                if y_lines[index] < point.y_m < y_lines[index + 1]
            ),
            None,
        )
        if segment_index is None:
            raise ValueError("Point load could not be mapped to the transverse grillage.")
        point_loads.append(
            VerificationPointLoad(
                member_id=transverse_member_ids[(x_index, segment_index)],
                direction="GZ",
                magnitude_kn=-point.magnitude_kn,
                distance_from_i_m=point.y_m - y_lines[segment_index],
            )
        )

    total_length = _support_stations(project)[-1]
    for patch in load_case.area_loads:
        if patch.x_start_m < -1e-9 or patch.x_end_m > total_length + 1e-9:
            raise ValueError("Area load lies outside the bridge length.")
        if patch.y_start_m < -half_deck_width - 1e-9 or patch.y_end_m > half_deck_width + 1e-9:
            raise ValueError("Area load lies outside the physical deck width.")
        x_start = _coordinate_index(x_stations, patch.x_start_m)
        x_end = _coordinate_index(x_stations, patch.x_end_m)
        y_start = _coordinate_index(y_lines, patch.y_start_m)
        y_end = _coordinate_index(y_lines, patch.y_end_m)
        for x_index in range(x_start, x_end):
            dx = x_stations[x_index + 1] - x_stations[x_index]
            for y_index in range(y_start, y_end):
                dy = y_lines[y_index + 1] - y_lines[y_index]
                corner_force = patch.pressure_kn_m2 * dx * dy / 4.0
                for current_node_id in (
                    node_id(x_index, y_index),
                    node_id(x_index + 1, y_index),
                    node_id(x_index, y_index + 1),
                    node_id(x_index + 1, y_index + 1),
                ):
                    nodal_force_by_node[current_node_id] = (
                        nodal_force_by_node.get(current_node_id, 0.0) - corner_force
                    )

    nodal_loads = tuple(
        VerificationNodalLoad(node_id=current_node_id, fz_kn=fz_kn)
        for current_node_id, fz_kn in sorted(nodal_force_by_node.items())
        if abs(fz_kn) > 1e-12
    )
    verification_case = VerificationLoadCase(
        load_case_id=1,
        name=load_case.name,
        uniform_loads=tuple(uniform_loads),
        point_loads=tuple(point_loads),
        nodal_loads=nodal_loads,
    )
    model = VerificationModel(
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
            "girder_spacing_m": f"{float(project.geometry.girder_spacing_m):.12g}",
            "deck_width_m": f"{float(project.geometry.deck_width_m):.12g}",
            "edge_overhang_m": f"{project.geometry.nominal_edge_overhang_m:.12g}",
            "station_count": str(len(x_stations)),
            "transverse_stiffness_basis": "explicit caller-supplied A, J, Iy and Iz",
            "longitudinal_stiffness_basis": "explicit caller-supplied A, J, Iy and Iz per span",
            "point_load_mapping": "exact x station; exact nodal or transverse-member y position",
            "area_load_mapping": "exact patch boundaries; uniform cell pressure lumped q*A/4 to each corner",
            "deck_overhang_model": "transverse cantilever strip from exterior girder to physical deck edge",
            "longitudinal_udl_basis": "explicit caller-supplied line load per girder",
            "self_weight_basis": "not activated unless included in supplied longitudinal line loads",
        },
    )
    model.validate_load_positions()
    return model
