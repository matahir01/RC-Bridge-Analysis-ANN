from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rc_bridge.analysis.physical_sections import ConcreteSectionLayer
from rc_bridge.design.eurocode_cracking import effective_tension_depth_mm


@dataclass(frozen=True)
class LayeredFlexureResult:
    resistance_knm: float
    neutral_axis_from_top_m: float
    compression_block_depth_m: float
    compression_centroid_from_top_m: float
    lever_arm_m: float
    steel_force_kn: float
    status: str


@dataclass(frozen=True)
class LayeredUncrackedSLS:
    transformed_area_mm2: float
    neutral_axis_from_top_mm: float
    second_moment_mm4: float
    cracking_moment_knm: float


@dataclass(frozen=True)
class LayeredCrackedSLS:
    neutral_axis_from_top_mm: float
    second_moment_mm4: float
    steel_stress_mpa: float


@dataclass(frozen=True)
class LayeredCrackWidthResult:
    crack_width_mm: float
    crack_limit_mm: float
    utilization: float
    steel_stress_mpa: float
    effective_tension_depth_mm: float
    effective_tension_area_mm2: float
    effective_reinforcement_ratio: float
    max_crack_spacing_mm: float
    strain_difference: float
    close_spacing: bool
    status: str


def _validate_layers(
    layers: tuple[ConcreteSectionLayer, ...],
    *,
    effective_depth_m: float,
) -> tuple[ConcreteSectionLayer, ...]:
    if not layers:
        raise ValueError("Layered section requires at least one concrete layer.")
    if effective_depth_m <= 0.0:
        raise ValueError("effective_depth_m must be positive.")
    ordered = tuple(sorted(layers, key=lambda item: (item.top_m, item.bottom_m)))
    for previous, current in pairwise(ordered):
        if current.top_m < previous.bottom_m - 1.0e-12:
            raise ValueError("Concrete layers must not overlap through the depth.")
    if effective_depth_m > max(item.bottom_m for item in ordered) + 1.0e-12:
        raise ValueError("Tension steel depth lies outside the layered section.")
    return ordered


def _layer_overlap(
    layer: ConcreteSectionLayer,
    *,
    top_m: float,
    bottom_m: float,
) -> tuple[float, float, float] | None:
    overlap_top = max(layer.top_m, top_m)
    overlap_bottom = min(layer.bottom_m, bottom_m)
    if overlap_bottom <= overlap_top:
        return None
    depth = overlap_bottom - overlap_top
    area = layer.width_m * depth
    centroid = 0.5 * (overlap_top + overlap_bottom)
    return area, centroid, depth


def _compression_block_properties(
    layers: tuple[ConcreteSectionLayer, ...],
    *,
    block_depth_m: float,
) -> tuple[float, float]:
    pieces: list[tuple[float, float]] = []
    for layer in layers:
        overlap = _layer_overlap(layer, top_m=0.0, bottom_m=block_depth_m)
        if overlap is None:
            continue
        area, centroid, _ = overlap
        pieces.append((area, centroid))
    area_total = sum(area for area, _ in pieces)
    if area_total <= 0.0:
        return 0.0, 0.0
    centroid = sum(area * y for area, y in pieces) / area_total
    return area_total, centroid


