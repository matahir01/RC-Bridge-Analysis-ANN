from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from rc_bridge.application.project_editor import (
    ProjectBasicFields,
    application_default_project,
)
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.core.models import DesignCode, SectionType, SupportSystem


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError(
            "The desktop interface requires Python with Tk support."
        ) from exc

    root = tk.Tk()
    root.title("RC Bridge Analysis")
    root.geometry("1180x760")
    root.minsize(980, 680)

    session = BridgeApplicationSession(application_default_project())
    variables: dict[str, tk.StringVar] = {}
    result_tree = None
    status_var = tk.StringVar(value="Ready")
    progress = None
    analysis_buttons: list[ttk.Button] = []

    def var(name: str, value: str = ""):
        item = tk.StringVar(value=value)
        variables[name] = item
        return item

    fields_frame = ttk.LabelFrame(root, text="Project definition", padding=12)
    fields_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

    right = ttk.Frame(root, padding=(0, 10, 10, 10))
    right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    rows = [
        ("Project name", "name"),
        ("Span lengths m (comma separated)", "spans"),
        ("Deck width (m)", "deck_width"),
        ("Carriageway width (m)", "carriageway_width"),
        ("Carriageway offset (m)", "carriageway_offset"),
        ("Girder count", "girder_count"),
        ("Girder spacing (m)", "girder_spacing"),
        ("Concrete fck (MPa)", "fck"),
        ("Steel fyk (MPa)", "fyk"),
        ("Rectangular width (m)", "rect_width"),
        ("Rectangular depth (m)", "rect_depth"),
        ("T flange width (m)", "t_flange_width"),
        ("T flange thickness (m)", "t_flange_thickness"),
        ("T web width (m)", "t_web_width"),
        ("T total depth (m)", "t_total_depth"),
        ("I top flange width (m)", "i_top_width"),
        ("I top flange thickness (m)", "i_top_thickness"),
        ("I web width (m)", "i_web_width"),
        ("I web depth (m)", "i_web_depth"),
        ("I bottom flange width (m)", "i_bottom_width"),
        ("I bottom flange thickness (m)", "i_bottom_thickness"),
    ]
    for row, (label, key) in enumerate(rows):
        ttk.Label(fields_frame, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=2,
        )
        ttk.Entry(fields_frame, textvariable=var(key), width=24).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=2,
        )

    selector_row = len(rows)
    ttk.Label(fields_frame, text="Design code").grid(
        row=selector_row,
        column=0,
        sticky="w",
        pady=2,
    )
    ttk.Combobox(
        fields_frame,
        textvariable=var("design_code"),
        values=[item.value for item in DesignCode],
        state="readonly",
        width=21,
    ).grid(row=selector_row, column=1, sticky="ew", pady=2)

    ttk.Label(fields_frame, text="Support system").grid(
        row=selector_row + 1,
        column=0,
        sticky="w",
        pady=2,
    )
    ttk.Combobox(
        fields_frame,
        textvariable=var("support_system"),
        values=[item.value for item in SupportSystem],
        state="readonly",
        width=21,
    ).grid(row=selector_row + 1, column=1, sticky="ew", pady=2)

    ttk.Label(fields_frame, text="Section type").grid(
        row=selector_row + 2,
        column=0,
        sticky="w",
        pady=2,
    )
    ttk.Combobox(
        fields_frame,
        textvariable=var("section_type"),
        values=[item.value for item in SectionType],
        state="readonly",
        width=21,
    ).grid(row=selector_row + 2, column=1, sticky="ew", pady=2)

    analysis_frame = ttk.LabelFrame(right, text="Native LM1 analysis", padding=12)
    analysis_frame.pack(fill=tk.X)

    ttk.Label(analysis_frame, text="Grid spacing (m)").grid(row=0, column=0, sticky="w")
    ttk.Entry(
        analysis_frame,
        textvariable=var("grid_spacing", "1.0"),
        width=10,
    ).grid(row=0, column=1, padx=(4, 14))
    ttk.Label(analysis_frame, text="Traffic step (m)").grid(row=0, column=2, sticky="w")
    ttk.Entry(
        analysis_frame,
        textvariable=var("traffic_step", "0.5"),
        width=10,
    ).grid(row=0, column=3, padx=(4, 14))
    ttk.Label(analysis_frame, text="Max exhaustive tandem cases").grid(
        row=0,
        column=4,
        sticky="w",
    )
    ttk.Entry(
        analysis_frame,
        textvariable=var("max_tandem", "5000"),
        width=10,
    ).grid(row=0, column=5, padx=(4, 0))

    button_frame = ttk.Frame(right, padding=(0, 10))
    button_frame.pack(fill=tk.X)

    result_frame = ttk.LabelFrame(right, text="Governing native LM1 effects", padding=8)
    result_frame.pack(fill=tk.BOTH, expand=True)

    columns = ("girder", "y", "moment", "m_case", "shear", "v_case", "torsion", "t_case")
    result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=18)
    headings = {
        "girder": "Girder",
        "y": "y (m)",
        "moment": "|M| kNm",
        "m_case": "M case",
        "shear": "|V| kN",
        "v_case": "V case",
        "torsion": "|T| kNm",
        "t_case": "T case",
    }
    widths = {
        "girder": 60,
        "y": 70,
        "moment": 95,
        "m_case": 70,
        "shear": 90,
        "v_case": 70,
        "torsion": 90,
        "t_case": 70,
    }
    for key in columns:
        result_tree.heading(key, text=headings[key])
        result_tree.column(key, width=widths[key], anchor=tk.CENTER)
    result_tree.pack(fill=tk.BOTH, expand=True)

    footer = ttk.Frame(right, padding=(0, 8))
    footer.pack(fill=tk.X)
    progress = ttk.Progressbar(footer, mode="indeterminate", length=180)
    progress.pack(side=tk.RIGHT)
    ttk.Label(footer, textvariable=status_var).pack(side=tk.LEFT)

    def optional_float(key: str) -> float | None:
        value = variables[key].get().strip()
        return None if not value else float(value)

    def project_from_form():
        spans = tuple(
            float(value.strip())
            for value in variables["spans"].get().split(",")
            if value.strip()
        )
        fields = ProjectBasicFields(
            name=variables["name"].get(),
            design_code=DesignCode(variables["design_code"].get()),
            support_system=SupportSystem(variables["support_system"].get()),
            span_lengths_m=spans,
            deck_width_m=float(variables["deck_width"].get()),
            carriageway_width_m=float(variables["carriageway_width"].get()),
            carriageway_offset_m=float(variables["carriageway_offset"].get()),
            girder_count=int(variables["girder_count"].get()),
            girder_spacing_m=float(variables["girder_spacing"].get()),
            section_type=SectionType(variables["section_type"].get()),
            fck_mpa=float(variables["fck"].get()),
            fyk_mpa=float(variables["fyk"].get()),
            rectangular_width_m=optional_float("rect_width"),
            rectangular_depth_m=optional_float("rect_depth"),
            t_flange_width_m=optional_float("t_flange_width"),
            t_flange_thickness_m=optional_float("t_flange_thickness"),
            t_web_width_m=optional_float("t_web_width"),
            t_total_depth_m=optional_float("t_total_depth"),
            i_top_flange_width_m=optional_float("i_top_width"),
            i_top_flange_thickness_m=optional_float("i_top_thickness"),
            i_web_width_m=optional_float("i_web_width"),
            i_web_depth_m=optional_float("i_web_depth"),
            i_bottom_flange_width_m=optional_float("i_bottom_width"),
            i_bottom_flange_thickness_m=optional_float("i_bottom_thickness"),
        )
        return fields.apply(session.project)

    def set_optional(key: str, value: float | None) -> None:
        variables[key].set("" if value is None else f"{value:g}")

    def populate(project) -> None:
        fields = ProjectBasicFields.from_project(project)
        variables["name"].set(fields.name)
        variables["design_code"].set(fields.design_code.value)
        variables["support_system"].set(fields.support_system.value)
        variables["spans"].set(", ".join(f"{value:g}" for value in fields.span_lengths_m))
        variables["deck_width"].set(f"{fields.deck_width_m:g}")
        variables["carriageway_width"].set(f"{fields.carriageway_width_m:g}")
        variables["carriageway_offset"].set(f"{fields.carriageway_offset_m:g}")
        variables["girder_count"].set(str(fields.girder_count))
        variables["girder_spacing"].set(f"{fields.girder_spacing_m:g}")
        variables["section_type"].set(fields.section_type.value)
        variables["fck"].set(f"{fields.fck_mpa:g}")
        variables["fyk"].set(f"{fields.fyk_mpa:g}")
        set_optional("rect_width", fields.rectangular_width_m)
        set_optional("rect_depth", fields.rectangular_depth_m)
        set_optional("t_flange_width", fields.t_flange_width_m)
        set_optional("t_flange_thickness", fields.t_flange_thickness_m)
        set_optional("t_web_width", fields.t_web_width_m)
        set_optional("t_total_depth", fields.t_total_depth_m)
        set_optional("i_top_width", fields.i_top_flange_width_m)
        set_optional("i_top_thickness", fields.i_top_flange_thickness_m)
        set_optional("i_web_width", fields.i_web_width_m)
        set_optional("i_web_depth", fields.i_web_depth_m)
        set_optional("i_bottom_width", fields.i_bottom_flange_width_m)
        set_optional("i_bottom_thickness", fields.i_bottom_flange_thickness_m)

    def clear_results() -> None:
        for item in result_tree.get_children():
            result_tree.delete(item)

    def show_result(result) -> None:
        clear_results()
        for girder in result.girders:
            result_tree.insert(
                "",
                tk.END,
                values=(
                    girder.girder_index,
                    f"{girder.y_m:.3f}",
                    f"{girder.moment_knm.value:.3f}",
                    girder.moment_knm.case_id,
                    f"{girder.shear_kn.value:.3f}",
                    girder.shear_kn.case_id,
                    f"{girder.torsion_knm.value:.3f}",
                    girder.torsion_knm.case_id,
                ),
            )
        status_var.set(
            f"Completed {result.evaluated_case_count} LM1 cases; "
            f"{len(result.governing_case_ids)} governing verification cases."
        )

    def set_busy(busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in analysis_buttons:
            button.configure(state=state)
        if busy:
            progress.start(12)
        else:
            progress.stop()

    def fail(message: str) -> None:
        set_busy(False)
        status_var.set("Analysis failed")
        messagebox.showerror("RC Bridge Analysis", message)

    def run_analysis() -> None:
        try:
            project = project_from_form()
            session.replace_project(project)
            grid_spacing = float(variables["grid_spacing"].get())
            traffic_step = float(variables["traffic_step"].get())
            max_tandem = int(variables["max_tandem"].get())
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Project input", str(exc))
            return

        set_busy(True)
        status_var.set("Running native full-width LM1 analysis...")

        def worker() -> None:
            try:
                result = session.run_native_lm1(
                    grid_spacing_m=grid_spacing,
                    longitudinal_step_m=traffic_step,
                    max_exhaustive_tandem_combinations=max_tandem,
                )
            except Exception as exc:  # desktop boundary: show validated engine error
                message = str(exc)
                root.after(0, lambda: fail(message))
                return

            def complete() -> None:
                set_busy(False)
                show_result(result)

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def new_project() -> None:
        session.project = application_default_project()
        session.project_path = None
        session.last_lm1_search = None
        populate(session.project)
        clear_results()
        status_var.set("New project")

    def open_project() -> None:
        path = filedialog.askopenfilename(
            title="Open RC bridge project",
            filetypes=(("RC bridge project", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            opened = BridgeApplicationSession.open(path)
        except Exception as exc:
            messagebox.showerror("Open project", str(exc))
            return
        session.project = opened.project
        session.project_path = opened.project_path
        session.last_lm1_search = None
        populate(session.project)
        clear_results()
        status_var.set(f"Opened {Path(path).name}")

    def save_as() -> None:
        try:
            session.replace_project(project_from_form())
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Project input", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="Save RC bridge project",
            defaultextension=".json",
            filetypes=(("RC bridge project", "*.json"),),
        )
        if not path:
            return
        session.save(path)
        status_var.set(f"Saved {Path(path).name}")

    def save_current() -> None:
        if session.project_path is None:
            save_as()
            return
        try:
            session.replace_project(project_from_form())
            path = session.save()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Save project", str(exc))
            return
        status_var.set(f"Saved {path.name}")

    def save_report() -> None:
        if session.last_lm1_search is None:
            messagebox.showinfo("Calculation report", "Run native LM1 analysis first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save calculation report",
            defaultextension=".html",
            filetypes=(("HTML report", "*.html"),),
        )
        if not path:
            return
        try:
            report = session.write_last_lm1_report(path)
        except Exception as exc:
            messagebox.showerror("Calculation report", str(exc))
            return
        status_var.set(f"Report saved: {report.name}")
        webbrowser.open(report.resolve().as_uri())

    def export_verification() -> None:
        if session.last_lm1_search is None:
            messagebox.showinfo("Verification export", "Run native LM1 analysis first.")
            return
        directory = filedialog.askdirectory(title="Choose verification export folder")
        if not directory:
            return
        try:
            packages = session.export_last_lm1_verification(
                directory,
                base_name="application_lm1",
            )
        except Exception as exc:
            messagebox.showerror("Verification export", str(exc))
            return
        status_var.set(f"Exported {len(packages)} governing MIDAS/STAAD case packages.")

    run_button = ttk.Button(button_frame, text="Run native LM1", command=run_analysis)
    run_button.pack(side=tk.LEFT)
    report_button = ttk.Button(button_frame, text="Save report", command=save_report)
    report_button.pack(side=tk.LEFT, padx=8)
    export_button = ttk.Button(
        button_frame,
        text="Export MIDAS / STAAD",
        command=export_verification,
    )
    export_button.pack(side=tk.LEFT)
    analysis_buttons.extend((run_button, report_button, export_button))

    menu = tk.Menu(root)
    file_menu = tk.Menu(menu, tearoff=False)
    file_menu.add_command(label="New", command=new_project)
    file_menu.add_command(label="Open...", command=open_project)
    file_menu.add_separator()
    file_menu.add_command(label="Save", command=save_current)
    file_menu.add_command(label="Save As...", command=save_as)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=root.destroy)
    menu.add_cascade(label="File", menu=file_menu)
    root.configure(menu=menu)

    populate(session.project)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
