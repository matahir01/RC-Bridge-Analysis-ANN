from __future__ import annotations

from dataclasses import dataclass
from math import pi

import numpy as np

from rc_bridge.application.extended_actions import ExtendedActionSettings, ExtendedActionSuite
from rc_bridge.codes.eurocode.materials import concrete_properties_ec2, secant_elastic_modulus_mpa
from rc_bridge.core.models import PermanentLineActionCategory, ProjectInput
from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.design.eurocode_detailing import minimum_tension_reinforcement_mm2
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance


@dataclass(frozen=True)
class LocalDeckSettings:
    """Settings for the native transverse deck-slab strip solver.

    The bridge deck is represented as a continuous one-metre longitudinal strip
    spanning transversely over the longitudinal girder lines, including the
    physical edge cantilevers. Wheel contact areas are dispersed to the slab
    mid-depth with an explicit horizontal/vertical spread ratio. This is the
    appropriate first local model for a longitudinal-girder deck; it is not
    relabelled as a general two-way plate FE model.
    """

    load_dispersion_horizontal_per_vertical: float = 1.0
    additional_dispersion_depth_m: float = 0.0
    nominal_bar_diameter_mm: float = 16.0
    available_bar_diameters_mm: tuple[float, ...] = (12.0, 16.0, 20.0, 25.0)
    available_spacings_mm: tuple[float, ...] = (
        300.0,
        250.0,
        225.0,
        200.0,
        175.0,
        150.0,
        125.0,
        100.0,
    )

    def __post_init__(self) -> None:
        if self.load_dispersion_horizontal_per_vertical <= 0.0:
            raise ValueError("Local-deck load-dispersion ratio must be positive.")
        if self.additional_dispersion_depth_m < 0.0:
            raise ValueError("Additional local-deck dispersion depth cannot be negative.")
        if self.nominal_bar_diameter_mm <= 0.0:
            raise ValueError("Local-deck nominal bar diameter must be positive.")
        if not self.available_bar_diameters_mm or any(
            value <= 0.0 for value in self.available_bar_diameters_mm
        ):
            raise ValueError("Local-deck available bar diameters must be positive.")
        if not self.available_spacings_mm or any(
            value <= 0.0 for value in self.available_spacings_mm
        ):
            raise ValueError("Local-deck available bar spacings must be positive.")


@dataclass(frozen=True)
class SlabBarArrangement:
    bar_diameter_mm: float
    spacing_mm: float
    provided_area_mm2_per_m: float

    @property
    def label(self) -> str:
        return f"Y{self.bar_diameter_mm:g}@{self.spacing_mm:g}"


@dataclass(frozen=True)
class LocalDeckResponse:
    stations_y_m: tuple[float, ...]
    moments_knm_per_m: tuple[float, ...]
    maximum_positive_knm_per_m: float
    maximum_negative_knm_per_m: float
    maximum_abs_knm_per_m: float


@dataclass(frozen=True)
class LocalDeckReinforcementResult:
    face: str
    design_moment_knm_per_m: float
    required_area_mm2_per_m: float
    minimum_area_mm2_per_m: float
    governing_area_mm2_per_m: float
    arrangement: SlabBarArrangement
    resistance_knm_per_m: float
    utilization: float
    status: str

    @property
    def passes(self) -> bool:
        return self.utilization <= 1.0 + 1.0e-9


@dataclass(frozen=True)
class LocalDeckDesignResult:
    permanent: LocalDeckResponse
    lm2_governing: LocalDeckResponse | None
    lm2_case_count: int
    lm2_governing_axle_centre_y_m: float | None
    barrier_left: LocalDeckResponse | None
    barrier_right: LocalDeckResponse | None
    uls_positive_moment_knm_per_m: float
    uls_negative_moment_knm_per_m: float
    accidental_positive_moment_knm_per_m: float
    accidental_negative_moment_knm_per_m: float
    bottom_transverse: LocalDeckReinforcementResult
    top_transverse: LocalDeckReinforcementResult
    status: str

    @property
    def passes(self) -> bool:
        return self.bottom_transverse.passes and self.top_transverse.passes


@dataclass(frozen=True)
class _Element:
    left_index: int
    right_index: int
    length_m: float
    udl_kn_m: float