def layered_singly_reinforced_resistance(
    *,
    layers: tuple[ConcreteSectionLayer, ...],
    effective_depth_m: float,
    steel_area_mm2: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    lambda_block: float = 0.8,
) -> LayeredFlexureResult:
    """Positive-bending EC2-style resistance for a layered concrete section.

    The rectangular compression block is intersected with the actual concrete
    layers, so nonparticipating construction gaps and I/T flange transitions
    are represented explicitly instead of being collapsed to one T section.
    """
    ordered = _validate_layers(layers, effective_depth_m=effective_depth_m)
    if min(steel_area_mm2, fck_mpa, fyk_mpa, gamma_c, gamma_s, alpha_cc) <= 0.0:
        raise ValueError("Reinforcement, strengths and factors must be positive.")
    if not 0.0 < lambda_block <= 1.0:
        raise ValueError("lambda_block must lie in (0, 1].")

    fcd_mpa = alpha_cc * fck_mpa / gamma_c
    fyd_mpa = fyk_mpa / gamma_s
    steel_force_n = steel_area_mm2 * fyd_mpa
    required_concrete_area_m2 = steel_force_n / (fcd_mpa * 1.0e6)
    maximum_block_depth = min(
        effective_depth_m,
        max(layer.bottom_m for layer in ordered),
    )
    maximum_area, _ = _compression_block_properties(
        ordered,
        block_depth_m=maximum_block_depth,
    )
    if required_concrete_area_m2 > maximum_area + 1.0e-12:
        raise ValueError(
            "Required compression force exceeds the concrete available above the tension steel."
        )

    lower = 0.0
    upper = maximum_block_depth
    for _ in range(100):
        mid = 0.5 * (lower + upper)
        area, _ = _compression_block_properties(ordered, block_depth_m=mid)
        if area < required_concrete_area_m2:
            lower = mid
        else:
            upper = mid
    block_depth = upper
    area, centroid = _compression_block_properties(
        ordered,
        block_depth_m=block_depth,
    )
    if area <= 0.0:
        raise ValueError("Compression block contains no participating concrete.")
    neutral_axis = block_depth / lambda_block
    lever_arm = effective_depth_m - centroid
    if lever_arm <= 0.0:
        raise ValueError("Calculated layered-section lever arm is non-positive.")
    resistance_knm = steel_force_n * lever_arm / 1000.0
    return LayeredFlexureResult(
        resistance_knm=resistance_knm,
        neutral_axis_from_top_m=neutral_axis,
        compression_block_depth_m=block_depth,
        compression_centroid_from_top_m=centroid,
        lever_arm_m=lever_arm,
        steel_force_kn=steel_force_n / 1000.0,
        status=(
            "simplified EC2 layered positive-bending resistance; actual participating "
            "concrete bands/gaps retained; ductility and strain limits remain explicit "
            "verification items"
        ),
    )


def required_tension_steel_layered(
    *,
    med_knm: float,
    layers: tuple[ConcreteSectionLayer, ...],
    effective_depth_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    tolerance_knm: float = 0.01,
) -> float:
    if med_knm < 0.0:
        raise ValueError("Design moment cannot be negative.")
    if med_knm == 0.0:
        return 0.0
    lower = 1.0
    upper = 1000.0
    for _ in range(30):
        try:
            result = layered_singly_reinforced_resistance(
                layers=layers,
                effective_depth_m=effective_depth_m,
                steel_area_mm2=upper,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
            )
        except ValueError as exc:
            if "compression force exceeds" in str(exc):
                break
            raise
        if result.resistance_knm >= med_knm:
            break
        lower = upper
        upper *= 2.0
    else:
        raise ValueError("Unable to bracket required layered-section steel area.")

    # If the upper trial exceeded compression capacity, shrink back toward the
    # last valid point and determine whether the requested moment is attainable.
    valid_upper = upper
    while valid_upper > lower:
        try:
            upper_result = layered_singly_reinforced_resistance(
                layers=layers,
                effective_depth_m=effective_depth_m,
                steel_area_mm2=valid_upper,
                fck_mpa=fck_mpa,
                fyk_mpa=fyk_mpa,
            )
            break
        except ValueError as exc:
            if "compression force exceeds" not in str(exc):
                raise
            valid_upper = 0.5 * (lower + valid_upper)
    else:
        raise ValueError("Layered section cannot develop the requested moment.")
    if upper_result.resistance_knm < med_knm:
        raise ValueError("Layered section cannot develop the requested moment.")

    upper = valid_upper
    for _ in range(80):
        mid = 0.5 * (lower + upper)
        result = layered_singly_reinforced_resistance(
            layers=layers,
            effective_depth_m=effective_depth_m,
            steel_area_mm2=mid,
            fck_mpa=fck_mpa,
            fyk_mpa=fyk_mpa,
        )
        if abs(result.resistance_knm - med_knm) <= tolerance_knm:
            return mid
        if result.resistance_knm < med_knm:
            lower = mid
        else:
            upper = mid
    return upper


