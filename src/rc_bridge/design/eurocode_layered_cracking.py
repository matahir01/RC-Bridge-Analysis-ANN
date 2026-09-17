from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rc_bridge.design.eurocode_cracking import CrackWidthResult


@dataclass(frozen=True)
class HorizontalSectionLayer:
    """One non-overlapping horizontal strip measured from the compression face.

    ``active=False`` keeps the layer's physical thickness in the section geometry
    while excluding its concrete area from stiffness, cracking moment and effective
    tension area. This is intended for construction layers whose structural
    participation has not been justified.
    """

    width_m: float
    start_depth_m: float
    end_depth_m: float
    label: str = ""
    active: bool = True

    def __post_init__(self) -> None:
        if self.width_m <= 0.0:
            raise ValueError("Layer width must be positive.")
        if self.start_depth_m < 0.0:
            raise ValueError("Layer start depth cannot be negative.")
        if self.end_depth_m <= self.start_depth_m:
            raise ValueError("Layer end depth must exceed its start depth.")


@dataclass(frozen=True)
class CrackedLayeredSectionSLS:
    neutral_axis_from_compression_face_mm: float
    second_moment_mm4: float
    steel_stress_mpa: float
    effective_tension_depth_mm: float
    effective_tension_area_mm2: float
    gross_cracking_moment_knm: float


def _validated_layers(
    layers: tuple[HorizontalSectionLayer, ...],
    total_depth_m: float,
) -> tuple[HorizontalSectionLayer, ...]:
    if not layers:
        raise ValueError("At least one concrete layer is required.")
    if total_depth_m <= 0.0:
        raise ValueError("Total section depth must be positive.")

    ordered = tuple(sorted(layers, key=lambda item: item.start_depth_m))
    tolerance = 1e-9
    if abs(ordered[0].start_depth_m) > tolerance:
        raise ValueError("Layered section must start at the compression face (depth 0).")
    for previous, current in pairwise(ordered):
        if abs(previous.end_depth_m - current.start_depth_m) > tolerance:
            raise ValueError("Layered section strips must be contiguous and non-overlapping.")
    if abs(ordered[-1].end_depth_m - total_depth_m) > tolerance:
        raise ValueError("Layered section strips must terminate at the total section depth.")
    if not any(layer.active for layer in ordered):
        raise ValueError("Layered section must contain at least one active concrete layer.")
    return ordered


def _gross_concrete_properties(
    layers: tuple[HorizontalSectionLayer, ...],
) -> tuple[float, float, float]:
    """Return active gross concrete area [mm2], centroid y [mm], inertia [mm4]."""
    areas: list[tuple[float, float, float]] = []
    for layer in layers:
        if not layer.active:
            continue
        width = layer.width_m * 1000.0
        y0 = layer.start_depth_m * 1000.0
        y1 = layer.end_depth_m * 1000.0
        depth = y1 - y0
        area = width * depth
        centroid = 0.5 * (y0 + y1)
        local_inertia = width * depth**3 / 12.0
        areas.append((area, centroid, local_inertia))

    total_area = sum(item[0] for item in areas)
    if total_area <= 0.0:
        raise ValueError("Layered section has no active gross concrete area.")
    centroid = sum(area * y for area, y, _ in areas) / total_area
    inertia = sum(local_i + area * (y - centroid) ** 2 for area, y, local_i in areas)
    return total_area, centroid, inertia


def layered_cracking_moment_knm(
    layers: tuple[HorizontalSectionLayer, ...],
    *,
    total_depth_m: float,
    fct_eff_mpa: float,
) -> float:
    """Gross-section cracking moment for tension at the face opposite depth zero."""
    if fct_eff_mpa <= 0.0:
        raise ValueError("fct_eff_mpa must be positive.")
    ordered = _validated_layers(layers, total_depth_m)
    _, centroid_mm, inertia_mm4 = _gross_concrete_properties(ordered)
    h_mm = total_depth_m * 1000.0
    tension_face_distance_mm = h_mm - centroid_mm
    if tension_face_distance_mm <= 0.0:
        raise ValueError("Invalid gross section centroid for cracking calculation.")
    return fct_eff_mpa * inertia_mm4 / tension_face_distance_mm / 1e6