@dataclass(frozen=True)
class _BeamSolution:
    coordinates_m: tuple[float, ...]
    displacements: np.ndarray
    elements: tuple[_Element, ...]
    element_end_forces: tuple[np.ndarray, ...]


def _merge(values: list[float], tolerance: float = 1.0e-9) -> tuple[float, ...]:
    merged: list[float] = []
    for value in sorted(values):
        if not merged or abs(value - merged[-1]) > tolerance:
            merged.append(float(value))
    return tuple(merged)


def _girder_y(project: ProjectInput) -> tuple[float, ...]:
    width = float(project.geometry.deck_width_m)
    edge = float(project.geometry.nominal_edge_overhang_m)
    spacing = float(project.geometry.girder_spacing_m)
    count = int(project.geometry.girder_count)
    first = -width / 2.0 + edge
    return tuple(first + index * spacing for index in range(count))


def _surfacing_pressure_at(project: ProjectInput, y_m: float) -> float:
    pressure = 0.0
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    for layer in project.permanent_actions.surfacing_layers:
        x_end = total_length if layer.x_end_m is None else float(layer.x_end_m)
        coverage = max(x_end - float(layer.x_start_m), 0.0) / total_length
        if float(layer.y_start_m) - 1.0e-9 <= y_m <= float(layer.y_end_m) + 1.0e-9:
            pressure += layer.pressure_kn_m2 * coverage
    return pressure


def _line_actions(project: ProjectInput) -> tuple[tuple[float, float, str], ...]:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    values: list[tuple[float, float, str]] = []
    for action in project.permanent_actions.line_actions:
        x_end = total_length if action.x_end_m is None else float(action.x_end_m)
        coverage = max(x_end - float(action.x_start_m), 0.0) / total_length
        values.append(
            (
                float(action.y_m),
                float(action.magnitude_kn_m) * coverage,
                action.category.value,
            )
        )
    return tuple(values)


def _effective_patch_dimensions(
    project: ProjectInput,
    settings: LocalDeckSettings,
    actions: ExtendedActionSettings,
) -> tuple[float, float]:
    surfacing_depth = max(
        (float(layer.thickness_m) for layer in project.permanent_actions.surfacing_layers),
        default=0.0,
    )
    dispersion_depth = (
        surfacing_depth
        + 0.5 * float(project.geometry.physical_deck_depth_m)
        + settings.additional_dispersion_depth_m
    )
    spread = (
        2.0
        * dispersion_depth
        * settings.load_dispersion_horizontal_per_vertical
    )
    return (
        float(actions.lm2_contact_length_m) + spread,
        float(actions.lm2_contact_width_m) + spread,
    )


def _beam_stiffness(ei_kn_m2: float, length_m: float) -> np.ndarray:
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


def _uniform_load_vector(q_kn_m: float, length_m: float) -> np.ndarray:
    return np.array(
        [
            q_kn_m * length_m / 2.0,
            q_kn_m * length_m**2 / 12.0,
            q_kn_m * length_m / 2.0,
            -q_kn_m * length_m**2 / 12.0,
        ],
        dtype=float,
    )


