from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rc_bridge.design.eurocode_layered_cracking import HorizontalSectionLayer


@dataclass(frozen=True)
class TransformedSteelLayer:
    label: str
    area_mm2: float
    depth_from_compression_face_m: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Steel-layer label cannot be empty.")
        if self.area_mm2 <= 0.0:
            raise ValueError("Steel-layer area must be positive.")
        if self.depth_from_compression_face_m <= 0.0:
            raise ValueError("Steel-layer depth must be positive.")


@dataclass(frozen=True)
class MultiSteelCrackedSectionResult:
    neutral_axis_from_compression_face_mm: float
    second_moment_mm4: float
    compression_face_stress_mpa: float
    steel_stresses_mpa: tuple[tuple[str, float], ...]

    def steel_stress_mpa(self, label: str) -> float:
        match = next(
            (stress for item_label, stress in self.steel_stresses_mpa if item_label == label),
            None,
        )
        if match is None:
            raise KeyError(f"Unknown steel layer {label!r}.")
        return match


def _validated_layers(
    layers: tuple[HorizontalSectionLayer, ...],
    total_depth_m: float,
) -> tuple[HorizontalSectionLayer, ...]:
    if not layers:
        raise ValueError("At least one concrete layer is required.")
    if total_depth_m <= 0.0:
        raise ValueError("Section depth must be positive.")
    ordered = tuple(sorted(layers, key=lambda item: item.start_depth_m))
    if abs(ordered[0].start_depth_m) > 1.0e-9:
        raise ValueError("Layered fatigue section must start at depth zero.")
    for previous, current in pairwise(ordered):
        if abs(previous.end_depth_m - current.start_depth_m) > 1.0e-9:
            raise ValueError("Layered fatigue section must be contiguous.")
    if abs(ordered[-1].end_depth_m - total_depth_m) > 1.0e-9:
        raise ValueError("Layered fatigue section must end at the total depth.")
    if not any(item.active for item in ordered):
        raise ValueError("Layered fatigue section has no active concrete.")
    return ordered


def _concrete_first_moment_about_na(
    layers: tuple[HorizontalSectionLayer, ...],
    x_mm: float,
) -> float:
    value = 0.0
    for layer in layers:
        if not layer.active:
            continue
        y0 = layer.start_depth_m * 1000.0
        y1 = min(layer.end_depth_m * 1000.0, x_mm)
        if y1 <= y0:
            continue
        width = layer.width_m * 1000.0
        depth = y1 - y0
        centroid = 0.5 * (y0 + y1)
        value += width * depth * (x_mm - centroid)
    return value


def _concrete_inertia_about_na(
    layers: tuple[HorizontalSectionLayer, ...],
    x_mm: float,
) -> float:
    value = 0.0
    for layer in layers:
        if not layer.active:
            continue
        y0 = layer.start_depth_m * 1000.0
        y1 = min(layer.end_depth_m * 1000.0, x_mm)
        if y1 <= y0:
            continue
        width = layer.width_m * 1000.0
        depth = y1 - y0
        centroid = 0.5 * (y0 + y1)
        area = width * depth
        value += width * depth**3 / 12.0 + area * (x_mm - centroid) ** 2
    return value


def cracked_layered_multi_steel_section(
    *,
    layers: tuple[HorizontalSectionLayer, ...],
    total_depth_m: float,
    steel_layers: tuple[TransformedSteelLayer, ...],
    modular_ratio: float,
    moment_magnitude_knm: float,
) -> MultiSteelCrackedSectionResult:
    """Elastic cracked transformed section with multiple reinforcement layers.

    Depth zero is the concrete compression face for the supplied bending
    direction. Tensile concrete and inactive construction layers are neglected.
    Steel layers may fall on either side of the neutral axis, so the same kernel
    can recover tension and compression steel stresses through moment reversal.
    """
    ordered = _validated_layers(layers, total_depth_m)
    if not steel_layers:
        raise ValueError("At least one reinforcement layer is required.")
    if modular_ratio <= 0.0 or moment_magnitude_knm < 0.0:
        raise ValueError("Modular ratio must be positive and moment non-negative.")
    h_mm = total_depth_m * 1000.0
    if any(
        item.depth_from_compression_face_m >= total_depth_m
        for item in steel_layers
    ):
        raise ValueError("Every steel layer must lie inside the physical section.")
    if len({item.label for item in steel_layers}) != len(steel_layers):
        raise ValueError("Steel-layer labels must be unique.")

    transformed = tuple(
        (
            modular_ratio * item.area_mm2,
            item.depth_from_compression_face_m * 1000.0,
        )
        for item in steel_layers
    )

    def equilibrium(x_mm: float) -> float:
        concrete = _concrete_first_moment_about_na(ordered, x_mm)
        steel = sum(area * (depth - x_mm) for area, depth in transformed)
        return concrete - steel

    samples = 400
    x_values = tuple(
        1.0e-6 + (h_mm - 2.0e-6) * index / samples
        for index in range(samples + 1)
    )
    bracket: tuple[float, float] | None = None
    previous_x = x_values[0]
    previous_value = equilibrium(previous_x)
    for x_mm in x_values[1:]:
        value = equilibrium(x_mm)
        if previous_value == 0.0:
            bracket = (previous_x, previous_x)
            break
        if value == 0.0 or previous_value * value < 0.0:
            bracket = (previous_x, x_mm)
            break
        previous_x = x_mm
        previous_value = value
    if bracket is None:
        raise ValueError("Unable to bracket the multi-steel cracked neutral axis.")

    lower, upper = bracket
    if upper > lower:
        lower_value = equilibrium(lower)
        for _ in range(120):
            mid = 0.5 * (lower + upper)
            value = equilibrium(mid)
            if abs(value) <= 1.0e-7:
                lower = upper = mid
                break
            if lower_value * value <= 0.0:
                upper = mid
            else:
                lower = mid
                lower_value = value
    x_mm = 0.5 * (lower + upper)

    inertia = _concrete_inertia_about_na(ordered, x_mm) + sum(
        area * (depth - x_mm) ** 2
        for area, depth in transformed
    )
    if inertia <= 0.0:
        raise ValueError("Calculated multi-steel cracked inertia is non-positive.")

    moment_nmm = moment_magnitude_knm * 1.0e6
    stresses = tuple(
        (
            item.label,
            modular_ratio
            * moment_nmm
            * (item.depth_from_compression_face_m * 1000.0 - x_mm)
            / inertia,
        )
        for item in steel_layers
    )
    compression_face = moment_nmm * x_mm / inertia
    return MultiSteelCrackedSectionResult(
        neutral_axis_from_compression_face_mm=x_mm,
        second_moment_mm4=inertia,
        compression_face_stress_mpa=compression_face,
        steel_stresses_mpa=stresses,
    )
