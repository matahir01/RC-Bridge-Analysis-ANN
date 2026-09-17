from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BS5400BeamDetailingResult:
    minimum_main_steel_mm2: float
    maximum_main_steel_mm2: float
    provided_main_steel_mm2: float
    main_steel_above_minimum: bool
    main_steel_below_maximum: bool
    side_face_reinforcement_required: bool
    minimum_side_face_steel_each_face_mm2: float
    provided_side_face_steel_each_face_mm2: float
    side_face_steel_ok: bool
    minimum_clear_bar_spacing_mm: float
    provided_clear_bar_spacing_mm: float
    clear_spacing_ok: bool
    maximum_tension_bar_spacing_mm: float
    provided_tension_bar_spacing_mm: float
    tension_spacing_ok: bool
    maximum_link_spacing_mm: float
    provided_link_spacing_mm: float
    link_spacing_ok: bool
    passes: bool
    status: str


def _minimum_main_ratio(reinforcement_grade_mpa: float) -> float:
    """Return BS 5400-4 5.8.4.1 minimum main reinforcement ratio."""
    if abs(reinforcement_grade_mpa - 460.0) < 1e-9:
        return 0.0015
    if abs(reinforcement_grade_mpa - 250.0) < 1e-9:
        return 0.0025
    raise ValueError(
        "BS 5400 minimum-main-steel defaults are defined here only for legacy "
        "Grade 460 or Grade 250 reinforcement; supply the adopted legacy grade explicitly."
    )


def check_beam_detailing_bs5400(
    *,
    average_breadth_excluding_compression_flange_m: float,
    effective_depth_m: float,
    gross_concrete_area_m2: float,
    provided_main_steel_mm2: float,
    reinforcement_grade_mpa: float,
    side_face_depth_m: float,
    side_face_breadth_m: float,
    provided_side_face_steel_each_face_mm2: float,
    maximum_aggregate_size_mm: float,
    provided_clear_bar_spacing_mm: float,
    provided_tension_bar_spacing_mm: float,
    provided_link_spacing_mm: float,
    maximum_tension_bar_spacing_mm: float = 300.0,
) -> BS5400BeamDetailingResult:
    """Check a focused set of BS 5400-4 beam detailing provisions.

    The minimum main-steel rule uses b_a*d, where b_a excludes a compression
    flange for non-rectangular sections. Deep-beam side-face reinforcement is
    checked when the side-face depth exceeds 600 mm. The 300 mm tension-bar
    spacing is only the geometric ceiling; crack-width control may require less.
    """
    positive = (
        average_breadth_excluding_compression_flange_m,
        effective_depth_m,
        gross_concrete_area_m2,
        provided_main_steel_mm2,
        reinforcement_grade_mpa,
        side_face_depth_m,
        side_face_breadth_m,
        maximum_aggregate_size_mm,
        provided_clear_bar_spacing_mm,
        provided_tension_bar_spacing_mm,
        provided_link_spacing_mm,
        maximum_tension_bar_spacing_mm,
    )
    if any(value <= 0.0 for value in positive):
        raise ValueError("BS 5400 beam detailing dimensions and reinforcement must be positive.")
    if provided_side_face_steel_each_face_mm2 < 0.0:
        raise ValueError("provided_side_face_steel_each_face_mm2 cannot be negative.")

    ba_mm = average_breadth_excluding_compression_flange_m * 1000.0
    d_mm = effective_depth_m * 1000.0
    gross_area_mm2 = gross_concrete_area_m2 * 1_000_000.0
    side_breadth_mm = side_face_breadth_m * 1000.0

    minimum_main = _minimum_main_ratio(reinforcement_grade_mpa) * ba_mm * d_mm
    maximum_main = 0.04 * gross_area_mm2

    side_required = side_face_depth_m > 0.60
    minimum_side = 0.0005 * side_breadth_mm * d_mm if side_required else 0.0
    side_ok = (
        provided_side_face_steel_each_face_mm2 >= minimum_side
        if side_required
        else True
    )

    minimum_clear = maximum_aggregate_size_mm + 5.0
    maximum_link = 0.75 * d_mm

    above_min = provided_main_steel_mm2 >= minimum_main
    below_max = provided_main_steel_mm2 <= maximum_main
    clear_ok = provided_clear_bar_spacing_mm >= minimum_clear
    tension_spacing_ok = provided_tension_bar_spacing_mm <= maximum_tension_bar_spacing_mm
    link_spacing_ok = provided_link_spacing_mm <= maximum_link
    passes = all(
        (
            above_min,
            below_max,
            side_ok,
            clear_ok,
            tension_spacing_ok,
            link_spacing_ok,
        )
    )

    return BS5400BeamDetailingResult(
        minimum_main_steel_mm2=minimum_main,
        maximum_main_steel_mm2=maximum_main,
        provided_main_steel_mm2=provided_main_steel_mm2,
        main_steel_above_minimum=above_min,
        main_steel_below_maximum=below_max,
        side_face_reinforcement_required=side_required,
        minimum_side_face_steel_each_face_mm2=minimum_side,
        provided_side_face_steel_each_face_mm2=provided_side_face_steel_each_face_mm2,
        side_face_steel_ok=side_ok,
        minimum_clear_bar_spacing_mm=minimum_clear,
        provided_clear_bar_spacing_mm=provided_clear_bar_spacing_mm,
        clear_spacing_ok=clear_ok,
        maximum_tension_bar_spacing_mm=maximum_tension_bar_spacing_mm,
        provided_tension_bar_spacing_mm=provided_tension_bar_spacing_mm,
        tension_spacing_ok=tension_spacing_ok,
        maximum_link_spacing_mm=maximum_link,
        provided_link_spacing_mm=provided_link_spacing_mm,
        link_spacing_ok=link_spacing_ok,
        passes=passes,
        status=(
            "BS 5400-4 legacy beam detailing checks: minimum/maximum main steel, "
            "deep-beam side-face steel and selected spacing limits; crack-width, "
            "cover, anchorage and lap checks remain separate."
        ),
    )