def _compressed_concrete_first_moment_about_na(
    layers: tuple[HorizontalSectionLayer, ...],
    x_mm: float,
) -> float:
    first_moment = 0.0
    for layer in layers:
        if not layer.active:
            continue
        width = layer.width_m * 1000.0
        y0 = layer.start_depth_m * 1000.0
        y1 = min(layer.end_depth_m * 1000.0, x_mm)
        if y1 <= y0:
            continue
        depth = y1 - y0
        centroid = 0.5 * (y0 + y1)
        first_moment += width * depth * (x_mm - centroid)
    return first_moment


def _compressed_concrete_inertia_about_na(
    layers: tuple[HorizontalSectionLayer, ...],
    x_mm: float,
) -> float:
    inertia = 0.0
    for layer in layers:
        if not layer.active:
            continue
        width = layer.width_m * 1000.0
        y0 = layer.start_depth_m * 1000.0
        y1 = min(layer.end_depth_m * 1000.0, x_mm)
        if y1 <= y0:
            continue
        depth = y1 - y0
        centroid = 0.5 * (y0 + y1)
        area = width * depth
        inertia += width * depth**3 / 12.0 + area * (x_mm - centroid) ** 2
    return inertia


def _effective_tension_area_mm2(
    layers: tuple[HorizontalSectionLayer, ...],
    *,
    total_depth_m: float,
    hceff_mm: float,
) -> float:
    h_mm = total_depth_m * 1000.0
    tension_zone_start = h_mm - hceff_mm
    area = 0.0
    for layer in layers:
        if not layer.active:
            continue
        width = layer.width_m * 1000.0
        y0 = max(layer.start_depth_m * 1000.0, tension_zone_start)
        y1 = layer.end_depth_m * 1000.0
        if y1 > y0:
            area += width * (y1 - y0)
    if area <= 0.0:
        raise ValueError("Calculated effective tension area is non-positive.")
    return area


def cracked_layered_section_sls(
    layers: tuple[HorizontalSectionLayer, ...],
    *,
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_from_compression_face_m: float,
    modular_ratio: float,
    service_moment_knm: float,
    fct_eff_mpa: float,
) -> CrackedLayeredSectionSLS:
    """Elastic transformed cracked analysis for a layered concrete section.

    Depth zero is always the compression face for the supplied bending direction;
    the tension face is at ``total_depth_m``. Tensile concrete and inactive layers
    are neglected in transformed stiffness.
    """
    ordered = _validated_layers(layers, total_depth_m)
    if min(steel_area_mm2, modular_ratio, fct_eff_mpa) <= 0.0:
        raise ValueError("Steel area, modular ratio and tensile strength must be positive.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment magnitude cannot be negative.")
    if not 0.0 < steel_depth_from_compression_face_m < total_depth_m:
        raise ValueError("Tension steel depth must lie inside the section.")

    h_mm = total_depth_m * 1000.0
    d_mm = steel_depth_from_compression_face_m * 1000.0
    nas = modular_ratio * steel_area_mm2

    def equilibrium(x_mm: float) -> float:
        concrete_first_moment = _compressed_concrete_first_moment_about_na(ordered, x_mm)
        steel_first_moment = nas * (d_mm - x_mm)
        return concrete_first_moment - steel_first_moment

    lower = 1e-6
    upper = min(d_mm - 1e-6, h_mm - 1e-6)
    if equilibrium(lower) >= 0.0 or equilibrium(upper) <= 0.0:
        raise ValueError("Unable to bracket cracked neutral axis for this layered section.")

    for _ in range(120):
        mid = 0.5 * (lower + upper)
        value = equilibrium(mid)
        if abs(value) <= 1e-7:
            lower = upper = mid
            break
        if value < 0.0:
            lower = mid
        else:
            upper = mid
    x_mm = 0.5 * (lower + upper)

    concrete_inertia = _compressed_concrete_inertia_about_na(ordered, x_mm)
    inertia_mm4 = concrete_inertia + nas * (d_mm - x_mm) ** 2
    if inertia_mm4 <= 0.0:
        raise ValueError("Calculated cracked second moment is non-positive.")

    moment_nmm = service_moment_knm * 1e6
    steel_stress_mpa = modular_ratio * moment_nmm * (d_mm - x_mm) / inertia_mm4
    hceff_mm = min(2.5 * (h_mm - d_mm), (h_mm - x_mm) / 3.0, h_mm / 2.0)
    if hceff_mm <= 0.0:
        raise ValueError("Calculated effective tension depth is non-positive.")
    aceff_mm2 = _effective_tension_area_mm2(
        ordered,
        total_depth_m=total_depth_m,
        hceff_mm=hceff_mm,
    )
    mcr_knm = layered_cracking_moment_knm(
        ordered,
        total_depth_m=total_depth_m,
        fct_eff_mpa=fct_eff_mpa,
    )
    return CrackedLayeredSectionSLS(
        neutral_axis_from_compression_face_mm=x_mm,
        second_moment_mm4=inertia_mm4,
        steel_stress_mpa=steel_stress_mpa,
        effective_tension_depth_mm=hceff_mm,
        effective_tension_area_mm2=aceff_mm2,
        gross_cracking_moment_knm=mcr_knm,
    )


