from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RibbonField:
    key: str
    label: str
    kind: str = "entry"
    values: tuple[str, ...] = ()
    width: int = 24


@dataclass(frozen=True)
class RibbonSection:
    title: str
    fields: tuple[RibbonField, ...]


def _ribbon_field_keys(
    sections: tuple[RibbonSection, ...],
) -> tuple[set[str], set[str]]:
    string_keys = {
        field.key
        for section in sections
        for field in section.fields
        if field.kind != "bool"
    }
    bool_keys = {
        field.key
        for section in sections
        for field in section.fields
        if field.kind == "bool"
    }
    return string_keys, bool_keys


def _capture_shared_values(
    string_vars: dict[str, Any],
    bool_vars: dict[str, Any],
    *,
    string_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], dict[str, bool]]:
    return (
        {key: string_vars[key].get() for key in string_keys},
        {key: bool(bool_vars[key].get()) for key in bool_keys},
    )


def _restore_shared_values(
    string_vars: dict[str, Any],
    bool_vars: dict[str, Any],
    *,
    string_values: dict[str, str],
    bool_values: dict[str, bool],
) -> None:
    for key, value in string_values.items():
        string_vars[key].set(value)
    for key, value in bool_values.items():
        bool_vars[key].set(value)


def open_scrollable_input_dialog(
    *,
    parent: Any,
    tk: Any,
    ttk: Any,
    title: str,
    sections: tuple[RibbonSection, ...],
    string_vars: dict[str, Any],
    bool_vars: dict[str, Any],
    apply_callback: Callable[[], bool | None],
    width: int = 700,
    height: int = 680,
) -> Any:
    """Open a modal, vertically scrollable transactional input editor.

    Dialog controls bind to temporary Tk variables. Shared application form variables
    are updated only immediately before Apply validation; failed validation restores
    the prior shared values, while Cancel/Escape/window-close discard dialog edits.
    """

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry(f"{width}x{height}")
    dialog.minsize(min(width, 560), min(height, 480))
    dialog.transient(parent)
    dialog.grab_set()

    string_keys, bool_keys = _ribbon_field_keys(sections)
    missing_strings = sorted(string_keys - string_vars.keys())
    missing_bools = sorted(bool_keys - bool_vars.keys())
    if missing_strings or missing_bools:
        dialog.grab_release()
        dialog.destroy()
        missing = ", ".join((*missing_strings, *missing_bools))
        raise KeyError(f"Ribbon dialog field variable(s) not found: {missing}")

    dialog_string_vars = {
        key: tk.StringVar(value=string_vars[key].get())
        for key in string_keys
    }
    dialog_bool_vars = {
        key: tk.BooleanVar(value=bool(bool_vars[key].get()))
        for key in bool_keys
    }

    outer = ttk.Frame(dialog)
    outer.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(
        outer,
        highlightthickness=0,
        background="#FFFFFF",
    )
    scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    content = ttk.Frame(canvas, style="Surface.TFrame", padding=(18, 14))
    window_id = canvas.create_window((0, 0), window=content, anchor="nw")

    def sync_scroll_region(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def sync_width(event) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    content.bind("<Configure>", sync_scroll_region)
    canvas.bind("<Configure>", sync_width)

    def on_mousewheel(event) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-delta / 120), "units")

    canvas.bind_all("<MouseWheel>", on_mousewheel)

    header = ttk.Frame(content, style="Surface.TFrame")
    header.pack(fill=tk.X, pady=(0, 12))
    ttk.Label(
        header,
        text=title,
        style="HeaderTitle.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        header,
        text=(
            "Edit the required engineering inputs here. Apply validates and commits "
            "the values to the project; Cancel closes this editor without applying."
        ),
        style="SurfaceMuted.TLabel",
        wraplength=620,
        justify="left",
    ).pack(anchor="w", pady=(3, 0))

    for section in sections:
        frame = ttk.LabelFrame(
            content,
            text=section.title,
            style="Card.TLabelframe",
            padding=12,
        )
        frame.pack(fill=tk.X, pady=(0, 10))
        frame.columnconfigure(1, weight=1)

        for row, field in enumerate(section.fields):
            ttk.Label(frame, text=field.label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=4,
            )
            if field.kind == "bool":
                variable = dialog_bool_vars[field.key]
                ttk.Checkbutton(frame, variable=variable).grid(
                    row=row,
                    column=1,
                    sticky="w",
                    pady=4,
                )
            elif field.kind == "choice":
                variable = dialog_string_vars[field.key]
                ttk.Combobox(
                    frame,
                    textvariable=variable,
                    values=field.values,
                    state="readonly",
                    width=field.width,
                ).grid(row=row, column=1, sticky="ew", pady=4)
            else:
                variable = dialog_string_vars[field.key]
                ttk.Entry(
                    frame,
                    textvariable=variable,
                    width=field.width,
                ).grid(row=row, column=1, sticky="ew", pady=4)

    footer = ttk.Frame(content, style="Surface.TFrame")
    footer.pack(fill=tk.X, pady=(2, 8))

    def close_dialog() -> None:
        canvas.unbind_all("<MouseWheel>")
        dialog.grab_release()
        dialog.destroy()

    def apply_and_close() -> None:
        shared_strings_before, shared_bools_before = _capture_shared_values(
            string_vars,
            bool_vars,
            string_keys=string_keys,
            bool_keys=bool_keys,
        )
        for key, variable in dialog_string_vars.items():
            string_vars[key].set(variable.get())
        for key, variable in dialog_bool_vars.items():
            bool_vars[key].set(bool(variable.get()))

        try:
            applied = apply_callback()
        except Exception:
            _restore_shared_values(
                string_vars,
                bool_vars,
                string_values=shared_strings_before,
                bool_values=shared_bools_before,
            )
            raise

        if applied is False:
            _restore_shared_values(
                string_vars,
                bool_vars,
                string_values=shared_strings_before,
                bool_values=shared_bools_before,
            )
            return
        close_dialog()

    ttk.Button(
        footer,
        text="Cancel",
        style="Secondary.TButton",
        command=close_dialog,
    ).pack(side=tk.RIGHT)
    ttk.Button(
        footer,
        text="Apply",
        style="Primary.TButton",
        command=apply_and_close,
    ).pack(side=tk.RIGHT, padx=(0, 8))

    dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    dialog.bind("<Escape>", lambda _event: close_dialog())
    return dialog