def _solve_continuous_strip(
    *,
    coordinates_m: tuple[float, ...],
    supports_m: tuple[float, ...],
    elastic_modulus_kn_m2: float,
    inertia_m4: float,
    element_udl_kn_m: tuple[float, ...],
    nodal_loads_kn: dict[float, float] | None = None,
) -> _BeamSolution:
    count = len(coordinates_m)
    if count < 2:
        raise ValueError("Local deck strip requires at least two transverse coordinates.")
    if len(element_udl_kn_m) != count - 1:
        raise ValueError("Local deck strip UDL vector must match the element count.")
    ndof = 2 * count
    stiffness = np.zeros((ndof, ndof), dtype=float)
    load = np.zeros(ndof, dtype=float)
    elements: list[_Element] = []
    element_stiffness: list[np.ndarray] = []
    element_loads: list[np.ndarray] = []

    for index in range(count - 1):
        length = coordinates_m[index + 1] - coordinates_m[index]
        if length <= 0.0:
            raise ValueError("Local deck strip coordinates must be strictly increasing.")
        q = element_udl_kn_m[index]
        k = _beam_stiffness(elastic_modulus_kn_m2 * inertia_m4, length)
        f = _uniform_load_vector(q, length)
        dofs = (2 * index, 2 * index + 1, 2 * index + 2, 2 * index + 3)
        for row_local, row_global in enumerate(dofs):
            load[row_global] += f[row_local]
            for col_local, col_global in enumerate(dofs):
                stiffness[row_global, col_global] += k[row_local, col_local]
        elements.append(_Element(index, index + 1, length, q))
        element_stiffness.append(k)
        element_loads.append(f)

    if nodal_loads_kn:
        for coordinate, magnitude in nodal_loads_kn.items():
            node = min(
                range(count),
                key=lambda idx: abs(coordinates_m[idx] - coordinate),
            )
            if abs(coordinates_m[node] - coordinate) > 1.0e-8:
                raise ValueError("A local deck line load was not inserted into the mesh.")
            load[2 * node] += magnitude

    restrained: set[int] = set()
    for support in supports_m:
        node = min(
            range(count),
            key=lambda idx: abs(coordinates_m[idx] - support),
        )
        if abs(coordinates_m[node] - support) > 1.0e-8:
            raise ValueError("A girder support line was not inserted into the local deck mesh.")
        restrained.add(2 * node)

    free = tuple(index for index in range(ndof) if index not in restrained)
    if not free:
        raise ValueError("Local deck strip has no free degrees of freedom.")
    displacement = np.zeros(ndof, dtype=float)
    kff = stiffness[np.ix_(free, free)]
    ff = load[list(free)]
    try:
        displacement[list(free)] = np.linalg.solve(kff, ff)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Local deck strip stiffness matrix is singular.") from exc

    end_forces: list[np.ndarray] = []
    for index, element in enumerate(elements):
        dofs = (
            2 * element.left_index,
            2 * element.left_index + 1,
            2 * element.right_index,
            2 * element.right_index + 1,
        )
        end_forces.append(
            element_stiffness[index] @ displacement[list(dofs)]
            - element_loads[index]
        )

    return _BeamSolution(
        coordinates_m=coordinates_m,
        displacements=displacement,
        elements=tuple(elements),
        element_end_forces=tuple(end_forces),
    )


def _response(solution: _BeamSolution) -> LocalDeckResponse:
    positions: list[float] = []
    moments: list[float] = []
    for element, end in zip(
        solution.elements,
        solution.element_end_forces,
        strict=True,
    ):
        y0 = solution.coordinates_m[element.left_index]
        length = element.length_m
        m_left = float(end[1])
        v_left = -float(end[0])
        # Include quarter points so wheel-patch boundaries/support peaks and
        # span positive bending are represented without relying on nodal moments.
        for ratio in (0.0, 0.25, 0.5, 0.75):
            x = ratio * length
            positions.append(y0 + x)
            moments.append(
                m_left
                + v_left * x
                - 0.5 * element.udl_kn_m * x**2
            )
    last = solution.elements[-1]
    positions.append(solution.coordinates_m[-1])
    moments.append(-float(solution.element_end_forces[-1][3]))
    maximum_positive = max(max(moments), 0.0)
    maximum_negative = min(min(moments), 0.0)
    return LocalDeckResponse(
        stations_y_m=tuple(positions),
        moments_knm_per_m=tuple(moments),
        maximum_positive_knm_per_m=maximum_positive,
        maximum_negative_knm_per_m=maximum_negative,
        maximum_abs_knm_per_m=max(abs(value) for value in moments),
    )


def _select_slab_bars(
    required_area_mm2_per_m: float,
    settings: LocalDeckSettings,
) -> SlabBarArrangement:
    candidates: list[SlabBarArrangement] = []
    for diameter in settings.available_bar_diameters_mm:
        area = pi * diameter**2 / 4.0
        for spacing in settings.available_spacings_mm:
            provided = area * 1000.0 / spacing
            if provided + 1.0e-9 < required_area_mm2_per_m:
                continue
            candidates.append(
                SlabBarArrangement(
                    bar_diameter_mm=diameter,
                    spacing_mm=spacing,
                    provided_area_mm2_per_m=provided,
                )
            )
    if not candidates:
        raise ValueError(
            "No configured slab reinforcement arrangement satisfies the local deck demand."
        )
    return min(
        candidates,
        key=lambda item: (
            item.provided_area_mm2_per_m,
            item.bar_diameter_mm,
            -item.spacing_mm,
        ),
    )