def uncracked_layered_section_sls(
    *,
    layers: tuple[ConcreteSectionLayer, ...],
    steel_area_mm2: float,
    steel_depth_m: float,
    modular_ratio: float,
    fct_eff_mpa: float,
    compression_steel_area_mm2: float = 0.0,
    compression_steel_depth_m: float | None = None,
) -> LayeredUncrackedSLS:
    ordered = _validate_layers(layers, effective_depth_m=steel_depth_m)
    if min(steel_area_mm2, modular_ratio, fct_eff_mpa) <= 0.0:
        raise ValueError("Uncracked layered-section inputs must be positive.")
    if compression_steel_area_mm2 < 0.0:
        raise ValueError("Compression steel area cannot be negative.")
    if compression_steel_area_mm2 > 0.0 and compression_steel_depth_m is None:
        raise ValueError("Compression steel depth is required when its area is positive.")
    if (
        compression_steel_depth_m is not None
        and not 0.0 < compression_steel_depth_m < steel_depth_m
    ):
        raise ValueError("Compression steel depth must lie above the tension steel.")
    concrete_area_mm2 = sum(layer.area_m2 for layer in ordered) * 1.0e6
    transformed_steel_area = modular_ratio * steel_area_mm2
    transformed_compression_area = modular_ratio * compression_steel_area_mm2
    transformed_area = (
        concrete_area_mm2
        + transformed_steel_area
        + transformed_compression_area
    )
    concrete_first = sum(
        layer.area_m2 * 1.0e6 * layer.centroid_from_top_m * 1000.0
        for layer in ordered
    )
    steel_y_mm = steel_depth_m * 1000.0
    compression_steel_y_mm = (
        None
        if compression_steel_depth_m is None
        else compression_steel_depth_m * 1000.0
    )
    compression_first = (
        0.0
        if compression_steel_y_mm is None
        else transformed_compression_area * compression_steel_y_mm
    )
    x_mm = (
        concrete_first
        + transformed_steel_area * steel_y_mm
        + compression_first
    ) / transformed_area
    inertia = 0.0
    for layer in ordered:
        width_mm = layer.width_m * 1000.0
        depth_mm = layer.depth_m * 1000.0
        area_mm2 = layer.area_m2 * 1.0e6
        y_mm = layer.centroid_from_top_m * 1000.0
        inertia += width_mm * depth_mm**3 / 12.0 + area_mm2 * (y_mm - x_mm) ** 2
    inertia += transformed_steel_area * (steel_y_mm - x_mm) ** 2
    if compression_steel_y_mm is not None:
        inertia += transformed_compression_area * (
            compression_steel_y_mm - x_mm
        ) ** 2
    if inertia <= 0.0:
        raise ValueError("Calculated layered uncracked inertia is non-positive.")
    bottom_mm = max(layer.bottom_m for layer in ordered) * 1000.0
    tensile_distance = bottom_mm - x_mm
    if tensile_distance <= 0.0:
        raise ValueError("Layered uncracked neutral axis is outside the section.")
    cracking_moment = fct_eff_mpa * inertia / tensile_distance / 1.0e6
    return LayeredUncrackedSLS(
        transformed_area_mm2=transformed_area,
        neutral_axis_from_top_mm=x_mm,
        second_moment_mm4=inertia,
        cracking_moment_knm=cracking_moment,
    )


