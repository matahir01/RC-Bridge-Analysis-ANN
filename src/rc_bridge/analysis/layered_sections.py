from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConcreteLayer:
    """Horizontal concrete layer stacked from the bottom reference face upward."""

    width_m: float
    thickness_m: float
    label: str = "concrete layer"
    active: bool = True

    def __post_init__(self) -> None:
        if self.width_m <= 0.0 or self.thickness_m <= 0.0:
            raise ValueError("Layer width and thickness must be positive.")
        if not self.label:
            raise ValueError("Layer label cannot be empty.")


@dataclass(frozen=True)
class LayeredCrackedSectionResult:
    neutral_axis_from_bottom_mm: float
    second_moment_mm4: float
    steel_stress_mpa: float
    total_depth_mm: float
    active_compression_layers: tuple[str, ...]
    status: str


def layered_total_depth_m(layers: tuple[ConcreteLayer, ...]) -> float:
    if not layers:
        raise ValueError("At least one concrete layer is required.")
    return sum(layer.thickness_m for layer in layers)


def _layer_bounds_mm(
    layers: tuple[ConcreteLayer, ...],
) -> tuple[tuple[ConcreteLayer, float, float], ...]:
    bounds: list[tuple[ConcreteLayer, float, float]] = []
    y0 = 0.0
    for layer in layers:
        y1 = y0 + layer.thickness_m * 1000.0
        bounds.append((layer, y0, y1))
        y0 = y1
    return tuple(bounds)


def _first_moment_segment_about_na(
    width_mm: float,
    y0_mm: float,
    y1_mm: float,
    neutral_axis_mm: float,
) -> float:
    if y1_mm <= y0_mm:
        return 0.0
    return width_mm * (
        neutral_axis_mm * (y1_mm - y0_mm) - (y1_mm**2 - y0_mm**2) / 2.0
    )


def _inertia_segment_about_na(
    width_mm: float,
    y0_mm: float,
    y1_mm: float,
    neutral_axis_mm: float,
) -> float:
    if y1_mm <= y0_mm:
        return 0.0
    return (
        width_mm
        * ((neutral_axis_mm - y0_mm) ** 3 - (neutral_axis_mm - y1_mm) ** 3)
        / 3.0
    )


def cracked_layered_section_sls(
    layers: tuple[ConcreteLayer, ...],
    *,
    steel_area_mm2: float,
    steel_depth_from_bottom_m: float,
    modular_ratio: float,
    service_moment_knm: float,
) -> LayeredCrackedSectionResult:
    """Cracked transformed-section analysis for arbitrary stacked concrete widths.

    The bottom face is the compression reference. Concrete above the neutral axis
    is neglected in tension. ``active=False`` layers retain their physical depth
    but contribute no concrete area or stiffness; this is useful for construction
    layers whose structural participation has not been justified.
    """
    if not layers:
        raise ValueError("At least one concrete layer is required.")
    if steel_area_mm2 <= 0.0 or modular_ratio <= 0.0:
        raise ValueError("Steel area and modular ratio must be positive.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment magnitude cannot be negative.")

    bounds = _layer_bounds_mm(layers)
    total_depth_mm = bounds[-1][2]
    steel_depth_mm = steel_depth_from_bottom_m * 1000.0
    if not 0.0 < steel_depth_mm < total_depth_mm:
        raise ValueError("Reinforcement depth must lie within the layered section.")
    transformed_steel_area = modular_ratio * steel_area_mm2

    def concrete_first_moment(x_mm: float) -> float:
        total = 0.0
        for layer, y0, y1 in bounds:
            if not layer.active or x_mm <= y0:
                continue
            compression_end = min(x_mm, y1)
            total += _first_moment_segment_about_na(
                layer.width_m * 1000.0,
                y0,
                compression_end,
                x_mm,
            )
        return total

    def equilibrium(x_mm: float) -> float:
        return concrete_first_moment(x_mm) - transformed_steel_area * (
            steel_depth_mm - x_mm
        )

    lower = 1e-6
    upper = min(steel_depth_mm - 1e-6, total_depth_mm - 1e-6)
    if equilibrium(lower) >= 0.0 or equilibrium(upper) <= 0.0:
        raise ValueError("Unable to bracket cracked neutral axis for the layered section.")

    for _ in range(120):
        mid = 0.5 * (lower + upper)
        value = equilibrium(mid)
        if abs(value) < 1e-6:
            lower = upper = mid
            break
        if value < 0.0:
            lower = mid
        else:
            upper = mid
    neutral_axis = 0.5 * (lower + upper)

    concrete_inertia = 0.0
    active_compression_layers: list[str] = []
    for layer, y0, y1 in bounds:
        if not layer.active or neutral_axis <= y0:
            continue
        compression_end = min(neutral_axis, y1)
        if compression_end > y0:
            active_compression_layers.append(layer.label)
            concrete_inertia += _inertia_segment_about_na(
                layer.width_m * 1000.0,
                y0,
                compression_end,
                neutral_axis,
            )

    inertia = concrete_inertia + transformed_steel_area * (
        steel_depth_mm - neutral_axis
    ) ** 2
    if inertia <= 0.0:
        raise ValueError("Calculated layered cracked second moment is non-positive.")

    steel_stress = (
        modular_ratio
        * service_moment_knm
        * 1e6
        * (steel_depth_mm - neutral_axis)
        / inertia
    )
    return LayeredCrackedSectionResult(
        neutral_axis_from_bottom_mm=neutral_axis,
        second_moment_mm4=inertia,
        steel_stress_mpa=steel_stress,
        total_depth_mm=total_depth_mm,
        active_compression_layers=tuple(active_compression_layers),
        status=(
            "Code-neutral cracked transformed-section analysis for stacked concrete layers; "
            "tensile concrete and inactive layers are excluded from stiffness"
        ),
    )


def layered_effective_tension_area_from_top_mm2(
    layers: tuple[ConcreteLayer, ...],
    *,
    tension_depth_mm: float,
) -> float:
    """Return active concrete area in a tension zone measured downward from the top."""
    if not layers:
        raise ValueError("At least one concrete layer is required.")
    if tension_depth_mm <= 0.0:
        raise ValueError("Tension-zone depth must be positive.")

    bounds = _layer_bounds_mm(layers)
    total_depth_mm = bounds[-1][2]
    if tension_depth_mm > total_depth_mm:
        raise ValueError("Tension-zone depth cannot exceed the layered-section depth.")
    zone_bottom = total_depth_mm - tension_depth_mm

    area = 0.0
    for layer, y0, y1 in bounds:
        if not layer.active:
            continue
        overlap_start = max(y0, zone_bottom)
        overlap_end = min(y1, total_depth_mm)
        if overlap_end > overlap_start:
            area += layer.width_m * 1000.0 * (overlap_end - overlap_start)
    if area <= 0.0:
        raise ValueError("No active concrete lies within the requested tension zone.")
    return area