def _reinforcement_design(
    project: ProjectInput,
    *,
    face: str,
    design_moment_knm_per_m: float,
    settings: LocalDeckSettings,
    cover_mm: float,
) -> LocalDeckReinforcementResult:
    depth = float(project.geometry.physical_deck_depth_m)
    diameter = settings.nominal_bar_diameter_mm
    effective_depth = depth - (cover_mm + diameter / 2.0) / 1000.0
    if effective_depth <= 0.0:
        raise ValueError("Local deck cover/bar assumptions leave no effective depth.")
    required = required_tension_steel_rectangular(
        med_knm=max(design_moment_knm_per_m, 0.0),
        width_m=1.0,
        effective_depth_m=effective_depth,
        fck_mpa=float(project.materials.fck_mpa),
        fyk_mpa=float(project.materials.fyk_mpa),
    )
    concrete = concrete_properties_ec2(float(project.materials.fck_mpa))
    minimum, _ = minimum_tension_reinforcement_mm2(
        fctm_mpa=concrete.fctm_mpa,
        fyk_mpa=float(project.materials.fyk_mpa),
        tension_zone_width_m=1.0,
        effective_depth_m=effective_depth,
    )
    governing = max(required, minimum)
    arrangement = _select_slab_bars(governing, settings)
    resistance = rectangular_singly_reinforced_resistance(
        width_m=1.0,
        effective_depth_m=effective_depth,
        steel_area_mm2=arrangement.provided_area_mm2_per_m,
        fck_mpa=float(project.materials.fck_mpa),
        fyk_mpa=float(project.materials.fyk_mpa),
    )
    utilization = (
        design_moment_knm_per_m / resistance.resistance_knm
        if resistance.resistance_knm > 0.0
        else float("inf")
    )
    return LocalDeckReinforcementResult(
        face=face,
        design_moment_knm_per_m=design_moment_knm_per_m,
        required_area_mm2_per_m=required,
        minimum_area_mm2_per_m=minimum,
        governing_area_mm2_per_m=governing,
        arrangement=arrangement,
        resistance_knm_per_m=resistance.resistance_knm,
        utilization=utilization,
        status=(
            "EC2 one-metre transverse slab-strip flexure using the native continuous "
            "girder-line support model; longitudinal/distribution steel remains subject "
            "to minimum reinforcement and drawing-level detailing."
        ),
    )


def _master_coordinates(
    project: ProjectInput,
    *,
    patch_centres: tuple[float, ...],
    patch_width_m: float,
) -> tuple[float, ...]:
    half = float(project.geometry.deck_width_m) / 2.0
    values = [-half, half, *_girder_y(project)]
    for centre in patch_centres:
        values.extend(
            [
                max(-half, centre - patch_width_m / 2.0),
                min(half, centre + patch_width_m / 2.0),
            ]
        )
    for layer in project.permanent_actions.surfacing_layers:
        values.extend([float(layer.y_start_m), float(layer.y_end_m)])
    values.extend(y for y, _, _ in _line_actions(project))
    return _merge(values)


def _permanent_udl_by_element(
    project: ProjectInput,
    coordinates: tuple[float, ...],
) -> tuple[float, ...]:
    concrete_pressure = (
        float(project.geometry.physical_deck_depth_m)
        * float(project.materials.concrete_density_kn_m3)
    )
    return tuple(
        concrete_pressure
        + _surfacing_pressure_at(
            project,
            0.5 * (coordinates[index] + coordinates[index + 1]),
        )
        for index in range(len(coordinates) - 1)
    )


def _permanent_nodal_loads(project: ProjectInput) -> dict[float, float]:
    values: dict[float, float] = {}
    for y_m, magnitude, category in _line_actions(project):
        if category in {
            PermanentLineActionCategory.BARRIER.value,
            PermanentLineActionCategory.SERVICES.value,
            PermanentLineActionCategory.OTHER.value,
        }:
            values[y_m] = values.get(y_m, 0.0) + magnitude
    return values