def cracked_layered_section_sls(
    *,
    layers: tuple[ConcreteSectionLayer, ...],
    steel_area_mm2: float,
    steel_depth_m: float,
    modular_ratio: float,
    service_moment_knm: float,
    compression_steel_area_mm2: float = 0.0,
    compression_steel_depth_m: float | None = None,
) -> LayeredCrackedSLS:
    ordered = _validate_layers(layers, effective_depth_m=steel_depth_m)
    if min(steel_area_mm2, modular_ratio) <= 0.0 or service_moment_knm < 0.0:
        raise ValueError("Cracked layered-section inputs are invalid.")
    if compression_steel_area_mm2 < 0.0:
        raise ValueError("Compression steel area cannot be negative.")
    if compression_steel_area_mm2 > 0.0 and compression_steel_depth_m is None:
        raise ValueError("Compression steel depth is required when its area is positive.")
    if (
        compression_steel_depth_m is not None
        and not 0.0 < compression_steel_depth_m < steel_depth_m
    ):
        raise ValueError("Compression steel depth must lie above the tension steel.")
    d_mm = steel_depth_m * 1000.0
    compression_d_mm = (
        None
        if compression_steel_depth_m is None
        else compression_steel_depth_m * 1000.0
    )
    nas = modular_ratio * steel_area_mm2
    nas_compression = modular_ratio * compression_steel_area_mm2

    def equilibrium(x_mm: float) -> float:
        x_m = x_mm / 1000.0
        concrete_first = 0.0
        for layer in ordered:
            overlap = _layer_overlap(layer, top_m=0.0, bottom_m=x_m)
            if overlap is None:
                continue
            area_m2, centroid_m, _ = overlap
            concrete_first += area_m2 * 1.0e6 * (x_mm - centroid_m * 1000.0)
        compression_steel_first = (
            0.0
            if compression_d_mm is None
            else nas_compression * (x_mm - compression_d_mm)
        )
        return (
            concrete_first
            + compression_steel_first
            - nas * (d_mm - x_mm)
        )

    lower = 1.0e-6
    upper = d_mm - 1.0e-6
    if equilibrium(lower) >= 0.0 or equilibrium(upper) <= 0.0:
        raise ValueError("Unable to bracket cracked layered-section neutral axis.")
    for _ in range(100):
        mid = 0.5 * (lower + upper)
        if equilibrium(mid) < 0.0:
            lower = mid
        else:
            upper = mid
    x_mm = 0.5 * (lower + upper)
    x_m = x_mm / 1000.0
    inertia = 0.0
    for layer in ordered:
        overlap = _layer_overlap(layer, top_m=0.0, bottom_m=x_m)
        if overlap is None:
            continue
        area_m2, centroid_m, depth_m = overlap
        width_mm = layer.width_m * 1000.0
        depth_mm = depth_m * 1000.0
        area_mm2 = area_m2 * 1.0e6
        centroid_mm = centroid_m * 1000.0
        inertia += (
            width_mm * depth_mm**3 / 12.0
            + area_mm2 * (x_mm - centroid_mm) ** 2
        )
    inertia += nas * (d_mm - x_mm) ** 2
    if compression_d_mm is not None:
        inertia += nas_compression * (x_mm - compression_d_mm) ** 2
    if inertia <= 0.0:
        raise ValueError("Calculated layered cracked inertia is non-positive.")
    steel_stress = (
        modular_ratio * service_moment_knm * 1.0e6 * (d_mm - x_mm) / inertia
    )
    return LayeredCrackedSLS(
        neutral_axis_from_top_mm=x_mm,
        second_moment_mm4=inertia,
        steel_stress_mpa=steel_stress,
    )


def layered_effective_tension_area_mm2(
    *,
    layers: tuple[ConcreteSectionLayer, ...],
    total_depth_m: float,
    effective_tension_depth_mm_value: float,
) -> float:
    if total_depth_m <= 0.0 or effective_tension_depth_mm_value <= 0.0:
        raise ValueError("Effective tension-zone inputs must be positive.")
    top = total_depth_m - effective_tension_depth_mm_value / 1000.0
    area = 0.0
    for layer in layers:
        overlap = _layer_overlap(layer, top_m=top, bottom_m=total_depth_m)
        if overlap is not None:
            area += overlap[0] * 1.0e6
    if area <= 0.0:
        raise ValueError("Effective tension zone contains no participating concrete.")
    return area


