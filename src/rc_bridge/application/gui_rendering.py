from __future__ import annotations

from collections.abc import Sequence

from rc_bridge.application.gui_presenters import BridgePreviewData


def _canvas_size(canvas, *, fallback_width: int, fallback_height: int) -> tuple[int, int]:
    width = int(canvas.winfo_width())
    height = int(canvas.winfo_height())
    if width <= 1:
        width = int(canvas.winfo_reqwidth() or fallback_width)
    if height <= 1:
        height = int(canvas.winfo_reqheight() or fallback_height)
    return max(width, fallback_width), max(height, fallback_height)


def draw_bridge_preview(canvas, data: BridgePreviewData) -> None:
    """Draw a clean plan/cross-section engineering preview on a Tk Canvas."""

    canvas.delete("all")
    width, height = _canvas_size(canvas, fallback_width=820, fallback_height=300)
    ink = "#172033"
    muted = "#5F6F82"
    border = "#D6E0EA"
    primary = "#163B65"
    accent = "#2F6FB3"
    deck_fill = "#E8EEF5"
    carriageway_fill = "#DCE8F3"
    concrete_fill = "#CCD7E2"

    margin = 28
    split_x = int(width * 0.62)

    canvas.create_text(
        margin,
        18,
        text="BRIDGE PLAN",
        anchor="w",
        fill=muted,
        font=("Segoe UI Semibold", 9),
    )
    canvas.create_text(
        split_x + margin,
        18,
        text="TRANSVERSE / GIRDER SECTION",
        anchor="w",
        fill=muted,
        font=("Segoe UI Semibold", 9),
    )
    canvas.create_line(split_x, 10, split_x, height - 10, fill=border)

    # Plan view.
    plan_left = margin
    plan_right = split_x - margin
    plan_top = 48
    plan_bottom = max(plan_top + 120, height - 52)
    total_length = max(data.total_length_m, 1.0)
    deck_width = max(data.deck_width_m, 1.0)
    x_scale = (plan_right - plan_left) / total_length
    y_scale = min((plan_bottom - plan_top) / deck_width, 22.0)
    centre_y = 0.5 * (plan_top + plan_bottom)
    deck_top = centre_y - 0.5 * deck_width * y_scale
    deck_bottom = centre_y + 0.5 * deck_width * y_scale

    canvas.create_rectangle(
        plan_left,
        deck_top,
        plan_right,
        deck_bottom,
        fill=deck_fill,
        outline=primary,
        width=2,
    )
    carriage_top = centre_y - data.carriageway_right_m * y_scale
    carriage_bottom = centre_y - data.carriageway_left_m * y_scale
    canvas.create_rectangle(
        plan_left,
        carriage_top,
        plan_right,
        carriage_bottom,
        fill=carriageway_fill,
        outline="",
    )
    canvas.create_line(
        plan_left,
        centre_y,
        plan_right,
        centre_y,
        fill=border,
        dash=(4, 3),
    )

    for y_m in data.girder_y_m:
        y_px = centre_y - y_m * y_scale
        canvas.create_line(
            plan_left,
            y_px,
            plan_right,
            y_px,
            fill=accent,
            width=2,
        )

    x = plan_left
    canvas.create_line(x, deck_top - 8, x, deck_bottom + 8, fill=ink, width=2)
    for index, span in enumerate(data.span_lengths_m, start=1):
        x_next = x + span * x_scale
        canvas.create_line(
            x_next,
            deck_top - 8,
            x_next,
            deck_bottom + 8,
            fill=ink,
            width=2,
        )
        canvas.create_text(
            0.5 * (x + x_next),
            deck_bottom + 20,
            text=f"Span {index}: {span:g} m",
            fill=muted,
            font=("Segoe UI", 8),
        )
        x = x_next

    canvas.create_text(
        plan_left,
        deck_top - 18,
        text=(
            f"{len(data.girder_y_m)} girders · deck {data.deck_width_m:g} m · "
            f"carriageway {data.carriageway_right_m - data.carriageway_left_m:g} m"
        ),
        anchor="w",
        fill=ink,
        font=("Segoe UI Semibold", 9),
    )

    # Transverse cross-section and one representative girder.
    section_left = split_x + margin
    section_right = width - margin
    section_top = 48
    section_bottom = height - 30
    section_width = max(section_right - section_left, 180)
    total_depth = max(
        data.girder_depth_m + data.false_slab_depth_m + data.in_situ_slab_depth_m,
        0.1,
    )
    x_scale_section = section_width / max(data.deck_width_m, 1.0)
    z_scale = min((section_bottom - section_top - 20) / total_depth, 150.0)
    deck_y = section_top + (
        data.false_slab_depth_m + data.in_situ_slab_depth_m
    ) * z_scale

    deck_left = 0.5 * (section_left + section_right) - 0.5 * data.deck_width_m * x_scale_section
    deck_right = 0.5 * (section_left + section_right) + 0.5 * data.deck_width_m * x_scale_section
    false_y = section_top + data.in_situ_slab_depth_m * z_scale
    canvas.create_rectangle(
        deck_left,
        section_top,
        deck_right,
        false_y,
        fill="#DCE7F2",
        outline=primary,
    )
    canvas.create_rectangle(
        deck_left,
        false_y,
        deck_right,
        deck_y,
        fill="#EEF2F6",
        outline=primary,
    )

    centre_x = 0.5 * (section_left + section_right)
    outline = data.girder_outline_m
    if outline:
        max_width = max(abs(x) for x, _ in outline) * 2.0
        girder_scale_x = min(
            x_scale_section,
            (section_width * 0.45) / max(max_width, 0.05),
        )
        points: list[float] = []
        for x_m, z_m in outline:
            points.extend(
                (
                    centre_x + x_m * girder_scale_x,
                    deck_y + z_m * z_scale,
                )
            )
        canvas.create_polygon(
            *points,
            fill=concrete_fill,
            outline=primary,
            width=2,
        )

    canvas.create_text(
        section_left,
        section_bottom,
        text=(
            f"{data.girder_shape.upper()} precast girder {data.girder_depth_m * 1000:.0f} mm"
            f" + {data.false_slab_depth_m * 1000:.0f} mm false slab"
            f" + {data.in_situ_slab_depth_m * 1000:.0f} mm in-situ deck"
        ),
        anchor="sw",
        fill=muted,
        font=("Segoe UI", 8),
    )