def _patch_udl(
    coordinates: tuple[float, ...],
    patches: tuple[tuple[float, float, float], ...],
) -> tuple[float, ...]:
    values: list[float] = []
    for index in range(len(coordinates) - 1):
        midpoint = 0.5 * (coordinates[index] + coordinates[index + 1])
        q = 0.0
        for y_start, y_end, pressure in patches:
            if y_start - 1.0e-9 <= midpoint <= y_end + 1.0e-9:
                q += pressure
        values.append(q)
    return tuple(values)


def _combine_responses(
    permanent: LocalDeckResponse,
    variable: LocalDeckResponse,
    *,
    gamma_g: float,
    gamma_q: float,
) -> tuple[float, float]:
    if permanent.stations_y_m != variable.stations_y_m:
        raise ValueError("Local deck responses must share an identical master mesh.")
    combined = tuple(
        gamma_g * g + gamma_q * q
        for g, q in zip(
            permanent.moments_knm_per_m,
            variable.moments_knm_per_m,
            strict=True,
        )
    )
    return max(max(combined), 0.0), abs(min(min(combined), 0.0))


def run_local_deck_design(
    project: ProjectInput,
    actions_result: ExtendedActionSuite,
    *,
    action_settings: ExtendedActionSettings,
    settings: LocalDeckSettings,
    cover_mm: float,
    gamma_g: float,
    gamma_q_traffic: float,
) -> LocalDeckDesignResult:
    """Analyse/design the transverse deck slab under permanent, LM2 and barrier actions."""

    if actions_result.lm2 is None:
        raise ValueError("Local deck design requires the LM2 action to be enabled.")
    if project.geometry.girder_count < 2:
        raise ValueError("Local deck strip requires at least two longitudinal girders.")

    patch_x, patch_y = _effective_patch_dimensions(
        project,
        settings,
        action_settings,
    )
    half_deck = float(project.geometry.deck_width_m) / 2.0
    half_track = 0.5 * action_settings.lm2_wheel_track_m
    carriageway_left = float(project.geometry.carriageway_left_edge_m)
    carriageway_right = float(project.geometry.carriageway_right_edge_m)
    centres: list[float] = []
    first = carriageway_left + half_track
    last = carriageway_right - half_track
    if first > last + 1.0e-9:
        raise ValueError("Carriageway is too narrow for the configured LM2 wheel track.")
    current = first
    while current <= last + 1.0e-9:
        centres.append(min(current, last))
        current += action_settings.lm2_transverse_step_m
    centres.extend([first, last, 0.5 * (first + last)])

    # The barrier vertical wheel is placed immediately inside each physical edge.
    barrier_centres = (
        -half_deck + patch_y / 2.0,
        half_deck - patch_y / 2.0,
    )
    wheel_centres = tuple(
        sorted(
            {
                *(value - half_track for value in centres),
                *(value + half_track for value in centres),
                *barrier_centres,
            }
        )
    )
    coordinates = _master_coordinates(
        project,
        patch_centres=wheel_centres,
        patch_width_m=patch_y,
    )
    supports = _girder_y(project)
    e_mpa = (
        float(project.materials.elastic_modulus_mpa)
        if project.materials.elastic_modulus_mpa is not None
        else secant_elastic_modulus_mpa(float(project.materials.fck_mpa))
    )
    e_kn_m2 = e_mpa * 1000.0
    slab_depth = float(project.geometry.physical_deck_depth_m)
    inertia_per_m = slab_depth**3 / 12.0

    permanent_solution = _solve_continuous_strip(
        coordinates_m=coordinates,
        supports_m=supports,
        elastic_modulus_kn_m2=e_kn_m2,
        inertia_m4=inertia_per_m,
        element_udl_kn_m=_permanent_udl_by_element(project, coordinates),
        nodal_loads_kn=_permanent_nodal_loads(project),
    )
    permanent = _response(permanent_solution)

    wheel_load = float(actions_result.lm2.wheel_load_kn)
    wheel_pressure = wheel_load / (patch_x * patch_y)
    lm2_best: LocalDeckResponse | None = None
    lm2_best_centre: float | None = None
    best_metric = -1.0
    uls_positive = 0.0
    uls_negative = 0.0
    case_count = 0
    for axle_centre in sorted(set(centres)):
        patches = []
        for wheel_y in (axle_centre - half_track, axle_centre + half_track):
            patches.append(
                (
                    max(-half_deck, wheel_y - patch_y / 2.0),
                    min(half_deck, wheel_y + patch_y / 2.0),
                    wheel_pressure,
                )
            )
        solution = _solve_continuous_strip(
            coordinates_m=coordinates,
            supports_m=supports,
            elastic_modulus_kn_m2=e_kn_m2,
            inertia_m4=inertia_per_m,
            element_udl_kn_m=_patch_udl(coordinates, tuple(patches)),
        )
        response = _response(solution)
        case_count += 1
        metric = response.maximum_abs_knm_per_m
        if metric > best_metric:
            best_metric = metric
            lm2_best = response
            lm2_best_centre = axle_centre
        positive, negative = _combine_responses(
            permanent,
            response,
            gamma_g=gamma_g,
            gamma_q=gamma_q_traffic,
        )
        uls_positive = max(uls_positive, positive)
        uls_negative = max(uls_negative, negative)

    barrier_results: list[LocalDeckResponse] = []
    accidental_positive = 0.0
    accidental_negative = 0.0
    if actions_result.barrier_impact is not None:
        barrier_wheel = actions_result.barrier_impact.accompanying_vertical_wheel_load_kn
        barrier_pressure = barrier_wheel / (patch_x * patch_y)
        for side, centre in zip(("left", "right"), barrier_centres, strict=True):
            y_start = (
                -half_deck
                if side == "left"
                else half_deck - patch_y
            )
            y_end = (
                -half_deck + patch_y
                if side == "left"
                else half_deck
            )
            solution = _solve_continuous_strip(
                coordinates_m=coordinates,
                supports_m=supports,
                elastic_modulus_kn_m2=e_kn_m2,
                inertia_m4=inertia_per_m,
                element_udl_kn_m=_patch_udl(
                    coordinates,
                    ((y_start, y_end, barrier_pressure),),
                ),
            )
            response = _response(solution)
            barrier_results.append(response)
            # Accidental local design: Gk + Ad, with the accidental vertical wheel
            # retained at its characteristic reference value.
            positive, negative = _combine_responses(
                permanent,
                response,
                gamma_g=1.0,
                gamma_q=1.0,
            )
            accidental_positive = max(accidental_positive, positive)
            accidental_negative = max(accidental_negative, negative)

    design_positive = max(uls_positive, accidental_positive)
    design_negative = max(uls_negative, accidental_negative)
    bottom = _reinforcement_design(
        project,
        face="bottom transverse in slab panels",
        design_moment_knm_per_m=design_positive,
        settings=settings,
        cover_mm=cover_mm,
    )
    top = _reinforcement_design(
        project,
        face="top transverse over girders / edge cantilever",
        design_moment_knm_per_m=design_negative,
        settings=settings,
        cover_mm=cover_mm,
    )
    return LocalDeckDesignResult(
        permanent=permanent,
        lm2_governing=lm2_best,
        lm2_case_count=case_count,
        lm2_governing_axle_centre_y_m=lm2_best_centre,
        barrier_left=barrier_results[0] if len(barrier_results) >= 1 else None,
        barrier_right=barrier_results[1] if len(barrier_results) >= 2 else None,
        uls_positive_moment_knm_per_m=uls_positive,
        uls_negative_moment_knm_per_m=uls_negative,
        accidental_positive_moment_knm_per_m=accidental_positive,
        accidental_negative_moment_knm_per_m=accidental_negative,
        bottom_transverse=bottom,
        top_transverse=top,
        status=(
            "Native continuous transverse deck-slab strip over the actual girder lines, "
            "including edge cantilevers, permanent pressure/line actions, dispersed LM2 "
            "wheel patches and the barrier-impact accompanying vertical wheel. This closes "
            "the current longitudinal-girder bridge local deck flexure blocker; a two-way "
            "plate FE model remains an optional higher-fidelity verification, not a hidden "
            "substitute for this documented strip assumption."
        ),
    )
