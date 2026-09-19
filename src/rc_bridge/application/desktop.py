from __future__ import annotations

import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from rc_bridge.application.preferences import (
    AnalysisApplicationSettings,
    ApplicationPreferences,
    EurocodeApplicationBasis,
    UnitDisplay,
)
from rc_bridge.application.project_editor import (
    ProjectBasicFields,
    application_default_project,
)
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.analysis.physical_sections import composite_section_identity
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
    root.title("RC Bridge Analysis & Design")
    root.geometry("1360x860")
    root.minsize(1120, 720)

    session = BridgeApplicationSession(application_default_project())
    displayed_unit = session.preferences.units
    string_vars: dict[str, tk.StringVar] = {}
    bool_vars: dict[str, tk.BooleanVar] = {}
    status_var = tk.StringVar(value="Ready")
    length_unit_var = tk.StringVar(value=displayed_unit.length_label)
    analysis_buttons: list[ttk.Button] = []

    def svar(name: str, value: str = "") -> tk.StringVar:
        item = tk.StringVar(value=value)
        string_vars[name] = item
        return item

    def bvar(name: str, value: bool = False) -> tk.BooleanVar:
        item = tk.BooleanVar(value=value)
        bool_vars[name] = item
        return item

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

    project_tab = ttk.Frame(notebook, padding=12)
    basis_tab = ttk.Frame(notebook, padding=12)
    analysis_tab = ttk.Frame(notebook, padding=12)
    design_tab = ttk.Frame(notebook, padding=12)
    verification_tab = ttk.Frame(notebook, padding=12)
    research_tab = ttk.Frame(notebook, padding=12)

    notebook.add(project_tab, text="Project")
    notebook.add(basis_tab, text="Design basis")
    notebook.add(analysis_tab, text="Analysis")
    notebook.add(design_tab, text="Design & checks")
    notebook.add(verification_tab, text="Verification")
    notebook.add(research_tab, text="Research")

    footer = ttk.Frame(root, padding=(10, 4, 10, 8))
    footer.pack(fill=tk.X)
    progress = ttk.Progressbar(footer, mode="determinate", length=220, maximum=100.0)
    progress.pack(side=tk.RIGHT)
    cancel_analysis_button = ttk.Button(footer, text="Cancel analysis", state=tk.DISABLED)
    cancel_analysis_button.pack(side=tk.RIGHT, padx=(0, 8))
    ttk.Label(footer, textvariable=status_var).pack(side=tk.LEFT)
    analysis_cancel_event = threading.Event()

    def add_entry(
        parent,
        *,
        row: int,
        label: str,
        key: str,
        width: int = 20,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=3,
        )
        ttk.Entry(parent, textvariable=svar(key), width=width).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=3,
        )

    # ------------------------------------------------------------------
    # Project tab
    # ------------------------------------------------------------------
    project_tab.columnconfigure(0, weight=1)
    project_tab.columnconfigure(1, weight=1)
    project_tab.columnconfigure(2, weight=1)

    layout_frame = ttk.LabelFrame(project_tab, text="Bridge layout", padding=10)
    layout_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    material_frame = ttk.LabelFrame(project_tab, text="Materials & deck", padding=10)
    material_frame.grid(row=0, column=1, sticky="nsew", padx=6)
    profile_frame = ttk.LabelFrame(project_tab, text="Precast girder section", padding=10)
    profile_frame.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

    add_entry(layout_frame, row=0, label="Project name", key="name", width=28)

    ttk.Label(layout_frame, text="Design code").grid(
        row=1, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        layout_frame,
        textvariable=svar("design_code"),
        values=[item.value for item in DesignCode],
        state="readonly",
        width=25,
    ).grid(row=1, column=1, sticky="ew", pady=3)

    ttk.Label(layout_frame, text="Support system").grid(
        row=2, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        layout_frame,
        textvariable=svar("support_system"),
        values=[item.value for item in SupportSystem],
        state="readonly",
        width=25,
    ).grid(row=2, column=1, sticky="ew", pady=3)

    add_entry(
        layout_frame,
        row=3,
        label="Span lengths (comma separated)",
        key="spans",
        width=28,
    )
    add_entry(layout_frame, row=4, label="Deck width", key="deck_width")
    add_entry(
        layout_frame,
        row=5,
        label="Carriageway width",
        key="carriageway_width",
    )
    add_entry(
        layout_frame,
        row=6,
        label="Carriageway offset",
        key="carriageway_offset",
    )
    add_entry(layout_frame, row=7, label="Girder count", key="girder_count")
    add_entry(layout_frame, row=8, label="Girder spacing", key="girder_spacing")

    ttk.Label(layout_frame, text="Current length input unit").grid(
        row=9, column=0, sticky="w", padx=(0, 8), pady=(8, 3)
    )
    ttk.Label(layout_frame, textvariable=length_unit_var).grid(
        row=9, column=1, sticky="w", pady=(8, 3)
    )

    add_entry(material_frame, row=0, label="Concrete fck (MPa)", key="fck")
    add_entry(material_frame, row=1, label="Steel fyk (MPa)", key="fyk")
    add_entry(
        material_frame,
        row=2,
        label="Concrete density (kN/m³)",
        key="concrete_density",
    )
    add_entry(
        material_frame,
        row=3,
        label="Elastic modulus (MPa, optional)",
        key="elastic_modulus",
    )
    add_entry(
        material_frame,
        row=4,
        label="Precast false slab depth",
        key="false_slab_depth",
    )
    add_entry(
        material_frame,
        row=5,
        label="In-situ slab depth",
        key="in_situ_depth",
    )
    ttk.Checkbutton(
        material_frame,
        text="False slab participates in composite stiffness",
        variable=bvar("false_slab_composite"),
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 3))
    ttk.Checkbutton(
        material_frame,
        text="In-situ slab participates in composite stiffness",
        variable=bvar("in_situ_composite", True),
    ).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)

    ttk.Label(profile_frame, text="Section type").grid(
        row=0, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        profile_frame,
        textvariable=svar("section_type"),
        values=[item.value for item in SectionType],
        state="readonly",
        width=24,
    ).grid(row=0, column=1, sticky="ew", pady=3)

    add_entry(profile_frame, row=1, label="Rectangular width", key="rect_width")
    add_entry(profile_frame, row=2, label="Rectangular depth", key="rect_depth")
    ttk.Separator(profile_frame).grid(
        row=3, column=0, columnspan=2, sticky="ew", pady=7
    )
    add_entry(profile_frame, row=4, label="T flange width", key="t_flange_width")
    add_entry(
        profile_frame,
        row=5,
        label="T flange thickness",
        key="t_flange_thickness",
    )
    add_entry(profile_frame, row=6, label="T web width", key="t_web_width")
    add_entry(profile_frame, row=7, label="T total depth", key="t_total_depth")
    ttk.Separator(profile_frame).grid(
        row=8, column=0, columnspan=2, sticky="ew", pady=7
    )
    add_entry(profile_frame, row=9, label="I top flange width", key="i_top_width")
    add_entry(
        profile_frame,
        row=10,
        label="I top flange thickness",
        key="i_top_thickness",
    )
    add_entry(profile_frame, row=11, label="I web width", key="i_web_width")
    add_entry(profile_frame, row=12, label="I web depth", key="i_web_depth")
    add_entry(
        profile_frame,
        row=13,
        label="I bottom flange width",
        key="i_bottom_width",
    )
    add_entry(
        profile_frame,
        row=14,
        label="I bottom flange thickness",
        key="i_bottom_thickness",
    )

    composite_identity_var = tk.StringVar(value="")
    ttk.Separator(profile_frame).grid(
        row=15, column=0, columnspan=2, sticky="ew", pady=7
    )
    ttk.Label(
        profile_frame,
        textvariable=composite_identity_var,
        wraplength=360,
        justify=tk.LEFT,
    ).grid(row=16, column=0, columnspan=2, sticky="w", pady=(4, 0))

    project_actions = ttk.Frame(project_tab, padding=(0, 12, 0, 0))
    project_actions.grid(row=1, column=0, columnspan=3, sticky="ew")
    guidance_var = tk.StringVar(value="")
    ttk.Label(
        project_actions,
        textvariable=guidance_var,
        wraplength=950,
        justify=tk.LEFT,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    project_button_frame = ttk.Frame(project_actions)
    project_button_frame.pack(side=tk.RIGHT)
    apply_project_button = ttk.Button(project_button_frame, text="Apply project")
    apply_project_button.pack(side=tk.LEFT, padx=4)
    revert_project_button = ttk.Button(project_button_frame, text="Revert")
    revert_project_button.pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Design-basis tab
    # ------------------------------------------------------------------
    basis_tab.columnconfigure(0, weight=1)
    basis_tab.columnconfigure(1, weight=1)

    units_frame = ttk.LabelFrame(basis_tab, text="Application units", padding=12)
    units_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    ttk.Label(units_frame, text="Length display/input mode").grid(
        row=0, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        units_frame,
        textvariable=svar("units"),
        values=[item.value for item in UnitDisplay],
        state="readonly",
        width=28,
    ).grid(row=0, column=1, sticky="ew", pady=3)
    ttk.Label(
        units_frame,
        text=(
            "The calculation engine always stores SI metres, kN and MPa. "
            "This setting changes only the editable/displayed length convention."
        ),
        wraplength=500,
        justify=tk.LEFT,
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    ec_frame = ttk.LabelFrame(basis_tab, text="Eurocode / National Annex basis", padding=12)
    ec_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    add_entry(
        ec_frame,
        row=0,
        label="γG unfavourable",
        key="gamma_g_unfavourable",
    )
    add_entry(
        ec_frame,
        row=1,
        label="γG favourable",
        key="gamma_g_favourable",
    )
    add_entry(ec_frame, row=2, label="γQ traffic", key="gamma_q_traffic")
    add_entry(ec_frame, row=3, label="ψ1 traffic", key="psi1_traffic")
    add_entry(ec_frame, row=4, label="ψ2 traffic", key="psi2_traffic")
    add_entry(ec_frame, row=5, label="Crack limit (mm)", key="crack_limit")
    add_entry(
        ec_frame,
        row=6,
        label="Deflection limit denominator (L/...)",
        key="deflection_ratio",
    )

    search_frame = ttk.LabelFrame(basis_tab, text="Native traffic-search settings", padding=12)
    search_frame.grid(
        row=1,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(12, 0),
    )
    add_entry(search_frame, row=0, label="Maximum grid spacing", key="grid_spacing")
    add_entry(search_frame, row=1, label="Traffic step", key="traffic_step")
    add_entry(
        search_frame,
        row=2,
        label="Max exhaustive tandem combinations",
        key="max_tandem",
    )
    ttk.Label(
        search_frame,
        text=(
            "These values control the native LM1 search only. "
            "ULS/SLS factors are kept separate and are not applied to the "
            "characteristic traffic search."
        ),
        wraplength=850,
        justify=tk.LEFT,
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    basis_buttons = ttk.Frame(basis_tab, padding=(0, 12, 0, 0))
    basis_buttons.grid(row=2, column=0, columnspan=2, sticky="e")
    apply_basis_button = ttk.Button(basis_buttons, text="Apply design basis")
    apply_basis_button.pack(side=tk.LEFT, padx=4)
    revert_basis_button = ttk.Button(basis_buttons, text="Revert")
    revert_basis_button.pack(side=tk.LEFT, padx=4)

    # ------------------------------------------------------------------
    # Analysis tab
    # ------------------------------------------------------------------
    analysis_header = ttk.Frame(analysis_tab)
    analysis_header.pack(fill=tk.X)
    ttk.Label(
        analysis_header,
        text=(
            "Native full-width traffic analysis uses the physical bridge model "
            "and keeps each governing M/V/T/deflection case traceable."
        ),
        wraplength=900,
        justify=tk.LEFT,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    run_button = ttk.Button(analysis_header, text="Run native LM1")
    run_button.pack(side=tk.RIGHT)
    analysis_buttons.append(run_button)

    search_status_var = tk.StringVar(value="No native LM1 analysis has been run.")
    ttk.Label(
        analysis_tab,
        textvariable=search_status_var,
        justify=tk.LEFT,
        wraplength=1100,
    ).pack(fill=tk.X, pady=(8, 6))

    effect_frame = ttk.LabelFrame(
        analysis_tab,
        text="Governing native LM1 girder effects",
        padding=8,
    )
    effect_frame.pack(fill=tk.BOTH, expand=True)

    effect_columns = (
        "girder",
        "y",
        "moment",
        "m_case",
        "shear",
        "v_case",
        "torsion",
        "t_case",
    )
    effect_tree = ttk.Treeview(
        effect_frame,
        columns=effect_columns,
        show="headings",
        height=11,
    )
    effect_headings = {
        "girder": "Girder",
        "y": "y (m)",
        "moment": "|M| kNm",
        "m_case": "M case",
        "shear": "|V| kN",
        "v_case": "V case",
        "torsion": "|T| kNm",
        "t_case": "T case",
    }
    for key in effect_columns:
        effect_tree.heading(key, text=effect_headings[key])
        effect_tree.column(key, width=95, anchor=tk.CENTER)
    effect_tree.pack(fill=tk.BOTH, expand=True)

    deflection_frame = ttk.LabelFrame(
        analysis_tab,
        text="Traffic deflection trace",
        padding=8,
    )
    deflection_frame.pack(fill=tk.X, pady=(8, 0))
    deflection_tree = ttk.Treeview(
        deflection_frame,
        columns=("girder", "value", "position", "case"),
        show="headings",
        height=5,
    )
    for key, title in (
        ("girder", "Girder"),
        ("value", "|DZ| mm"),
        ("position", "x (m)"),
        ("case", "Case"),
    ):
        deflection_tree.heading(key, text=title)
        deflection_tree.column(key, width=120, anchor=tk.CENTER)
    deflection_tree.pack(fill=tk.X)

    # ------------------------------------------------------------------
    # Design/checks tab
    # ------------------------------------------------------------------
    ttk.Label(
        design_tab,
        text=(
            "This dashboard exposes what the deterministic engine can do and "
            "keeps independent-validation gates visible. Implemented design "
            "modules are not relabelled as production-certified before Stage 7."
        ),
        wraplength=1080,
        justify=tk.LEFT,
    ).pack(fill=tk.X)

    capability_tree = ttk.Treeview(
        design_tab,
        columns=("capability", "state", "detail"),
        show="headings",
        height=18,
    )
    capability_tree.heading("capability", text="Capability")
    capability_tree.heading("state", text="State")
    capability_tree.heading("detail", text="Engineering boundary")
    capability_tree.column("capability", width=310, anchor=tk.W)
    capability_tree.column("state", width=160, anchor=tk.CENTER)
    capability_tree.column("detail", width=720, anchor=tk.W)
    capability_tree.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

    refresh_dashboard_button = ttk.Button(design_tab, text="Refresh dashboard")
    refresh_dashboard_button.pack(anchor=tk.E, pady=(8, 0))

    # ------------------------------------------------------------------
    # Verification tab
    # ------------------------------------------------------------------
    verification_text = tk.Text(
        verification_tab,
        height=9,
        wrap="word",
        state=tk.DISABLED,
    )
    verification_text.pack(fill=tk.X)

    verification_buttons = ttk.Frame(verification_tab, padding=(0, 12, 0, 0))
    verification_buttons.pack(fill=tk.X)
    html_button = ttk.Button(verification_buttons, text="Save HTML report")
    html_button.pack(side=tk.LEFT, padx=(0, 6))
    pdf_button = ttk.Button(verification_buttons, text="Save PDF report")
    pdf_button.pack(side=tk.LEFT, padx=6)
    print_button = ttk.Button(verification_buttons, text="Print / preview report")
    print_button.pack(side=tk.LEFT, padx=6)
    export_button = ttk.Button(
        verification_buttons,
        text="Export governing MIDAS / STAAD packages",
    )
    export_button.pack(side=tk.LEFT, padx=6)
    analysis_buttons.extend((html_button, pdf_button, print_button, export_button))

    package_tree = ttk.Treeview(
        verification_tab,
        columns=("case", "purpose"),
        show="headings",
        height=10,
    )
    package_tree.heading("case", text="Governing case")
    package_tree.heading("purpose", text="Verification purpose")
    package_tree.column("case", width=150, anchor=tk.CENTER)
    package_tree.column("purpose", width=850, anchor=tk.W)
    package_tree.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

    # ------------------------------------------------------------------
    # Research tab
    # ------------------------------------------------------------------
    research_text = tk.Text(research_tab, wrap="word", state=tk.DISABLED)
    research_text.pack(fill=tk.BOTH, expand=True)
    research_actions = ttk.Frame(research_tab, padding=(0, 10, 0, 0))
    research_actions.pack(fill=tk.X)
    dataset_button = ttk.Button(
        research_actions,
        text="Generate ANN ground truth",
        state=tk.DISABLED,
    )
    dataset_button.pack(side=tk.LEFT, padx=(0, 6))
    ann_button = ttk.Button(
        research_actions,
        text="Train ANN surrogate",
        state=tk.DISABLED,
    )
    ann_button.pack(side=tk.LEFT, padx=6)
    rbdo_button = ttk.Button(
        research_actions,
        text="Run reliability / RBDO",
        state=tk.DISABLED,
    )
    rbdo_button.pack(side=tk.LEFT, padx=6)

    def _set_text(widget, value: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.configure(state=tk.DISABLED)

    def optional_float(key: str) -> float | None:
        value = string_vars[key].get().strip()
        return None if not value else float(value)

    def optional_length_m(key: str) -> float | None:
        value = string_vars[key].get().strip()
        if not value:
            return None
        return displayed_unit.to_metres(float(value))

    def length_m(key: str) -> float:
        return displayed_unit.to_metres(float(string_vars[key].get()))

    def project_from_form():
        spans = tuple(
            displayed_unit.to_metres(float(value.strip()))
            for value in string_vars["spans"].get().split(",")
            if value.strip()
        )
        fields = ProjectBasicFields(
            name=string_vars["name"].get(),
            design_code=DesignCode(string_vars["design_code"].get()),
            support_system=SupportSystem(string_vars["support_system"].get()),
            span_lengths_m=spans,
            deck_width_m=length_m("deck_width"),
            carriageway_width_m=length_m("carriageway_width"),
            carriageway_offset_m=length_m("carriageway_offset"),
            girder_count=int(string_vars["girder_count"].get()),
            girder_spacing_m=length_m("girder_spacing"),
            section_type=SectionType(string_vars["section_type"].get()),
            fck_mpa=float(string_vars["fck"].get()),
            fyk_mpa=float(string_vars["fyk"].get()),
            rectangular_width_m=optional_length_m("rect_width"),
            rectangular_depth_m=optional_length_m("rect_depth"),
            t_flange_width_m=optional_length_m("t_flange_width"),
            t_flange_thickness_m=optional_length_m("t_flange_thickness"),
            t_web_width_m=optional_length_m("t_web_width"),
            t_total_depth_m=optional_length_m("t_total_depth"),
            i_top_flange_width_m=optional_length_m("i_top_width"),
            i_top_flange_thickness_m=optional_length_m("i_top_thickness"),
            i_web_width_m=optional_length_m("i_web_width"),
            i_web_depth_m=optional_length_m("i_web_depth"),
            i_bottom_flange_width_m=optional_length_m("i_bottom_width"),
            i_bottom_flange_thickness_m=optional_length_m("i_bottom_thickness"),
            precast_false_slab_depth_m=length_m("false_slab_depth"),
            in_situ_slab_depth_m=length_m("in_situ_depth"),
            false_slab_composite_participation=bool_vars[
                "false_slab_composite"
            ].get(),
            in_situ_slab_composite_participation=bool_vars[
                "in_situ_composite"
            ].get(),
            concrete_density_kn_m3=float(string_vars["concrete_density"].get()),
            elastic_modulus_mpa=optional_float("elastic_modulus"),
        )
        return fields.apply(session.project)

    def preferences_from_form() -> ApplicationPreferences:
        new_units = UnitDisplay(string_vars["units"].get())
        basis = EurocodeApplicationBasis(
            gamma_g_unfavourable=float(
                string_vars["gamma_g_unfavourable"].get()
            ),
            gamma_g_favourable=float(string_vars["gamma_g_favourable"].get()),
            gamma_q_traffic=float(string_vars["gamma_q_traffic"].get()),
            psi1_traffic=float(string_vars["psi1_traffic"].get()),
            psi2_traffic=float(string_vars["psi2_traffic"].get()),
            crack_limit_mm=float(string_vars["crack_limit"].get()),
            deflection_limit_span_ratio=float(
                string_vars["deflection_ratio"].get()
            ),
        )
        analysis = AnalysisApplicationSettings(
            grid_spacing_m=displayed_unit.to_metres(
                float(string_vars["grid_spacing"].get())
            ),
            traffic_step_m=displayed_unit.to_metres(
                float(string_vars["traffic_step"].get())
            ),
            max_exhaustive_tandem_combinations=int(
                string_vars["max_tandem"].get()
            ),
        )
        return ApplicationPreferences(
            units=new_units,
            eurocode=basis,
            analysis=analysis,
        )

    def set_optional_length(key: str, value_m: float | None) -> None:
        if value_m is None:
            string_vars[key].set("")
        else:
            string_vars[key].set(f"{displayed_unit.from_metres(value_m):g}")

    def populate_project(project) -> None:
        fields = ProjectBasicFields.from_project(project)
        string_vars["name"].set(fields.name)
        string_vars["design_code"].set(fields.design_code.value)
        string_vars["support_system"].set(fields.support_system.value)
        string_vars["spans"].set(
            ", ".join(
                f"{displayed_unit.from_metres(value):g}"
                for value in fields.span_lengths_m
            )
        )
        string_vars["deck_width"].set(
            f"{displayed_unit.from_metres(fields.deck_width_m):g}"
        )
        string_vars["carriageway_width"].set(
            f"{displayed_unit.from_metres(fields.carriageway_width_m):g}"
        )
        string_vars["carriageway_offset"].set(
            f"{displayed_unit.from_metres(fields.carriageway_offset_m):g}"
        )
        string_vars["girder_count"].set(str(fields.girder_count))
        string_vars["girder_spacing"].set(
            f"{displayed_unit.from_metres(fields.girder_spacing_m):g}"
        )
        string_vars["section_type"].set(fields.section_type.value)
        string_vars["fck"].set(f"{fields.fck_mpa:g}")
        string_vars["fyk"].set(f"{fields.fyk_mpa:g}")
        string_vars["concrete_density"].set(
            f"{fields.concrete_density_kn_m3:g}"
        )
        string_vars["elastic_modulus"].set(
            ""
            if fields.elastic_modulus_mpa is None
            else f"{fields.elastic_modulus_mpa:g}"
        )
        string_vars["false_slab_depth"].set(
            f"{displayed_unit.from_metres(fields.precast_false_slab_depth_m):g}"
        )
        string_vars["in_situ_depth"].set(
            f"{displayed_unit.from_metres(fields.in_situ_slab_depth_m):g}"
        )
        bool_vars["false_slab_composite"].set(
            fields.false_slab_composite_participation
        )
        bool_vars["in_situ_composite"].set(
            fields.in_situ_slab_composite_participation
        )
        set_optional_length("rect_width", fields.rectangular_width_m)
        set_optional_length("rect_depth", fields.rectangular_depth_m)
        set_optional_length("t_flange_width", fields.t_flange_width_m)
        set_optional_length("t_flange_thickness", fields.t_flange_thickness_m)
        set_optional_length("t_web_width", fields.t_web_width_m)
        set_optional_length("t_total_depth", fields.t_total_depth_m)
        set_optional_length("i_top_width", fields.i_top_flange_width_m)
        set_optional_length("i_top_thickness", fields.i_top_flange_thickness_m)
        set_optional_length("i_web_width", fields.i_web_width_m)
        set_optional_length("i_web_depth", fields.i_web_depth_m)
        set_optional_length("i_bottom_width", fields.i_bottom_flange_width_m)
        set_optional_length(
            "i_bottom_thickness",
            fields.i_bottom_flange_thickness_m,
        )
        length_unit_var.set(displayed_unit.length_label)
        layout = project.geometry.girder_layout
        guidance_var.set(
            "Layout guidance: "
            f"edge overhang = {layout.implied_edge_overhang_m:.3f} m; "
            f"minimum deck width for current girder lines = "
            f"{layout.minimum_deck_width_m:.3f} m."
        )
        identity = composite_section_identity(project.geometry)
        composite_identity_var.set(
            "PRECAST: "
            f"{identity.precast_section}\n"
            "FINAL HARDENED SECTION: "
            f"{identity.final_section}\n"
            f"Overall physical depth = {identity.physical_total_depth_m:.3f} m; "
            f"participating deck depth = {identity.participating_deck_depth_m:.3f} m. "
            "The grillage uses edge-aware tributary deck widths by girder line."
        )

    def populate_preferences(preferences: ApplicationPreferences) -> None:
        string_vars["units"].set(preferences.units.value)
        basis = preferences.eurocode
        string_vars["gamma_g_unfavourable"].set(
            f"{basis.gamma_g_unfavourable:g}"
        )
        string_vars["gamma_g_favourable"].set(
            f"{basis.gamma_g_favourable:g}"
        )
        string_vars["gamma_q_traffic"].set(f"{basis.gamma_q_traffic:g}")
        string_vars["psi1_traffic"].set(f"{basis.psi1_traffic:g}")
        string_vars["psi2_traffic"].set(f"{basis.psi2_traffic:g}")
        string_vars["crack_limit"].set(f"{basis.crack_limit_mm:g}")
        string_vars["deflection_ratio"].set(
            f"{basis.deflection_limit_span_ratio:g}"
        )
        string_vars["grid_spacing"].set(
            f"{displayed_unit.from_metres(preferences.analysis.grid_spacing_m):g}"
        )
        string_vars["traffic_step"].set(
            f"{displayed_unit.from_metres(preferences.analysis.traffic_step_m):g}"
        )
        string_vars["max_tandem"].set(
            str(preferences.analysis.max_exhaustive_tandem_combinations)
        )

    def clear_results() -> None:
        for tree in (effect_tree, deflection_tree, package_tree):
            for item in tree.get_children():
                tree.delete(item)
        search_status_var.set("No native LM1 analysis has been run.")

    def show_result(result) -> None:
        for item in effect_tree.get_children():
            effect_tree.delete(item)
        for girder in result.girders:
            effect_tree.insert(
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

        for item in deflection_tree.get_children():
            deflection_tree.delete(item)
        for trace in result.deflections:
            deflection_tree.insert(
                "",
                tk.END,
                values=(
                    trace.girder_index,
                    f"{trace.value_mm:.3f}",
                    f"{trace.position_m:.3f}",
                    trace.case_id,
                ),
            )

        for item in package_tree.get_children():
            package_tree.delete(item)
        for case_id in result.governing_case_ids:
            package_tree.insert(
                "",
                tk.END,
                values=(
                    case_id,
                    "Exact governing native LM1 case for independent comparison",
                ),
            )

        search_status_var.set(
            f"Completed {result.evaluated_case_count} LM1 cases using "
            f"{result.search_strategy}; {len(result.governing_case_ids)} "
            "governing verification cases retained."
        )
        status_var.set("Native LM1 analysis complete.")
        refresh_dashboard()

    def refresh_dashboard() -> None:
        for item in capability_tree.get_children():
            capability_tree.delete(item)
        dashboard = session.dashboard()
        for capability in dashboard.capabilities:
            capability_tree.insert(
                "",
                tk.END,
                values=(
                    capability.name,
                    capability.state.value.replace("_", " "),
                    capability.detail,
                ),
            )

        result = session.last_lm1_search
        case_text = (
            "No application-generated governing cases exist yet."
            if result is None
            else (
                "Current governing native LM1 case IDs: "
                + ", ".join(str(value) for value in result.governing_case_ids)
                + "."
            )
        )
        _set_text(
            verification_text,
            (
                "Stage 7 independent acceptance boundary\n\n"
                "The application can generate the exact MIDAS Civil .mct and STAAD.Pro "
                ".std models used by the native analysis. Those files must be run in the "
                "installed external programs and their genuine returned results checked "
                "for geometry, stiffness, loading, result axes, signs and justified "
                "tolerances before production certification.\n\n"
                + case_text
            ),
        )
        _set_text(
            research_text,
            (
                "Research pipeline status\n\n"
                "The deterministic engine includes dataset structures, ANN surrogate "
                "training utilities, reliability mechanics and RBDO foundations. "
                "Ground-truth generation remains intentionally locked until the exact "
                "solver profile satisfies the deterministic verification manifest.\n\n"
                "Required profile evidence includes traffic loading, load combinations, "
                "flexure, shear, cracking, deflection, fatigue, detailing, transverse "
                "distribution, independent benchmarking and torsion when it is in scope.\n\n"
                "After Stage 7 external acceptance, Stage 8 closes the manifests; Stage 9 "
                "defines justified random-variable distributions/bounds/correlations; "
                "Stage 10 generates verified datasets, trains/validates the ANN and then "
                "runs reliability analysis/RBDO."
            ),
        )

    def set_busy(busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in analysis_buttons:
            button.configure(state=state)
        cancel_analysis_button.configure(
            state=tk.NORMAL if busy else tk.DISABLED
        )
        if not busy:
            progress["value"] = 0.0

    def fail(title: str, message: str) -> None:
        set_busy(False)
        status_var.set("Operation failed")
        messagebox.showerror(title, message)

    def commit_forms() -> None:
        nonlocal displayed_unit
        project = project_from_form()
        preferences = preferences_from_form()
        project_changed = project != session.project
        settings_changed = preferences.analysis != session.preferences.analysis
        if project_changed:
            session.replace_project(project)
        elif settings_changed:
            session.last_lm1_search = None
        session.set_preferences(preferences)
        displayed_unit = preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        if project_changed or settings_changed:
            clear_results()
        refresh_dashboard()

    def apply_project() -> None:
        try:
            project = project_from_form()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Project input", str(exc))
            return
        if project != session.project:
            session.replace_project(project)
            clear_results()
        populate_project(session.project)
        refresh_dashboard()
        status_var.set("Project definition applied.")

    def apply_basis() -> None:
        nonlocal displayed_unit
        try:
            project = project_from_form()
            preferences = preferences_from_form()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Design basis", str(exc))
            return
        project_changed = project != session.project
        settings_changed = preferences.analysis != session.preferences.analysis
        if project_changed:
            session.replace_project(project)
        elif settings_changed:
            session.last_lm1_search = None
        session.set_preferences(preferences)
        displayed_unit = preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        if project_changed or settings_changed:
            clear_results()
        refresh_dashboard()
        status_var.set("Application design basis applied.")

    def run_analysis() -> None:
        try:
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Project / design basis", str(exc))
            return

        if session.project.design_code is not DesignCode.EUROCODE:
            messagebox.showinfo(
                "Native traffic analysis",
                (
                    "The desktop full-width native traffic workbench currently uses "
                    "EN 1991-2 LM1. The isolated BS 5400 / BD 37 verification engine "
                    "remains available in the deterministic library but is not "
                    "misrepresented here as the LM1 workflow."
                ),
            )
            return

        analysis_cancel_event.clear()
        set_busy(True)
        progress["value"] = 0.0
        started = time.perf_counter()
        status_var.set("Preparing native LM1 grillage and traffic cases...")

        def update_progress(completed: int, total: int) -> None:
            elapsed = max(time.perf_counter() - started, 1.0e-9)
            rate = completed / elapsed
            remaining = max(total - completed, 0)
            eta = remaining / rate if rate > 0.0 else 0.0
            percent = 100.0 * completed / total

            def apply_progress() -> None:
                progress["value"] = percent
                status_var.set(
                    f"LM1 case {completed:,}/{total:,} — {percent:.1f}% — "
                    f"elapsed {elapsed / 60.0:.1f} min — ETA {eta / 60.0:.1f} min"
                )

            root.after(0, apply_progress)

        def worker() -> None:
            try:
                result = session.run_native_lm1(
                    progress_callback=update_progress,
                    cancel_requested=analysis_cancel_event.is_set,
                )
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                message = str(exc)
                root.after(
                    0,
                    lambda: fail("Native LM1 analysis", message),
                )
                return

            def complete() -> None:
                set_busy(False)
                show_result(result)

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def new_project() -> None:
        nonlocal displayed_unit
        session.project = application_default_project()
        session.project_path = None
        session.preferences = ApplicationPreferences()
        session.last_lm1_search = None
        displayed_unit = session.preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        clear_results()
        refresh_dashboard()
        status_var.set("New project")

    def open_project() -> None:
        nonlocal displayed_unit
        path = filedialog.askopenfilename(
            title="Open RC bridge project",
            filetypes=(("RC bridge project", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            opened = BridgeApplicationSession.open(path)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Open project", str(exc))
            return
        session.project = opened.project
        session.project_path = opened.project_path
        session.preferences = opened.preferences
        session.last_lm1_search = None
        displayed_unit = session.preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        clear_results()
        refresh_dashboard()
        status_var.set(f"Opened {Path(path).name}")

    def save_as() -> None:
        try:
            commit_forms()
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
        try:
            written = session.save(path)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Save project", str(exc))
            return
        status_var.set(f"Saved {written.name}")

    def save_current() -> None:
        if session.project_path is None:
            save_as()
            return
        try:
            commit_forms()
            path = session.save()
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Save project", str(exc))
            return
        status_var.set(f"Saved {path.name}")

    def require_analysis(action: str) -> bool:
        if session.last_lm1_search is not None:
            return True
        messagebox.showinfo(action, "Run native LM1 analysis first.")
        return False

    def save_html_report() -> None:
        if not require_analysis("Calculation report"):
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
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Calculation report", str(exc))
            return
        status_var.set(f"HTML report saved: {report.name}")

    def save_pdf_report() -> None:
        if not require_analysis("PDF calculation report"):
            return
        path = filedialog.asksaveasfilename(
            title="Save PDF calculation report",
            defaultextension=".pdf",
            filetypes=(("PDF report", "*.pdf"),),
        )
        if not path:
            return
        try:
            report = session.write_last_lm1_pdf_report(path)
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("PDF calculation report", str(exc))
            return
        status_var.set(f"PDF report saved: {report.name}")

    def print_preview() -> None:
        if not require_analysis("Print / preview report"):
            return
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".html",
                prefix="rc_bridge_report_",
                delete=False,
            ) as handle:
                path = Path(handle.name)
            session.write_last_lm1_report(path)
            webbrowser.open(path.resolve().as_uri())
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Print / preview report", str(exc))
            return
        status_var.set("Opened printable report in the default browser.")

    def export_verification() -> None:
        if not require_analysis("Verification export"):
            return
        directory = filedialog.askdirectory(
            title="Choose verification export folder"
        )
        if not directory:
            return
        try:
            packages = session.export_last_lm1_verification(
                directory,
                base_name="application_lm1",
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Verification export", str(exc))
            return
        status_var.set(
            f"Exported {len(packages)} governing MIDAS/STAAD case packages."
        )

    def cancel_analysis() -> None:
        analysis_cancel_event.set()
        status_var.set("Cancelling native LM1 analysis after the current case...")

    cancel_analysis_button.configure(command=cancel_analysis)
    apply_project_button.configure(command=apply_project)
    revert_project_button.configure(
        command=lambda: populate_project(session.project)
    )
    apply_basis_button.configure(command=apply_basis)
    revert_basis_button.configure(
        command=lambda: populate_preferences(session.preferences)
    )
    run_button.configure(command=run_analysis)
    refresh_dashboard_button.configure(command=refresh_dashboard)
    html_button.configure(command=save_html_report)
    pdf_button.configure(command=save_pdf_report)
    print_button.configure(command=print_preview)
    export_button.configure(command=export_verification)

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

    analysis_menu = tk.Menu(menu, tearoff=False)
    analysis_menu.add_command(label="Run native LM1", command=run_analysis)
    menu.add_cascade(label="Analysis", menu=analysis_menu)

    report_menu = tk.Menu(menu, tearoff=False)
    report_menu.add_command(label="Save HTML...", command=save_html_report)
    report_menu.add_command(label="Save PDF...", command=save_pdf_report)
    report_menu.add_command(label="Print / preview", command=print_preview)
    menu.add_cascade(label="Reports", menu=report_menu)

    verification_menu = tk.Menu(menu, tearoff=False)
    verification_menu.add_command(
        label="Export MIDAS / STAAD...",
        command=export_verification,
    )
    menu.add_cascade(label="Verification", menu=verification_menu)
    root.configure(menu=menu)

    populate_project(session.project)
    populate_preferences(session.preferences)
    clear_results()
    refresh_dashboard()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