def draw_bar_chart(
    canvas,
    *,
    labels: Sequence[str],
    values: Sequence[float],
    title: str,
    unit: str,
    threshold: float | None = None,
) -> None:
    canvas.delete("all")
    width, height = _canvas_size(canvas, fallback_width=650, fallback_height=250)
    ink = "#172033"
    muted = "#5F6F82"
    border = "#D6E0EA"
    accent = "#2F6FB3"
    warning = "#A06000"

    canvas.create_text(
        18,
        16,
        text=title,
        anchor="w",
        fill=ink,
        font=("Segoe UI Semibold", 10),
    )
    if not values:
        canvas.create_text(
            width / 2,
            height / 2,
            text="No result data available",
            fill=muted,
            font=("Segoe UI", 10),
        )
        return

    left = 48
    right = width - 18
    top = 42
    bottom = height - 42
    max_value = max(max(abs(float(value)) for value in values), threshold or 0.0, 1.0e-9)
    chart_height = bottom - top
    canvas.create_line(left, bottom, right, bottom, fill=border)
    bar_width = max((right - left) / max(len(values), 1) * 0.58, 4.0)
    step = (right - left) / max(len(values), 1)

    if threshold is not None and threshold > 0.0:
        y = bottom - threshold / max_value * chart_height
        canvas.create_line(left, y, right, y, fill=warning, dash=(5, 3))
        canvas.create_text(
            right,
            y - 3,
            text=f"limit {threshold:g}",
            anchor="se",
            fill=warning,
            font=("Segoe UI", 8),
        )

    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        x = left + (index + 0.5) * step
        bar_height = abs(float(value)) / max_value * chart_height
        canvas.create_rectangle(
            x - bar_width / 2,
            bottom - bar_height,
            x + bar_width / 2,
            bottom,
            fill=accent,
            outline="",
        )
        canvas.create_text(
            x,
            bottom + 12,
            text=str(label),
            fill=muted,
            font=("Segoe UI", 8),
        )
        canvas.create_text(
            x,
            max(top + 8, bottom - bar_height - 8),
            text=f"{float(value):.3g}",
            fill=ink,
            font=("Segoe UI", 8),
        )
    canvas.create_text(
        left,
        top - 10,
        text=unit,
        anchor="w",
        fill=muted,
        font=("Segoe UI", 8),
    )