def crack_width_ec2_layered_section(
    *,
    layers: tuple[HorizontalSectionLayer, ...],
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_from_compression_face_m: float,
    bar_diameter_mm: float,
    bar_spacing_mm: float,
    cover_mm: float,
    service_moment_knm: float,
    es_mpa: float,
    ecm_mpa: float,
    fct_eff_mpa: float,
    crack_limit_mm: float,
    kt: float = 0.4,
    k1: float = 0.8,
    k2: float = 0.5,
    k3: float = 3.4,
    k4: float = 0.425,
) -> CrackWidthResult:
    """First-generation EC2 direct crack-width calculation for a layered section."""
    positive = (
        steel_area_mm2,
        bar_diameter_mm,
        bar_spacing_mm,
        cover_mm,
        es_mpa,
        ecm_mpa,
        fct_eff_mpa,
        crack_limit_mm,
    )
    if any(value <= 0.0 for value in positive):
        raise ValueError("Reinforcement, material, cover and crack-limit inputs must be positive.")
    if service_moment_knm < 0.0:
        raise ValueError("Service moment magnitude cannot be negative.")
    if not 0.0 < kt <= 1.0:
        raise ValueError("kt must lie between zero and one.")

    cracked = cracked_layered_section_sls(
        layers,
        total_depth_m=total_depth_m,
        steel_area_mm2=steel_area_mm2,
        steel_depth_from_compression_face_m=steel_depth_from_compression_face_m,
        modular_ratio=es_mpa / ecm_mpa,
        service_moment_knm=service_moment_knm,
        fct_eff_mpa=fct_eff_mpa,
    )
    rho = steel_area_mm2 / cracked.effective_tension_area_mm2
    if rho <= 0.0:
        raise ValueError("Effective reinforcement ratio must be positive.")

    sigma_s = cracked.steel_stress_mpa
    if service_moment_knm <= cracked.gross_cracking_moment_knm:
        return CrackWidthResult(
            crack_width_mm=0.0,
            crack_limit_mm=crack_limit_mm,
            utilization=0.0,
            g_crack_mm=crack_limit_mm,
            steel_stress_mpa=sigma_s,
            effective_tension_depth_mm=cracked.effective_tension_depth_mm,
            effective_tension_area_mm2=cracked.effective_tension_area_mm2,
            effective_reinforcement_ratio=rho,
            max_crack_spacing_mm=0.0,
            strain_difference=0.0,
            close_spacing=True,
            status="uncracked under supplied service moment",
        )

    strain_calc = (
        sigma_s - kt * fct_eff_mpa / rho * (1.0 + (es_mpa / ecm_mpa) * rho)
    ) / es_mpa
    strain_min = 0.6 * sigma_s / es_mpa
    strain_difference = max(strain_calc, strain_min, 0.0)

    close_spacing = bar_spacing_mm <= 5.0 * (cover_mm + bar_diameter_mm / 2.0)
    if close_spacing:
        srmax = k3 * cover_mm + k1 * k2 * k4 * bar_diameter_mm / rho
    else:
        h_mm = total_depth_m * 1000.0
        srmax = 1.3 * (h_mm - cracked.neutral_axis_from_compression_face_mm)

    crack_width_mm = srmax * strain_difference
    return CrackWidthResult(
        crack_width_mm=crack_width_mm,
        crack_limit_mm=crack_limit_mm,
        utilization=crack_width_mm / crack_limit_mm,
        g_crack_mm=crack_limit_mm - crack_width_mm,
        steel_stress_mpa=sigma_s,
        effective_tension_depth_mm=cracked.effective_tension_depth_mm,
        effective_tension_area_mm2=cracked.effective_tension_area_mm2,
        effective_reinforcement_ratio=rho,
        max_crack_spacing_mm=srmax,
        strain_difference=strain_difference,
        close_spacing=close_spacing,
        status="first-generation EC2 direct crack-width calculation for a layered section",
    )