def crack_width_layered_section(
    *,
    layers: tuple[ConcreteSectionLayer, ...],
    total_depth_m: float,
    steel_area_mm2: float,
    steel_depth_m: float,
    bar_diameter_mm: float,
    bar_spacing_mm: float,
    cover_mm: float,
    service_moment_knm: float,
    cracking_moment_knm: float,
    es_mpa: float,
    ecm_mpa: float,
    fct_eff_mpa: float,
    crack_limit_mm: float,
    compression_steel_area_mm2: float = 0.0,
    compression_steel_depth_m: float | None = None,
    kt: float = 0.4,
    k1: float = 0.8,
    k2: float = 0.5,
    k3: float = 3.4,
    k4: float = 0.425,
) -> LayeredCrackWidthResult:
    positive = (
        total_depth_m, steel_area_mm2, steel_depth_m, bar_diameter_mm,
        bar_spacing_mm, cover_mm, es_mpa, ecm_mpa, fct_eff_mpa, crack_limit_mm,
    )
    if any(value <= 0.0 for value in positive):
        raise ValueError("Layered crack-width inputs must be positive.")
    if service_moment_knm < 0.0 or cracking_moment_knm <= 0.0:
        raise ValueError("Service moment/cracking moment inputs are invalid.")
    if not 0.0 < kt <= 1.0:
        raise ValueError("kt must lie between zero and one.")
    modular_ratio = es_mpa / ecm_mpa
    cracked = cracked_layered_section_sls(
        layers=layers,
        steel_area_mm2=steel_area_mm2,
        steel_depth_m=steel_depth_m,
        modular_ratio=modular_ratio,
        service_moment_knm=service_moment_knm,
        compression_steel_area_mm2=compression_steel_area_mm2,
        compression_steel_depth_m=compression_steel_depth_m,
    )
    hceff = effective_tension_depth_mm(
        total_depth_m,
        steel_depth_m,
        cracked.neutral_axis_from_top_mm,
    )
    aceff = layered_effective_tension_area_mm2(
        layers=layers,
        total_depth_m=total_depth_m,
        effective_tension_depth_mm_value=hceff,
    )
    rho = steel_area_mm2 / aceff
    sigma_s = cracked.steel_stress_mpa
    if service_moment_knm <= cracking_moment_knm:
        return LayeredCrackWidthResult(
            crack_width_mm=0.0, crack_limit_mm=crack_limit_mm, utilization=0.0,
            steel_stress_mpa=sigma_s, effective_tension_depth_mm=hceff,
            effective_tension_area_mm2=aceff, effective_reinforcement_ratio=rho,
            max_crack_spacing_mm=0.0, strain_difference=0.0, close_spacing=True,
            status="uncracked under supplied service moment",
        )
    strain_calc = (
        sigma_s - kt * fct_eff_mpa / rho * (1.0 + modular_ratio * rho)
    ) / es_mpa
    strain_min = 0.6 * sigma_s / es_mpa
    strain_difference = max(strain_calc, strain_min, 0.0)
    close_spacing = bar_spacing_mm <= 5.0 * (cover_mm + bar_diameter_mm / 2.0)
    if close_spacing:
        srmax = k3 * cover_mm + k1 * k2 * k4 * bar_diameter_mm / rho
    else:
        srmax = 1.3 * (total_depth_m * 1000.0 - cracked.neutral_axis_from_top_mm)
    crack_width = srmax * strain_difference
    return LayeredCrackWidthResult(
        crack_width_mm=crack_width,
        crack_limit_mm=crack_limit_mm,
        utilization=crack_width / crack_limit_mm,
        steel_stress_mpa=sigma_s,
        effective_tension_depth_mm=hceff,
        effective_tension_area_mm2=aceff,
        effective_reinforcement_ratio=rho,
        max_crack_spacing_mm=srmax,
        strain_difference=strain_difference,
        close_spacing=close_spacing,
        status=(
            "EC2 layered crack-width calculation with actual participating "
            "concrete bands/gaps and optional transformed compression reinforcement"
        ),
    )