def draw_line_chart(
    canvas,
    *,
    x_values: Sequence[float],
    series: Sequence[tuple[str, Sequence[float]]],
    title: str,
    y_unit: str,
) -> None:
    canvas.delete("all")
    width, height = _canvas_size(canvas, fallback_width=650, fallback_height=250)
    ink = "#172033"
    muted = "#5F6F82"
    border = "#D6E0EA"
    colours = ("#2F6FB3", "#177245", "#A06000", "#8A4FA3")

    canvas.create_text(
        18,
        16,
        text=title,
        anchor="w",
        fill=ink,
        font=("Segoe UI Semibold", 10),
    )
    if not x_values or not series:
        canvas.create_text(
            width / 2,
            height / 2,
            text="No result data available",
            fill=muted,
            font=("Segoe UI", 10),
        )
        return

    left = 58
    right = width - 18
    top = 42
    bottom = height - 38
    x_min = min(float(v) for v in x_values)
    x_max = max(float(v) for v in x_values)
    all_y = [
        float(value)
        for _, values in series
        for value in values
    ]
    y_min = min(all_y, default=0.0)
    y_max = max(all_y, default=0.0)
    if abs(y_max - y_min) < 1.0e-12:
        y_min -= 1.0
        y_max += 1.0
    pad = 0.08 * (y_max - y_min)
    y_min -= pad
    y_max += pad

    def sx(value: float) -> float:
        if abs(x_max - x_min) < 1.0e-12:
            return 0.5 * (left + right)
        return left + (float(value) - x_min) / (x_max - x_min) * (right - left)

    def sy(value: float) -> float:
        return bottom - (float(value) - y_min) / (y_max - y_min) * (bottom - top)

    zero_y = sy(0.0) if y_min <= 0.0 <= y_max else bottom
    canvas.create_line(left, zero_y, right, zero_y, fill=border)
    canvas.create_line(left, top, left, bottom, fill=border)
    for index, (name, values) in enumerate(series):
        points: list[float] = []
        for x, y in zip(x_values, values, strict=True):
            points.extend((sx(float(x)), sy(float(y))))
        colour = colours[index % len(colours)]
        if len(points) >= 4:
            canvas.create_line(*points, fill=colour, width=2, smooth=False)
        for point_index in range(0, len(points), 2):
            canvas.create_oval(
                points[point_index] - 2,
                points[point_index + 1] - 2,
                points[point_index] + 2,
                points[point_index + 1] + 2,
                fill=colour,
                outline="",
            )
        legend_x = left + index * 150
        canvas.create_line(legend_x, height - 14, legend_x + 22, height - 14, fill=colour, width=2)
        canvas.create_text(
            legend_x + 27,
            height - 14,
            text=name,
            anchor="w",
            fill=muted,
            font=("Segoe UI", 8),
        )

    canvas.create_text(left, top - 10, text=y_unit, anchor="w", fill=muted, font=("Segoe UI", 8))
    canvas.create_text(right, bottom + 18, text=f"{x_max:g}", anchor="e", fill=muted, font=("Segoe UI", 8))
    canvas.create_text(left, bottom + 18, text=f"{x_min:g}", anchor="w", fill=muted, font=("Segoe UI", 8))


def draw_reinforcement_section(
    canvas,
    *,
    bridge: BridgePreviewData,
    bar_count: int,
    bar_label: str,
    link_label: str,
) -> None:
    """Draw a schematic selected-girder reinforcement section for design review."""

    canvas.delete("all")
    width, height = _canvas_size(canvas, fallback_width=360, fallback_height=180)
    ink = "#172033"
    muted = "#5F6F82"
    primary = "#163B65"
    concrete = "#D9E2EC"
    steel = "#A73434"

    outline = bridge.girder_outline_m
    if not outline:
        return
    min_x = min(x for x, _ in outline)
    max_x = max(x for x, _ in outline)
    max_z = max(z for _, z in outline)
    section_width = max(max_x - min_x, 0.05)
    scale = min((width - 70) / section_width, (height - 55) / max(max_z, 0.05))
    centre_x = width / 2.0
    top_y = 25.0
    points: list[float] = []
    for x_m, z_m in outline:
        points.extend((centre_x + x_m * scale, top_y + z_m * scale))
    canvas.create_polygon(*points, fill=concrete, outline=primary, width=2)

    # Schematic closed link just inside the available envelope.
    left = centre_x + min_x * scale + 10
    right = centre_x + max_x * scale - 10
    bottom = top_y + max_z * scale - 10
    link_top = top_y + 10
    if right > left and bottom > link_top:
        canvas.create_rectangle(
            left,
            link_top,
            right,
            bottom,
            outline=steel,
            width=2,
        )

    bars_to_draw = min(max(int(bar_count), 2), 12)
    if bars_to_draw == 1:
        xs = [0.5 * (left + right)]
    else:
        xs = [
            left + 8 + index * max((right - left - 16) / (bars_to_draw - 1), 0.0)
            for index in range(bars_to_draw)
        ]
    for x in xs:
        canvas.create_oval(
            x - 4,
            bottom - 8,
            x + 4,
            bottom,
            fill=steel,
            outline=steel,
        )

    canvas.create_text(
        12,
        height - 14,
        text=f"Schematic cage · {bar_label} · {link_label}",
        anchor="w",
        fill=muted,
        font=("Segoe UI", 8),
    )
    canvas.create_text(
        12,
        12,
        text="SELECTED GIRDER REINFORCEMENT",
        anchor="w",
        fill=ink,
        font=("Segoe UI Semibold", 9),
    )
