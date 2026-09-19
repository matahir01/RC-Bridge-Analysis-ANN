from __future__ import annotations

import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from rc_bridge.analysis.physical_sections import (
    composite_section_description,
    girder_tributary_slab_widths_m,
)
from rc_bridge.application.design_checks import ApplicationDesignSettings
from rc_bridge.application.extended_actions import ExtendedActionSettings
from rc_bridge.application.fatigue import FatigueApplicationSettings
from rc_bridge.application.gui_presenters import (
    analysis_dashboard_data,
    analysis_girder_diagram,
    bridge_preview_data,
    deck_dashboard_data,
    design_dashboard_data,
    verification_dashboard_data,
)
from rc_bridge.application.gui_rendering import (
    draw_bar_chart,
    draw_bridge_preview,
    draw_line_chart,
    draw_reinforcement_section,
)
from rc_bridge.application.gui_theme import configure_desktop_theme
from rc_bridge.application.interface_contract import (
    APPLICATION_INTERFACE_VERSION,
    build_application_view_snapshot,
    validate_application_interface,
    validate_engine_interface,
)
from rc_bridge.application.load_cases import (
    ApplicationLoadCaseFields,
    SurfacingExtent,
    eurocode_variable_action_scope,
)
from rc_bridge.application.local_deck import LocalDeckSettings
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
from rc_bridge.core.models import DesignCode, SectionType, SupportSystem
from rc_bridge.workflow.lm1_grillage_search import LM1SearchCancelled
from rc_bridge.workflow.project_bridge import SLSCombinationChoice


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as exc:
        raise RuntimeError(
            "The desktop interface requires Python with Tk support."
        ) from exc

    root = tk.Tk()
    root.title("RC Bridge Studio")
    root.geometry("1480x900")
    root.minsize(1180, 740)
    configure_desktop_theme(root, ttk)

    validate_engine_interface()
    session = BridgeApplicationSession(application_default_project())
    validate_application_interface(session)
    displayed_unit = session.preferences.units
    string_vars: dict[str, tk.StringVar] = {}
    bool_vars: dict[str, tk.BooleanVar] = {}
    status_var = tk.StringVar(value="Ready")
    length_unit_var = tk.StringVar(value=displayed_unit.length_label)
    workspace_title_var = tk.StringVar(value="Overview")
    project_header_var = tk.StringVar(value="")
    analysis_buttons: list[ttk.Button] = []
    cancel_event = threading.Event()

    def svar(name: str, value: str = "") -> tk.StringVar:
        item = tk.StringVar(value=value)
        string_vars[name] = item
        return item

    def bvar(name: str, value: bool = False) -> tk.BooleanVar:
        item = tk.BooleanVar(value=value)
        bool_vars[name] = item
        return item

    header = ttk.Frame(root, style="Header.TFrame", padding=(18, 11))
    header.pack(fill=tk.X)
    header_text = ttk.Frame(header, style="Header.TFrame")
    header_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(
        header_text,
        textvariable=workspace_title_var,
        style="HeaderTitle.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        header_text,
        textvariable=project_header_var,
        style="HeaderSubtitle.TLabel",
    ).pack(anchor="w", pady=(2, 0))

    header_actions = ttk.Frame(header, style="Header.TFrame")
    header_actions.pack(side=tk.RIGHT)
    header_open_button = ttk.Button(
        header_actions,
        text="Open",
        style="Secondary.TButton",
    )
    header_open_button.pack(side=tk.LEFT, padx=4)
    header_save_button = ttk.Button(
        header_actions,
        text="Save",
        style="Secondary.TButton",
    )
    header_save_button.pack(side=tk.LEFT, padx=4)
    header_run_button = ttk.Button(
        header_actions,
        text="Run full analysis",
        style="Primary.TButton",
    )
    header_run_button.pack(side=tk.LEFT, padx=(8, 0))
    analysis_buttons.append(header_run_button)

    body = ttk.Frame(root)
    body.pack(fill=tk.BOTH, expand=True)

    sidebar = ttk.Frame(body, style="Sidebar.TFrame", width=220, padding=(12, 14))
    sidebar.pack(side=tk.LEFT, fill=tk.Y)
    sidebar.pack_propagate(False)
    ttk.Label(
        sidebar,
        text="RC BRIDGE STUDIO",
        style="SidebarBrand.TLabel",
    ).pack(anchor="w", padx=4)
    ttk.Label(
        sidebar,
        text=f"ENGINE / APP API v{APPLICATION_INTERFACE_VERSION}",
        style="SidebarCaption.TLabel",
    ).pack(anchor="w", padx=4, pady=(2, 18))

    content = ttk.Frame(body, padding=(12, 10, 12, 6))
    content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    notebook = ttk.Notebook(content, style="Workspace.TNotebook")
    notebook.pack(fill=tk.BOTH, expand=True)

    overview_tab = ttk.Frame(notebook, padding=12)
    project_tab = ttk.Frame(notebook, padding=12)
    basis_tab = ttk.Frame(notebook, padding=12)
    load_cases_tab = ttk.Frame(notebook, padding=12)
    actions_tab = ttk.Frame(notebook, padding=12)
    analysis_tab = ttk.Frame(notebook, padding=12)
    design_tab = ttk.Frame(notebook, padding=12)
    local_tab = ttk.Frame(notebook, padding=12)
    calculations_tab = ttk.Frame(notebook, padding=12)
    verification_tab = ttk.Frame(notebook, padding=12)
    research_tab = ttk.Frame(notebook, padding=12)

    workspace_pages = (
        ("overview", "Overview", overview_tab, "WORKSPACE"),
        ("project", "Project", project_tab, "SETUP"),
        ("basis", "Design basis", basis_tab, "SETUP"),
        ("loads", "Loads & combinations", load_cases_tab, "SETUP"),
        ("actions", "Additional actions", actions_tab, "ANALYSIS"),
        ("analysis", "Traffic analysis", analysis_tab, "ANALYSIS"),
        ("design", "Design & checks", design_tab, "DESIGN"),
        ("deck", "Deck & fatigue", local_tab, "DESIGN"),
        ("calculations", "Calculations", calculations_tab, "REVIEW"),
        ("verification", "Verification", verification_tab, "REVIEW"),
        ("research", "Research", research_tab, "RESEARCH"),
    )
    for _, title, frame, _ in workspace_pages:
        notebook.add(frame, text=title)

    nav_buttons: dict[str, ttk.Button] = {}
    page_titles = {str(frame): title for _, title, frame, _ in workspace_pages}
    page_keys = {str(frame): key for key, _, frame, _ in workspace_pages}
    current_section: str | None = None
    for key, title, frame, section in workspace_pages:
        if section != current_section:
            ttk.Label(
                sidebar,
                text=section,
                style="SidebarSection.TLabel",
            ).pack(anchor="w", padx=6, pady=((8 if current_section else 0), 4))
            current_section = section
        button = ttk.Button(
            sidebar,
            text=title,
            style="Nav.TButton",
            command=lambda target=frame: notebook.select(target),
        )
        button.pack(fill=tk.X, pady=1)
        nav_buttons[key] = button

    ttk.Label(
        sidebar,
        text=(
            "Deterministic bridge analysis,\n"
            "design, verification & research"
        ),
        style="SidebarCaption.TLabel",
        justify=tk.LEFT,
    ).pack(side=tk.BOTTOM, anchor="w", padx=6, pady=(16, 2))

    def sync_workspace_navigation(_event=None) -> None:
        selected = notebook.select()
        workspace_title_var.set(page_titles.get(selected, "RC Bridge Studio"))
        active_key = page_keys.get(selected)
        for key, button in nav_buttons.items():
            button.configure(
                style="NavActive.TButton" if key == active_key else "Nav.TButton"
            )

    notebook.bind("<<NotebookTabChanged>>", sync_workspace_navigation)

    footer = ttk.Frame(root, style="Status.TFrame", padding=(14, 7, 14, 8))
    footer.pack(fill=tk.X)
    ttk.Label(
        footer,
        textvariable=status_var,
        style="SurfaceMuted.TLabel",
    ).pack(side=tk.LEFT)
    progress = ttk.Progressbar(
        footer,
        mode="determinate",
        maximum=100.0,
        length=220,
    )
    progress.pack(side=tk.RIGHT)
    full_run_button = ttk.Button(
        footer,
        text="Run Full Analysis & Design",
        style="Primary.TButton",
    )
    full_run_button.pack(side=tk.RIGHT, padx=(0, 10))
    analysis_buttons.append(full_run_button)

    notebook.select(overview_tab)
    sync_workspace_navigation()

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

    def add_entry_at(
        parent,
        *,
        row: int,
        label: str,
        key: str,
        label_column: int,
        entry_column: int,
        width: int = 20,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=label_column,
            sticky="w",
            padx=(8 if label_column else 0, 8),
            pady=3,
        )
        ttk.Entry(parent, textvariable=svar(key), width=width).grid(
            row=row,
            column=entry_column,
            sticky="ew",
            pady=3,
        )

    # ------------------------------------------------------------------
    # Overview workspace
    # ------------------------------------------------------------------
    overview_tab.columnconfigure(0, weight=1)
    overview_tab.columnconfigure(1, weight=1)
    overview_tab.rowconfigure(1, weight=1)

    overview_project_var = tk.StringVar(value="")
    overview_progress_var = tk.StringVar(value="0 / 0")
    overview_design_var = tk.StringVar(value="Not run")
    overview_verification_var = tk.StringVar(value="Not imported")
    overview_performance_var = tk.StringVar(value="")
    overview_performance_detail_var = tk.StringVar(value="")

    overview_heading = ttk.Frame(overview_tab)
    overview_heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
    ttk.Label(
        overview_heading,
        text="Project control centre",
        style="PageTitle.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        overview_heading,
        text=(
            "Define the bridge, run the deterministic workflow, inspect worked "
            "calculations and close the external verification loop from one workspace."
        ),
        style="Muted.TLabel",
        wraplength=950,
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(3, 0))

    overview_metrics = ttk.Frame(overview_tab)
    overview_metrics.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
    overview_metrics.columnconfigure(0, weight=1)
    overview_metrics.columnconfigure(1, weight=1)

    project_card = ttk.LabelFrame(
        overview_metrics,
        text="Current project",
        style="Card.TLabelframe",
        padding=14,
    )
    project_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Label(
        project_card,
        textvariable=overview_project_var,
        style="CardTitle.TLabel",
        wraplength=600,
        justify=tk.LEFT,
    ).pack(anchor="w")

    progress_card = ttk.LabelFrame(
        overview_metrics,
        text="Workflow progress",
        style="Card.TLabelframe",
        padding=14,
    )
    progress_card.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))
    ttk.Label(
        progress_card,
        textvariable=overview_progress_var,
        style="Metric.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        progress_card,
        text="completed stages",
        style="SurfaceMuted.TLabel",
    ).pack(anchor="w")

    design_card = ttk.LabelFrame(
        overview_metrics,
        text="Design status",
        style="Card.TLabelframe",
        padding=14,
    )
    design_card.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))
    ttk.Label(
        design_card,
        textvariable=overview_design_var,
        style="Metric.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        design_card,
        text="integrated ULS/SLS",
        style="SurfaceMuted.TLabel",
    ).pack(anchor="w")

    verification_card = ttk.LabelFrame(
        overview_metrics,
        text="External verification",
        style="Card.TLabelframe",
        padding=14,
    )
    verification_card.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Label(
        verification_card,
        textvariable=overview_verification_var,
        style="CardTitle.TLabel",
        wraplength=600,
        justify=tk.LEFT,
    ).pack(anchor="w")

    performance_card = ttk.LabelFrame(
        overview_metrics,
        text="Performance diagnostics",
        style="Card.TLabelframe",
        padding=14,
    )
    performance_card.grid(row=3, column=0, columnspan=2, sticky="ew")
    ttk.Label(
        performance_card,
        textvariable=overview_performance_var,
        style="CardTitle.TLabel",
    ).pack(anchor="w")
    ttk.Label(
        performance_card,
        textvariable=overview_performance_detail_var,
        style="SurfaceMuted.TLabel",
        wraplength=600,
        justify=tk.LEFT,
    ).pack(anchor="w", pady=(3, 0))

    workflow_card = ttk.LabelFrame(
        overview_tab,
        text="Engineering workflow",
        style="Card.TLabelframe",
        padding=10,
    )
    workflow_card.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
    workflow_card.rowconfigure(0, weight=1)
    workflow_card.columnconfigure(0, weight=1)
    overview_stage_tree = ttk.Treeview(
        workflow_card,
        columns=("state", "detail"),
        show="headings",
        height=13,
    )
    overview_stage_tree.heading("state", text="Status")
    overview_stage_tree.heading("detail", text="Stage / engineering note")
    overview_stage_tree.column("state", width=90, anchor=tk.CENTER)
    overview_stage_tree.column("detail", width=520, anchor=tk.W)
    overview_stage_tree.grid(row=0, column=0, sticky="nsew")

    overview_actions = ttk.Frame(overview_tab)
    overview_actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
    overview_run_button = ttk.Button(
        overview_actions,
        text="Run Full Analysis & Design",
        style="Primary.TButton",
    )
    overview_run_button.pack(side=tk.LEFT)
    overview_calculations_button = ttk.Button(
        overview_actions,
        text="Review calculations",
        style="Secondary.TButton",
    )
    overview_calculations_button.pack(side=tk.LEFT, padx=8)
    overview_verification_button = ttk.Button(
        overview_actions,
        text="Open verification",
        style="Secondary.TButton",
    )
    overview_verification_button.pack(side=tk.LEFT)
    analysis_buttons.append(overview_run_button)

    # ------------------------------------------------------------------
    # Calculation review workspace
    # ------------------------------------------------------------------
    calculations_tab.columnconfigure(0, weight=2)
    calculations_tab.columnconfigure(1, weight=3)
    calculations_tab.rowconfigure(1, weight=1)

    calculation_heading = ttk.Frame(calculations_tab)
    calculation_heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Label(
        calculation_heading,
        text="Worked calculation review",
        style="PageTitle.TLabel",
    ).pack(side=tk.LEFT)
    calculation_refresh_button = ttk.Button(
        calculation_heading,
        text="Refresh calculations",
        style="Secondary.TButton",
    )
    calculation_refresh_button.pack(side=tk.RIGHT)

    calculation_tree_frame = ttk.LabelFrame(
        calculations_tab,
        text="Calculation navigator",
        style="Card.TLabelframe",
        padding=8,
    )
    calculation_tree_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
    calculation_tree_frame.rowconfigure(0, weight=1)
    calculation_tree_frame.columnconfigure(0, weight=1)
    calculation_tree = ttk.Treeview(
        calculation_tree_frame,
        columns=("status",),
        show="tree headings",
    )
    calculation_tree.heading("#0", text="Block / step")
    calculation_tree.heading("status", text="Status")
    calculation_tree.column("#0", width=390, anchor=tk.W)
    calculation_tree.column("status", width=90, anchor=tk.CENTER)
    calculation_tree.grid(row=0, column=0, sticky="nsew")

    calculation_detail_frame = ttk.LabelFrame(
        calculations_tab,
        text="Calculation detail",
        style="Card.TLabelframe",
        padding=10,
    )
    calculation_detail_frame.grid(row=1, column=1, sticky="nsew", padx=(7, 0))
    calculation_detail_frame.rowconfigure(0, weight=1)
    calculation_detail_frame.columnconfigure(0, weight=1)
    calculation_detail = tk.Text(
        calculation_detail_frame,
        wrap="word",
        relief="flat",
        padx=14,
        pady=12,
        font=("Segoe UI", 10),
        background="#FFFFFF",
        foreground="#172033",
        insertbackground="#172033",
    )
    calculation_detail.grid(row=0, column=0, sticky="nsew")
    calculation_detail.configure(state=tk.DISABLED)
    calculation_item_map: dict[str, tuple[object, object | None]] = {}

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

    ttk.Label(profile_frame, text="Precast section type").grid(
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

    project_preview_frame = ttk.LabelFrame(
        project_tab,
        text="Applied bridge geometry preview",
        style="Card.TLabelframe",
        padding=8,
    )
    project_preview_frame.grid(
        row=2,
        column=0,
        columnspan=3,
        sticky="nsew",
        pady=(10, 0),
    )
    project_tab.rowconfigure(2, weight=1)
    project_preview_canvas = tk.Canvas(
        project_preview_frame,
        height=300,
        background="#FFFFFF",
        highlightthickness=0,
    )
    project_preview_canvas.pack(fill=tk.BOTH, expand=True)

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
    add_entry(
        ec_frame,
        row=3,
        label="γQ non-traffic / execution",
        key="gamma_q_nontraffic",
    )
    add_entry(ec_frame, row=4, label="ψ1 traffic", key="psi1_traffic")
    add_entry(ec_frame, row=5, label="ψ2 traffic", key="psi2_traffic")
    add_entry(ec_frame, row=6, label="ψ1 LM2", key="psi1_lm2")
    add_entry(
        ec_frame,
        row=7,
        label="ψ0 thermal ULS",
        key="psi0_thermal_uls",
    )
    add_entry(
        ec_frame,
        row=8,
        label="ψ0 thermal SLS",
        key="psi0_thermal_sls",
    )
    add_entry(ec_frame, row=9, label="ψ1 thermal", key="psi1_thermal")
    add_entry(ec_frame, row=10, label="ψ2 thermal", key="psi2_thermal")
    add_entry(ec_frame, row=11, label="Crack limit (mm)", key="crack_limit")
    add_entry(
        ec_frame,
        row=12,
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
    # Load cases & combinations tab
    # ------------------------------------------------------------------
    load_cases_tab.columnconfigure(0, weight=1)
    load_cases_tab.rowconfigure(1, weight=1)

    load_input_frame = ttk.LabelFrame(
        load_cases_tab,
        text="Permanent actions",
        padding=10,
    )
    load_input_frame.grid(row=0, column=0, sticky="ew")
    for column in range(4):
        load_input_frame.columnconfigure(column, weight=1)

    add_entry(
        load_input_frame,
        row=0,
        label="Surfacing thickness",
        key="load_surfacing_thickness",
    )
    add_entry(
        load_input_frame,
        row=1,
        label="Surfacing density (kN/m³)",
        key="load_surfacing_density",
    )
    ttk.Label(load_input_frame, text="Surfacing transverse extent").grid(
        row=2, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        load_input_frame,
        textvariable=svar("load_surfacing_extent"),
        values=[item.value for item in SurfacingExtent],
        state="readonly",
        width=20,
    ).grid(row=2, column=1, sticky="ew", pady=3)

    add_entry_at(
        load_input_frame,
        row=0,
        label="Left barrier (kN/m)",
        key="load_left_barrier",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        load_input_frame,
        row=1,
        label="Right barrier (kN/m)",
        key="load_right_barrier",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        load_input_frame,
        row=2,
        label="Left services (kN/m)",
        key="load_left_services",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        load_input_frame,
        row=3,
        label="Right services (kN/m)",
        key="load_right_services",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        load_input_frame,
        row=4,
        label="Left services y-position",
        key="load_left_services_y",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        load_input_frame,
        row=5,
        label="Right services y-position",
        key="load_right_services_y",
        label_column=2,
        entry_column=3,
    )

    load_button_frame = ttk.Frame(load_input_frame)
    load_button_frame.grid(row=6, column=0, columnspan=4, sticky="e", pady=(8, 0))
    apply_load_cases_button = ttk.Button(
        load_button_frame,
        text="Apply load cases",
    )
    apply_load_cases_button.pack(side=tk.LEFT, padx=4)
    revert_load_cases_button = ttk.Button(
        load_button_frame,
        text="Revert",
    )
    revert_load_cases_button.pack(side=tk.LEFT, padx=4)

    load_views = ttk.Panedwindow(load_cases_tab, orient=tk.VERTICAL)
    load_views.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

    audit_frame = ttk.LabelFrame(
        load_views,
        text="Automatic permanent-load audit — equivalent full-length line loads",
        padding=8,
    )
    audit_columns = (
        "girder",
        "girder_sw",
        "false_slab",
        "in_situ",
        "surfacing",
        "barriers",
        "services",
        "other",
        "total",
    )
    permanent_audit_tree = ttk.Treeview(
        audit_frame,
        columns=audit_columns,
        show="headings",
        height=8,
    )
    audit_headings = {
        "girder": "Girder",
        "girder_sw": "Girder SW",
        "false_slab": "75 mm slab",
        "in_situ": "In-situ slab",
        "surfacing": "Surfacing",
        "barriers": "Barriers",
        "services": "Services",
        "other": "Other",
        "total": "Total Gk",
    }
    for key in audit_columns:
        permanent_audit_tree.heading(key, text=audit_headings[key])
        permanent_audit_tree.column(key, width=105, anchor=tk.CENTER)
    permanent_audit_tree.pack(fill=tk.BOTH, expand=True)
    permanent_load_canvas = tk.Canvas(
        audit_frame,
        height=155,
        background="#FFFFFF",
        highlightthickness=0,
    )
    permanent_load_canvas.pack(fill=tk.X, pady=(8, 0))
    load_views.add(audit_frame, weight=1)

    lower_load_frame = ttk.Frame(load_views)
    lower_load_frame.columnconfigure(0, weight=1)
    lower_load_frame.columnconfigure(1, weight=1)
    lower_load_frame.rowconfigure(0, weight=1)

    scope_frame = ttk.LabelFrame(
        lower_load_frame,
        text="Variable-action scope",
        padding=8,
    )
    scope_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
    action_scope_tree = ttk.Treeview(
        scope_frame,
        columns=("action", "status", "detail"),
        show="headings",
        height=8,
    )
    action_scope_tree.heading("action", text="Action")
    action_scope_tree.heading("status", text="Status")
    action_scope_tree.heading("detail", text="Current application treatment")
    action_scope_tree.column("action", width=190, anchor=tk.W)
    action_scope_tree.column("status", width=120, anchor=tk.CENTER)
    action_scope_tree.column("detail", width=400, anchor=tk.W)
    action_scope_tree.pack(fill=tk.BOTH, expand=True)

    combinations_frame = ttk.LabelFrame(
        lower_load_frame,
        text="Baseline Gk + LM1 interpretation",
        padding=8,
    )
    combinations_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
    combination_columns = (
        "girder",
        "g_m",
        "q_m",
        "uls_m",
        "g_v",
        "q_v",
        "uls_v",
        "sls_char_m",
        "sls_freq_m",
        "sls_qp_m",
    )
    combination_tree = ttk.Treeview(
        combinations_frame,
        columns=combination_columns,
        show="headings",
        height=8,
    )
    combination_headings = {
        "girder": "Girder",
        "g_m": "Gk M",
        "q_m": "LM1 Qk M",
        "uls_m": "ULS M",
        "g_v": "Gk V",
        "q_v": "LM1 Qk V",
        "uls_v": "ULS V",
        "sls_char_m": "SLS char M",
        "sls_freq_m": "SLS freq M",
        "sls_qp_m": "SLS qp M",
    }
    for key in combination_columns:
        combination_tree.heading(key, text=combination_headings[key])
        combination_tree.column(key, width=95, anchor=tk.CENTER)
    combination_tree.pack(fill=tk.BOTH, expand=True)

    load_views.add(lower_load_frame, weight=1)

    ttk.Label(
        load_cases_tab,
        text=(
            "Permanent self-weight is derived automatically from the physical girder/deck. "
            "The table above is deliberately the baseline Gk + characteristic-LM1 view. "
            "Run Additional actions 1–6 and then Design & checks for the governing compatible "
            "traffic groups, construction stages, bearing/restraint demand and accidental "
            "barrier path; they are not silently added into this baseline table."
        ),
        wraplength=1180,
        justify=tk.LEFT,
    ).grid(row=2, column=0, sticky="ew", pady=(8, 0))

    # ------------------------------------------------------------------
    # Additional actions tab
    # ------------------------------------------------------------------
    actions_tab.columnconfigure(0, weight=1)
    actions_tab.rowconfigure(1, weight=1)

    actions_header = ttk.Frame(actions_tab)
    actions_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    actions_header.columnconfigure(0, weight=1)
    ttk.Label(
        actions_header,
        text=(
            "Required additional action families for this bridge plus static wind. "
            "Vertical actions are solved on the native grillage where the current physics "
            "supports them; longitudinal/horizontal/local actions are calculated explicitly "
            "and kept outside the vertical solver rather than being silently approximated."
        ),
        wraplength=980,
        justify=tk.LEFT,
    ).grid(row=0, column=0, sticky="ew")
    run_actions_button = ttk.Button(
        actions_header,
        text="Run required actions + wind",
    )
    run_actions_button.grid(row=0, column=1, sticky="e", padx=(10, 0))
    analysis_buttons.append(run_actions_button)

    actions_canvas = tk.Canvas(
        actions_tab,
        highlightthickness=0,
        borderwidth=0,
    )
    actions_scrollbar = ttk.Scrollbar(
        actions_tab,
        orient=tk.VERTICAL,
        command=actions_canvas.yview,
    )
    actions_canvas.configure(yscrollcommand=actions_scrollbar.set)
    actions_canvas.grid(row=1, column=0, sticky="nsew")
    actions_scrollbar.grid(row=1, column=1, sticky="ns")

    actions_scroll_frame = ttk.Frame(actions_canvas)
    actions_canvas_window = actions_canvas.create_window(
        (0, 0),
        window=actions_scroll_frame,
        anchor="nw",
    )

    def _refresh_actions_scrollregion(_event=None) -> None:
        actions_canvas.configure(scrollregion=actions_canvas.bbox("all"))

    def _fit_actions_scroll_width(event) -> None:
        actions_canvas.itemconfigure(actions_canvas_window, width=event.width)

    actions_scroll_frame.bind("<Configure>", _refresh_actions_scrollregion)
    actions_canvas.bind("<Configure>", _fit_actions_scroll_width)
    actions_scroll_frame.columnconfigure(0, weight=1)

    actions_input = ttk.Frame(actions_scroll_frame)
    actions_input.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    for column in range(3):
        actions_input.columnconfigure(column, weight=1)

    traffic_actions_frame = ttk.LabelFrame(
        actions_input,
        text="Traffic actions — braking, pedestrian, LM2",
        padding=8,
    )
    traffic_actions_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
    traffic_actions_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(
        traffic_actions_frame,
        text="Braking / acceleration",
        variable=bvar("action_braking_enabled"),
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    add_entry(
        traffic_actions_frame,
        row=1,
        label="Braking loaded length (blank = full)",
        key="action_braking_length",
    )
    add_entry(
        traffic_actions_frame,
        row=2,
        label="Braking alpha Q1",
        key="action_braking_alpha_Q1",
    )
    add_entry(
        traffic_actions_frame,
        row=3,
        label="Braking alpha q1",
        key="action_braking_alpha_q1",
    )
    add_entry(
        traffic_actions_frame,
        row=4,
        label="gr2 LM1 tandem factor",
        key="action_gr2_ts_factor",
    )
    add_entry(
        traffic_actions_frame,
        row=5,
        label="gr2 LM1 UDL factor",
        key="action_gr2_udl_factor",
    )
    ttk.Separator(traffic_actions_frame).grid(
        row=6, column=0, columnspan=2, sticky="ew", pady=5
    )
    ttk.Checkbutton(
        traffic_actions_frame,
        text="Pedestrian / footway UDL",
        variable=bvar("action_pedestrian_enabled"),
    ).grid(row=7, column=0, columnspan=2, sticky="w")
    add_entry(
        traffic_actions_frame,
        row=8,
        label="Pedestrian qfk (kN/m²)",
        key="action_pedestrian_q",
    )
    add_entry(
        traffic_actions_frame,
        row=9,
        label="Reduced qfk with LM1 (kN/m²)",
        key="action_pedestrian_reduced_q",
    )
    add_entry(
        traffic_actions_frame,
        row=10,
        label="Left usable footway width",
        key="action_left_footway",
    )
    add_entry(
        traffic_actions_frame,
        row=11,
        label="Right usable footway width",
        key="action_right_footway",
    )
    ttk.Separator(traffic_actions_frame).grid(
        row=12, column=0, columnspan=2, sticky="ew", pady=5
    )
    ttk.Checkbutton(
        traffic_actions_frame,
        text="LM2 isolated axle scan",
        variable=bvar("action_lm2_enabled"),
    ).grid(row=13, column=0, columnspan=2, sticky="w")
    add_entry(
        traffic_actions_frame,
        row=14,
        label="LM2 beta Q",
        key="action_lm2_beta",
    )
    add_entry(
        traffic_actions_frame,
        row=15,
        label="LM2 longitudinal step",
        key="action_lm2_x_step",
    )
    add_entry(
        traffic_actions_frame,
        row=16,
        label="LM2 transverse step",
        key="action_lm2_y_step",
    )

    thermal_actions_frame = ttk.LabelFrame(
        actions_input,
        text="Thermal actions — EN 1991-1-5 inputs",
        padding=8,
    )
    thermal_actions_frame.grid(row=0, column=1, sticky="nsew", padx=4)
    thermal_actions_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(
        thermal_actions_frame,
        text="Thermal action",
        variable=bvar("action_thermal_enabled"),
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    add_entry(
        thermal_actions_frame,
        row=1,
        label="Thermal alpha (/°C)",
        key="action_thermal_alpha",
    )
    add_entry(
        thermal_actions_frame,
        row=2,
        label="Uniform expansion ΔT (°C)",
        key="action_thermal_expansion",
    )
    add_entry(
        thermal_actions_frame,
        row=3,
        label="Uniform contraction ΔT (°C)",
        key="action_thermal_contraction",
    )
    add_entry(
        thermal_actions_frame,
        row=4,
        label="Top-warmer gradient ΔT (°C)",
        key="action_thermal_gradient_heat",
    )
    add_entry(
        thermal_actions_frame,
        row=5,
        label="Bottom-warmer gradient ΔT (°C)",
        key="action_thermal_gradient_cool",
    )
    add_entry(
        thermal_actions_frame,
        row=6,
        label="Longitudinal restraint fraction",
        key="action_thermal_restraint",
    )
    ttk.Separator(thermal_actions_frame).grid(
        row=7, column=0, columnspan=2, sticky="ew", pady=5
    )
    add_entry(
        thermal_actions_frame,
        row=8,
        label="Bearing longitudinal capacity / bearing (kN)",
        key="action_bearing_force_capacity",
    )
    add_entry(
        thermal_actions_frame,
        row=9,
        label="Bearing movement capacity (mm)",
        key="action_bearing_movement_capacity",
    )
    ttk.Label(
        thermal_actions_frame,
        text=(
            "15/8 °C are first-generation concrete-beam reference gradients. "
            "Uniform expansion/contraction ranges must come from the project climate/"
            "National Annex; zero capacity means demand-only and remains a design blocker."
        ),
        wraplength=340,
        justify=tk.LEFT,
    ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))

    accidental_actions_frame = ttk.LabelFrame(
        actions_input,
        text="Barrier impact & construction",
        padding=8,
    )
    accidental_actions_frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
    accidental_actions_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(
        accidental_actions_frame,
        text="Vehicle impact on safety barrier",
        variable=bvar("action_barrier_enabled"),
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    add_entry(
        accidental_actions_frame,
        row=1,
        label="Transverse impact force (kN)",
        key="action_barrier_force",
    )
    add_entry(
        accidental_actions_frame,
        row=2,
        label="Barrier load height (m)",
        key="action_barrier_height",
    )
    add_entry(
        accidental_actions_frame,
        row=3,
        label="Vertical wheel factor",
        key="action_barrier_vertical_factor",
    )
    add_entry(
        accidental_actions_frame,
        row=4,
        label="Barrier alpha Q1",
        key="action_barrier_alpha_Q1",
    )
    add_entry(
        accidental_actions_frame,
        row=5,
        label="Barrier transverse resistance (kN)",
        key="action_barrier_transverse_resistance",
    )
    add_entry(
        accidental_actions_frame,
        row=6,
        label="Barrier base-moment resistance (kNm)",
        key="action_barrier_moment_resistance",
    )
    ttk.Separator(accidental_actions_frame).grid(
        row=7, column=0, columnspan=2, sticky="ew", pady=5
    )
    ttk.Checkbutton(
        accidental_actions_frame,
        text="Construction-stage actions",
        variable=bvar("action_construction_enabled"),
    ).grid(row=8, column=0, columnspan=2, sticky="w")
    add_entry(
        accidental_actions_frame,
        row=9,
        label="Execution UDL (kN/m²)",
        key="action_construction_udl",
    )
    ttk.Label(
        accidental_actions_frame,
        text=(
            "Girder, false-slab, wet-deck and superimposed permanent actions are "
            "automatically separated by construction stage. Zero barrier resistance "
            "means demand-only and remains a design blocker."
        ),
        wraplength=340,
        justify=tk.LEFT,
    ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))

    wind_actions_frame = ttk.LabelFrame(
        actions_input,
        text="Static wind action & transverse bearing capacity",
        padding=8,
    )
    wind_actions_frame.grid(
        row=1,
        column=0,
        columnspan=3,
        sticky="ew",
        pady=(8, 0),
    )
    for column in range(6):
        wind_actions_frame.columnconfigure(column, weight=1)
    ttk.Checkbutton(
        wind_actions_frame,
        text="Wind action",
        variable=bvar("action_wind_enabled"),
    ).grid(row=0, column=0, columnspan=2, sticky="w")
    add_entry_at(
        wind_actions_frame,
        row=1,
        label="Basic/project wind speed (m/s)",
        key="action_wind_velocity",
        label_column=0,
        entry_column=1,
    )
    add_entry_at(
        wind_actions_frame,
        row=2,
        label="Air density (kg/m³)",
        key="action_wind_density",
        label_column=0,
        entry_column=1,
    )
    add_entry_at(
        wind_actions_frame,
        row=1,
        label="Exposure factor",
        key="action_wind_exposure",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        wind_actions_frame,
        row=2,
        label="Transverse force coefficient",
        key="action_wind_transverse_cf",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        wind_actions_frame,
        row=1,
        label="Vertical force coefficient",
        key="action_wind_vertical_cf",
        label_column=4,
        entry_column=5,
    )
    add_entry_at(
        wind_actions_frame,
        row=2,
        label="Loaded height (m; 0 = auto)",
        key="action_wind_height",
        label_column=4,
        entry_column=5,
    )
    add_entry_at(
        wind_actions_frame,
        row=3,
        label="Bearing transverse capacity / bearing (kN)",
        key="action_bearing_transverse_capacity",
        label_column=0,
        entry_column=1,
    )
    ttk.Label(
        wind_actions_frame,
        text=(
            "Wind speed is a project/site input. The program derives static pressure/resultants "
            "and sends the transverse resultant to the support/bearing design path; it does "
            "not invent site terrain/orography or aerodynamic-instability data."
        ),
        wraplength=900,
        justify=tk.LEFT,
    ).grid(row=3, column=2, columnspan=4, sticky="w", padx=(8, 0))

    actions_result_frame = ttk.LabelFrame(
        actions_scroll_frame,
        text="Action calculation / analysis results",
        padding=8,
    )
    actions_result_frame.grid(row=1, column=0, sticky="nsew")
    action_result_tree = ttk.Treeview(
        actions_result_frame,
        columns=("action", "result", "value", "scope"),
        show="headings",
        height=14,
    )
    action_result_tree.heading("action", text="Action")
    action_result_tree.heading("result", text="Result")
    action_result_tree.heading("value", text="Value")
    action_result_tree.heading("scope", text="Analysis / engineering boundary")
    action_result_tree.column("action", width=190, anchor=tk.W)
    action_result_tree.column("result", width=220, anchor=tk.W)
    action_result_tree.column("value", width=180, anchor=tk.CENTER)
    action_result_tree.column("scope", width=700, anchor=tk.W)
    action_result_tree.pack(fill=tk.BOTH, expand=True)

    def _actions_mousewheel(event) -> str:
        delta = -1 if event.delta > 0 else 1
        actions_canvas.yview_scroll(delta, "units")
        return "break"

    def _bind_actions_mousewheel(_event) -> None:
        actions_canvas.bind_all("<MouseWheel>", _actions_mousewheel)

    def _unbind_actions_mousewheel(_event) -> None:
        actions_canvas.unbind_all("<MouseWheel>")

    actions_canvas.bind("<Enter>", _bind_actions_mousewheel)
    actions_canvas.bind("<Leave>", _unbind_actions_mousewheel)
    actions_scroll_frame.bind("<Enter>", _bind_actions_mousewheel)
    actions_scroll_frame.bind("<Leave>", _unbind_actions_mousewheel)

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

    cancel_button = ttk.Button(
        analysis_header,
        text="Cancel analysis",
        state=tk.DISABLED,
    )
    cancel_button.pack(side=tk.RIGHT, padx=(8, 0))
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

    analysis_metric_frame = ttk.Frame(analysis_tab)
    analysis_metric_frame.pack(fill=tk.X, pady=(0, 8))
    analysis_metric_vars = {
        "moment": tk.StringVar(value="—"),
        "shear": tk.StringVar(value="—"),
        "torsion": tk.StringVar(value="—"),
        "deflection": tk.StringVar(value="—"),
    }
    for metric_index, (metric_key, metric_title) in enumerate(
        (
            ("moment", "Max |M|"),
            ("shear", "Max |V|"),
            ("torsion", "Max |T|"),
            ("deflection", "Max |DZ|"),
        )
    ):
        card = ttk.LabelFrame(
            analysis_metric_frame,
            text=metric_title,
            style="Card.TLabelframe",
            padding=(12, 8),
        )
        card.grid(
            row=0,
            column=metric_index,
            sticky="ew",
            padx=(0 if metric_index == 0 else 4, 0),
        )
        analysis_metric_frame.columnconfigure(metric_index, weight=1)
        ttk.Label(
            card,
            textvariable=analysis_metric_vars[metric_key],
            style="Metric.TLabel",
        ).pack(anchor="w")

    analysis_chart_frame = ttk.LabelFrame(
        analysis_tab,
        text="Girder response overview",
        style="Card.TLabelframe",
        padding=8,
    )
    analysis_chart_frame.pack(fill=tk.X, pady=(0, 8))
    analysis_chart_controls = ttk.Frame(analysis_chart_frame)
    analysis_chart_controls.pack(fill=tk.X)
    ttk.Label(analysis_chart_controls, text="Display").pack(side=tk.LEFT)
    analysis_chart_metric_var = tk.StringVar(value="Moment")
    analysis_chart_metric = ttk.Combobox(
        analysis_chart_controls,
        textvariable=analysis_chart_metric_var,
        values=("Moment", "Shear", "Torsion", "Deflection"),
        state="readonly",
        width=16,
    )
    analysis_chart_metric.pack(side=tk.LEFT, padx=(6, 12))
    ttk.Label(analysis_chart_controls, text="Girder").pack(side=tk.LEFT)
    analysis_chart_girder_var = tk.StringVar(value="G1")
    analysis_chart_girder = ttk.Combobox(
        analysis_chart_controls,
        textvariable=analysis_chart_girder_var,
        values=("G1",),
        state="readonly",
        width=9,
    )
    analysis_chart_girder.pack(side=tk.LEFT, padx=(6, 0))
    analysis_chart_canvas = tk.Canvas(
        analysis_chart_frame,
        height=210,
        background="#FFFFFF",
        highlightthickness=0,
    )
    analysis_chart_canvas.pack(fill=tk.X, pady=(6, 0))

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
        height=9,
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
            "Analysis-derived EC2 design interpretation. Flexure, shear, crack width, "
            "service deflection and reinforcement/detailing are calculated from the current "
            "physical layered section and the governing compatible action groups. "
            "Construction stages, bearing/restraint demand and local barrier demand are "
            "carried with the design; unresolved capacities remain explicit blockers. "
            "Production acceptance remains locked until genuine independent verification is completed."
        ),
        wraplength=1180,
        justify=tk.LEFT,
    ).pack(fill=tk.X)

    design_controls = ttk.LabelFrame(
        design_tab,
        text="Design assumptions",
        padding=8,
    )
    design_controls.pack(fill=tk.X, pady=(8, 0))
    for column in range(6):
        design_controls.columnconfigure(column, weight=1)

    add_entry_at(
        design_controls,
        row=0,
        label="Cover (mm)",
        key="design_cover",
        label_column=0,
        entry_column=1,
    )
    add_entry_at(
        design_controls,
        row=1,
        label="Durability min cover (mm)",
        key="design_durability_cover",
        label_column=0,
        entry_column=1,
    )
    add_entry_at(
        design_controls,
        row=2,
        label="Cover deviation (mm)",
        key="design_cover_deviation",
        label_column=0,
        entry_column=1,
    )
    add_entry_at(
        design_controls,
        row=0,
        label="Aggregate size (mm)",
        key="design_aggregate",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        design_controls,
        row=1,
        label="Nominal link dia. (mm)",
        key="design_link_diameter",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        design_controls,
        row=2,
        label="cot θ",
        key="design_cot_theta",
        label_column=2,
        entry_column=3,
    )
    add_entry_at(
        design_controls,
        row=0,
        label="Creep coefficient",
        key="design_creep",
        label_column=4,
        entry_column=5,
    )
    add_entry_at(
        design_controls,
        row=1,
        label="Deflection β",
        key="design_beta",
        label_column=4,
        entry_column=5,
    )
    add_entry_at(
        design_controls,
        row=2,
        label="Crack kt",
        key="design_crack_kt",
        label_column=4,
        entry_column=5,
    )

    ttk.Label(design_controls, text="Crack SLS combination").grid(
        row=3, column=0, sticky="w", padx=(0, 8), pady=3
    )
    ttk.Combobox(
        design_controls,
        textvariable=svar("design_crack_combination"),
        values=[item.value for item in SLSCombinationChoice],
        state="readonly",
        width=18,
    ).grid(row=3, column=1, sticky="ew", pady=3)
    ttk.Label(design_controls, text="Deflection SLS combination").grid(
        row=3, column=2, sticky="w", padx=(8, 8), pady=3
    )
    ttk.Combobox(
        design_controls,
        textvariable=svar("design_deflection_combination"),
        values=[item.value for item in SLSCombinationChoice],
        state="readonly",
        width=18,
    ).grid(row=3, column=3, sticky="ew", pady=3)

    run_design_button = ttk.Button(
        design_controls,
        text="Run design interpretation",
    )
    run_design_button.grid(row=3, column=5, sticky="e", pady=3)

    design_status_var = tk.StringVar(
        value=(
            "Run native LM1 and required additional actions before the integrated "
            "design interpretation."
        )
    )
    ttk.Label(
        design_tab,
        textvariable=design_status_var,
        wraplength=1180,
        justify=tk.LEFT,
    ).pack(fill=tk.X, pady=(8, 4))

    design_views = ttk.Notebook(design_tab)
    design_views.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
    design_summary_page = ttk.Frame(design_views, padding=6)
    design_selected_page = ttk.Frame(design_views, padding=6)
    design_capability_page = ttk.Frame(design_views, padding=6)
    design_views.add(design_summary_page, text="Design summary")
    design_views.add(design_selected_page, text="Selected girder")
    design_views.add(design_capability_page, text="Capability / verification")

    design_dashboard_frame = ttk.Frame(design_summary_page)
    design_dashboard_frame.pack(fill=tk.X, pady=(2, 8))
    design_worst_var = tk.StringVar(value="—")
    design_governing_var = tk.StringVar(value="—")
    design_blocker_var = tk.StringVar(value="—")
    for metric_index, (title, variable) in enumerate(
        (
            ("Worst utilization", design_worst_var),
            ("Governing girder", design_governing_var),
            ("Open blockers", design_blocker_var),
        )
    ):
        card = ttk.LabelFrame(
            design_dashboard_frame,
            text=title,
            style="Card.TLabelframe",
            padding=(12, 8),
        )
        card.grid(
            row=0,
            column=metric_index,
            sticky="ew",
            padx=(0 if metric_index == 0 else 4, 0),
        )
        design_dashboard_frame.columnconfigure(metric_index, weight=1)
        ttk.Label(card, textvariable=variable, style="Metric.TLabel").pack(anchor="w")

    design_chart_canvas = tk.Canvas(
        design_summary_page,
        height=150,
        background="#FFFFFF",
        highlightthickness=0,
    )
    design_chart_canvas.pack(fill=tk.X, pady=(0, 8))

    design_frame = ttk.LabelFrame(
        design_summary_page,
        text="Per-girder design results",
        padding=6,
    )
    design_frame.pack(fill=tk.BOTH, expand=True)
    design_columns = (
        "girder",
        "d",
        "med",
        "as_req",
        "bars",
        "mrd",
        "flex_util",
        "ved",
        "links",
        "shear_util",
        "wk",
        "crack_util",
        "defl",
        "defl_util",
        "gov_m",
        "gov_v",
        "construction",
        "status",
    )
    design_tree = ttk.Treeview(
        design_frame,
        columns=design_columns,
        show="headings",
        height=7,
    )
    design_headings = {
        "girder": "Girder",
        "d": "d (mm)",
        "med": "MEd (kNm)",
        "as_req": "As,req (mm²)",
        "bars": "Selected bars",
        "mrd": "MRd (kNm)",
        "flex_util": "M util.",
        "ved": "VEd (kN)",
        "links": "Selected links",
        "shear_util": "V util.",
        "wk": "wk (mm)",
        "crack_util": "Crack util.",
        "defl": "Defl. (mm)",
        "defl_util": "Defl. util.",
        "gov_m": "Governing M situation",
        "gov_v": "Governing V situation",
        "construction": "Construction stage",
        "status": "Current checks",
    }
    for key in design_columns:
        design_tree.heading(key, text=design_headings[key])
        design_tree.column(
            key,
            width=(
                105
                if key not in {
                    "bars",
                    "links",
                    "gov_m",
                    "gov_v",
                    "construction",
                    "status",
                }
                else 185
            ),
            anchor=(
                tk.CENTER
                if key not in {"gov_m", "gov_v", "construction", "status"}
                else tk.W
            ),
        )
    design_x_scroll = ttk.Scrollbar(
        design_frame,
        orient=tk.HORIZONTAL,
        command=design_tree.xview,
    )
    design_tree.configure(xscrollcommand=design_x_scroll.set)
    design_tree.pack(fill=tk.BOTH, expand=True)
    design_x_scroll.pack(fill=tk.X)

    design_review_frame = ttk.LabelFrame(
        design_selected_page,
        text="Selected girder / construction-stage review",
        style="Card.TLabelframe",
        padding=8,
    )
    design_review_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
    design_review_frame.columnconfigure(0, weight=2)
    design_review_frame.columnconfigure(1, weight=3)
    design_selected_var = tk.StringVar(
        value="Select a girder result to inspect its reinforcement and governing checks."
    )
    design_section_canvas = tk.Canvas(
        design_review_frame,
        height=185,
        background="#FFFFFF",
        highlightthickness=0,
    )
    design_section_canvas.grid(row=0, column=0, sticky="ew", padx=(0, 8))
    ttk.Label(
        design_review_frame,
        textvariable=design_selected_var,
        wraplength=520,
        justify=tk.LEFT,
    ).grid(row=1, column=0, sticky="nw", padx=(0, 8), pady=(5, 0))
    design_stage_tree = ttk.Treeview(
        design_review_frame,
        columns=("stage", "m", "v", "m_util", "v_util", "status"),
        show="headings",
        height=4,
    )
    for key, title, width_value in (
        ("stage", "Construction stage", 150),
        ("m", "MEd kNm", 95),
        ("v", "VEd kN", 95),
        ("m_util", "M util.", 80),
        ("v_util", "V util.", 80),
        ("status", "Status", 80),
    ):
        design_stage_tree.heading(key, text=title)
        design_stage_tree.column(key, width=width_value, anchor=tk.CENTER)
    design_stage_tree.grid(row=0, column=1, sticky="ew")
    design_show_calculation_button = ttk.Button(
        design_review_frame,
        text="Show selected girder calculations",
        style="Secondary.TButton",
    )
    design_show_calculation_button.grid(row=2, column=0, sticky="w", pady=(7, 0))

    capability_frame = ttk.LabelFrame(
        design_capability_page,
        text="Verification and capability boundary",
        padding=6,
    )
    capability_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
    capability_tree = ttk.Treeview(
        capability_frame,
        columns=("capability", "state", "detail"),
        show="headings",
        height=5,
    )
    capability_tree.heading("capability", text="Capability")
    capability_tree.heading("state", text="State")
    capability_tree.heading("detail", text="Engineering boundary")
    capability_tree.column("capability", width=280, anchor=tk.W)
    capability_tree.column("state", width=150, anchor=tk.CENTER)
    capability_tree.column("detail", width=760, anchor=tk.W)
    capability_tree.pack(fill=tk.X, expand=True)

    refresh_dashboard_button = ttk.Button(
        capability_frame,
        text="Refresh dashboard",
    )
    refresh_dashboard_button.pack(anchor=tk.E, pady=(6, 0))

    # ------------------------------------------------------------------
    # Deck & fatigue tab
    # ------------------------------------------------------------------
    local_tab.columnconfigure(0, weight=1)
    local_tab.columnconfigure(1, weight=1)
    local_tab.rowconfigure(3, weight=1)

    deck_controls = ttk.LabelFrame(
        local_tab,
        text="Native local deck/slab design",
        padding=8,
    )
    deck_controls.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
    deck_controls.columnconfigure(1, weight=1)
    add_entry(
        deck_controls,
        row=0,
        label="Load dispersion H/V ratio",
        key="deck_dispersion_ratio",
    )
    add_entry(
        deck_controls,
        row=1,
        label="Additional dispersion depth (m)",
        key="deck_additional_dispersion",
    )
    add_entry(
        deck_controls,
        row=2,
        label="Nominal slab bar dia. (mm)",
        key="deck_nominal_bar_diameter",
    )
    run_local_deck_button = ttk.Button(
        deck_controls,
        text="Run local deck design",
    )
    run_local_deck_button.grid(row=3, column=1, sticky="e", pady=(8, 0))

    fatigue_controls = ttk.LabelFrame(
        local_tab,
        text="Native FLM3 fatigue",
        padding=8,
    )
    fatigue_controls.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
    fatigue_controls.columnconfigure(1, weight=1)
    add_entry(
        fatigue_controls,
        row=0,
        label="FLM3 movement step (m)",
        key="fatigue_movement_step",
    )
    add_entry(
        fatigue_controls,
        row=1,
        label="FLM3 section step (m)",
        key="fatigue_section_step",
    )
    add_entry(
        fatigue_controls,
        row=2,
        label="FLM3 axle load factor",
        key="fatigue_axle_factor",
    )
    add_entry(
        fatigue_controls,
        row=3,
        label="Longitudinal λs (0 = required input)",
        key="fatigue_lambda_s",
    )
    add_entry(
        fatigue_controls,
        row=4,
        label="Longitudinal ΔσRsk (MPa; 0 = input needed)",
        key="fatigue_strength",
    )
    add_entry(
        fatigue_controls,
        row=5,
        label="Link λs (0 = required input)",
        key="fatigue_link_lambda_s",
    )
    add_entry(
        fatigue_controls,
        row=6,
        label="Link ΔσRsk (MPa; 0 = input needed)",
        key="fatigue_link_strength",
    )
    run_fatigue_button = ttk.Button(
        fatigue_controls,
        text="Run FLM3 fatigue",
    )
    run_fatigue_button.grid(row=7, column=1, sticky="e", pady=(8, 0))
    analysis_buttons.extend((run_local_deck_button, run_fatigue_button))

    local_dashboard_frame = ttk.Frame(local_tab)
    local_dashboard_frame.grid(
        row=1,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(8, 0),
    )
    local_bottom_var = tk.StringVar(value="Bottom: —")
    local_top_var = tk.StringVar(value="Top: —")
    local_shear_var = tk.StringVar(value="Shear: —")
    local_fatigue_var = tk.StringVar(value="Fatigue: —")
    for metric_index, (title, variable) in enumerate(
        (
            ("Bottom transverse", local_bottom_var),
            ("Top transverse", local_top_var),
            ("One-way shear", local_shear_var),
            ("FLM3", local_fatigue_var),
        )
    ):
        card = ttk.LabelFrame(
            local_dashboard_frame,
            text=title,
            style="Card.TLabelframe",
            padding=(10, 7),
        )
        card.grid(
            row=0,
            column=metric_index,
            sticky="ew",
            padx=(0 if metric_index == 0 else 4, 0),
        )
        local_dashboard_frame.columnconfigure(metric_index, weight=1)
        ttk.Label(card, textvariable=variable, style="CardTitle.TLabel").pack(anchor="w")

    local_chart_frame = ttk.LabelFrame(
        local_tab,
        text="Transverse deck response",
        style="Card.TLabelframe",
        padding=8,
    )
    local_chart_frame.grid(
        row=2,
        column=0,
        columnspan=2,
        sticky="ew",
        pady=(8, 0),
    )
    local_chart_canvas = tk.Canvas(
        local_chart_frame,
        height=210,
        background="#FFFFFF",
        highlightthickness=0,
    )
    local_chart_canvas.pack(fill=tk.X)

    local_result_frame = ttk.LabelFrame(
        local_tab,
        text="Deck / fatigue results",
        padding=8,
    )
    local_result_frame.grid(
        row=3,
        column=0,
        columnspan=2,
        sticky="nsew",
        pady=(8, 0),
    )
    local_result_tree = ttk.Treeview(
        local_result_frame,
        columns=("check", "result", "value", "status"),
        show="headings",
        height=15,
    )
    local_result_tree.heading("check", text="Check")
    local_result_tree.heading("result", text="Result")
    local_result_tree.heading("value", text="Value")
    local_result_tree.heading("status", text="Status / boundary")
    local_result_tree.column("check", width=190, anchor=tk.W)
    local_result_tree.column("result", width=230, anchor=tk.W)
    local_result_tree.column("value", width=210, anchor=tk.CENTER)
    local_result_tree.column("status", width=720, anchor=tk.W)
    local_result_tree.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Verification tab
    # ------------------------------------------------------------------
    verification_buttons = ttk.Frame(verification_tab, padding=(0, 0, 0, 6))
    verification_buttons.pack(fill=tk.X)
    html_button = ttk.Button(verification_buttons, text="Save HTML report")
    html_button.pack(side=tk.LEFT, padx=(0, 6))
    pdf_button = ttk.Button(verification_buttons, text="Save PDF report")
    pdf_button.pack(side=tk.LEFT, padx=6)
    print_button = ttk.Button(verification_buttons, text="Print / preview report")
    print_button.pack(side=tk.LEFT, padx=6)
    export_button = ttk.Button(
        verification_buttons,
        text="Export MIDAS / STAAD campaign",
        style="Primary.TButton",
    )
    export_button.pack(side=tk.LEFT, padx=(12, 6))

    verification_import_buttons = ttk.Frame(
        verification_tab,
        padding=(0, 0, 0, 8),
    )
    verification_import_buttons.pack(fill=tk.X)
    import_staad_button = ttk.Button(
        verification_import_buttons,
        text="Import STAAD .ANL",
    )
    import_staad_button.pack(side=tk.LEFT, padx=(0, 6))
    import_midas_button = ttk.Button(
        verification_import_buttons,
        text="Import MIDAS tables",
    )
    import_midas_button.pack(side=tk.LEFT, padx=6)
    save_verification_evidence_button = ttk.Button(
        verification_import_buttons,
        text="Save comparison evidence",
    )
    save_verification_evidence_button.pack(side=tk.LEFT, padx=6)
    analysis_buttons.extend(
        (
            html_button,
            pdf_button,
            print_button,
            export_button,
            import_staad_button,
            import_midas_button,
            save_verification_evidence_button,
        )
    )

    verification_views = ttk.Notebook(verification_tab)
    verification_views.pack(fill=tk.BOTH, expand=True)
    verification_results_page = ttk.Frame(verification_views, padding=8)
    verification_models_page = ttk.Frame(verification_views, padding=8)
    verification_scope_page = ttk.Frame(verification_views, padding=8)
    verification_views.add(verification_results_page, text="External comparison")
    verification_views.add(verification_models_page, text="Exported cases")
    verification_views.add(verification_scope_page, text="Acceptance scope")

    verification_dashboard_frame = ttk.Frame(verification_results_page)
    verification_dashboard_frame.pack(fill=tk.X, pady=(0, 6))
    verification_status_metric_var = tk.StringVar(value="NOT IMPORTED")
    verification_coverage_metric_var = tk.StringVar(value="—")
    verification_error_metric_var = tk.StringVar(value="—")
    for metric_index, (title, variable) in enumerate(
        (
            ("Comparison status", verification_status_metric_var),
            ("Imported coverage", verification_coverage_metric_var),
            ("Maximum relative error", verification_error_metric_var),
        )
    ):
        card = ttk.LabelFrame(
            verification_dashboard_frame,
            text=title,
            style="Card.TLabelframe",
            padding=(10, 7),
        )
        card.grid(
            row=0,
            column=metric_index,
            sticky="ew",
            padx=(0 if metric_index == 0 else 4, 0),
        )
        verification_dashboard_frame.columnconfigure(metric_index, weight=1)
        ttk.Label(card, textvariable=variable, style="CardTitle.TLabel").pack(anchor="w")

    verification_error_canvas = tk.Canvas(
        verification_results_page,
        height=165,
        background="#FFFFFF",
        highlightthickness=0,
    )
    verification_error_canvas.pack(fill=tk.X, pady=(4, 8))

    verification_result_tree = ttk.Treeview(
        verification_results_page,
        columns=("result", "kind", "status", "max_error", "source"),
        show="headings",
        height=9,
    )
    verification_result_tree.heading("result", text="Imported result")
    verification_result_tree.heading("kind", text="Type")
    verification_result_tree.heading("status", text="Comparison")
    verification_result_tree.heading("max_error", text="Max rel. error")
    verification_result_tree.heading("source", text="Source")
    verification_result_tree.column("result", width=390, anchor=tk.W)
    verification_result_tree.column("kind", width=120, anchor=tk.CENTER)
    verification_result_tree.column("status", width=120, anchor=tk.CENTER)
    verification_result_tree.column("max_error", width=130, anchor=tk.CENTER)
    verification_result_tree.column("source", width=160, anchor=tk.W)
    verification_result_tree.pack(fill=tk.BOTH, expand=True)

    package_tree = ttk.Treeview(
        verification_models_page,
        columns=("case", "purpose"),
        show="headings",
        height=14,
    )
    package_tree.heading("case", text="Governing case")
    package_tree.heading("purpose", text="Verification purpose")
    package_tree.column("case", width=150, anchor=tk.CENTER)
    package_tree.column("purpose", width=900, anchor=tk.W)
    package_tree.pack(fill=tk.BOTH, expand=True)

    verification_text = tk.Text(
        verification_scope_page,
        wrap="word",
        state=tk.DISABLED,
        relief="flat",
        padx=16,
        pady=14,
        background="#FFFFFF",
        foreground="#172033",
        font=("Segoe UI", 10),
    )
    verification_text.pack(fill=tk.BOTH, expand=True)

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
            gamma_q_nontraffic=float(
                string_vars["gamma_q_nontraffic"].get()
            ),
            psi1_traffic=float(string_vars["psi1_traffic"].get()),
            psi2_traffic=float(string_vars["psi2_traffic"].get()),
            psi1_lm2=float(string_vars["psi1_lm2"].get()),
            psi0_thermal_uls=float(
                string_vars["psi0_thermal_uls"].get()
            ),
            psi0_thermal_sls=float(
                string_vars["psi0_thermal_sls"].get()
            ),
            psi1_thermal=float(string_vars["psi1_thermal"].get()),
            psi2_thermal=float(string_vars["psi2_thermal"].get()),
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
        design = ApplicationDesignSettings(
            cover_mm=float(string_vars["design_cover"].get()),
            durability_minimum_cover_mm=float(
                string_vars["design_durability_cover"].get()
            ),
            cover_deviation_mm=float(
                string_vars["design_cover_deviation"].get()
            ),
            aggregate_size_mm=float(string_vars["design_aggregate"].get()),
            nominal_link_diameter_mm=float(
                string_vars["design_link_diameter"].get()
            ),
            crack_combination=SLSCombinationChoice(
                string_vars["design_crack_combination"].get()
            ),
            deflection_combination=SLSCombinationChoice(
                string_vars["design_deflection_combination"].get()
            ),
            creep_coefficient=float(string_vars["design_creep"].get()),
            deflection_beta=float(string_vars["design_beta"].get()),
            crack_kt=float(string_vars["design_crack_kt"].get()),
            cot_theta=float(string_vars["design_cot_theta"].get()),
        )
        actions = ExtendedActionSettings(
            braking_enabled=bool_vars["action_braking_enabled"].get(),
            braking_alpha_q1=float(string_vars["action_braking_alpha_q1"].get()),
            braking_alpha_Q1=float(string_vars["action_braking_alpha_Q1"].get()),
            braking_loaded_length_m=(
                None
                if not string_vars["action_braking_length"].get().strip()
                else displayed_unit.to_metres(
                    float(string_vars["action_braking_length"].get())
                )
            ),
            thermal_enabled=bool_vars["action_thermal_enabled"].get(),
            thermal_alpha_per_c=float(string_vars["action_thermal_alpha"].get()),
            thermal_uniform_expansion_delta_c=float(
                string_vars["action_thermal_expansion"].get()
            ),
            thermal_uniform_contraction_delta_c=float(
                string_vars["action_thermal_contraction"].get()
            ),
            thermal_gradient_heat_c=float(
                string_vars["action_thermal_gradient_heat"].get()
            ),
            thermal_gradient_cool_c=float(
                string_vars["action_thermal_gradient_cool"].get()
            ),
            thermal_longitudinal_restraint_fraction=float(
                string_vars["action_thermal_restraint"].get()
            ),
            pedestrian_enabled=bool_vars["action_pedestrian_enabled"].get(),
            pedestrian_load_kn_m2=float(string_vars["action_pedestrian_q"].get()),
            pedestrian_reduced_with_lm1_kn_m2=float(
                string_vars["action_pedestrian_reduced_q"].get()
            ),
            gr2_lm1_tandem_factor=float(
                string_vars["action_gr2_ts_factor"].get()
            ),
            gr2_lm1_udl_factor=float(
                string_vars["action_gr2_udl_factor"].get()
            ),
            left_footway_width_m=displayed_unit.to_metres(
                float(string_vars["action_left_footway"].get())
            ),
            right_footway_width_m=displayed_unit.to_metres(
                float(string_vars["action_right_footway"].get())
            ),
            lm2_enabled=bool_vars["action_lm2_enabled"].get(),
            lm2_beta_Q=float(string_vars["action_lm2_beta"].get()),
            lm2_longitudinal_step_m=displayed_unit.to_metres(
                float(string_vars["action_lm2_x_step"].get())
            ),
            lm2_transverse_step_m=displayed_unit.to_metres(
                float(string_vars["action_lm2_y_step"].get())
            ),
            barrier_impact_enabled=bool_vars["action_barrier_enabled"].get(),
            barrier_transverse_force_kn=float(
                string_vars["action_barrier_force"].get()
            ),
            barrier_load_height_m=float(
                string_vars["action_barrier_height"].get()
            ),
            barrier_vertical_factor=float(
                string_vars["action_barrier_vertical_factor"].get()
            ),
            barrier_alpha_Q1=float(
                string_vars["action_barrier_alpha_Q1"].get()
            ),
            bearing_longitudinal_capacity_per_bearing_kn=float(
                string_vars["action_bearing_force_capacity"].get()
            ),
            bearing_movement_capacity_mm=float(
                string_vars["action_bearing_movement_capacity"].get()
            ),
            barrier_transverse_resistance_kn=float(
                string_vars["action_barrier_transverse_resistance"].get()
            ),
            barrier_base_moment_resistance_knm=float(
                string_vars["action_barrier_moment_resistance"].get()
            ),
            wind_enabled=bool_vars["action_wind_enabled"].get(),
            wind_basic_velocity_m_s=float(
                string_vars["action_wind_velocity"].get()
            ),
            wind_air_density_kg_m3=float(
                string_vars["action_wind_density"].get()
            ),
            wind_exposure_factor=float(
                string_vars["action_wind_exposure"].get()
            ),
            wind_transverse_force_coefficient=float(
                string_vars["action_wind_transverse_cf"].get()
            ),
            wind_vertical_force_coefficient=float(
                string_vars["action_wind_vertical_cf"].get()
            ),
            wind_loaded_height_m=float(
                string_vars["action_wind_height"].get()
            ),
            bearing_transverse_capacity_per_bearing_kn=float(
                string_vars["action_bearing_transverse_capacity"].get()
            ),
            construction_enabled=bool_vars["action_construction_enabled"].get(),
            construction_execution_udl_kn_m2=float(
                string_vars["action_construction_udl"].get()
            ),
        )
        local_deck = LocalDeckSettings(
            load_dispersion_horizontal_per_vertical=float(
                string_vars["deck_dispersion_ratio"].get()
            ),
            additional_dispersion_depth_m=float(
                string_vars["deck_additional_dispersion"].get()
            ),
            nominal_bar_diameter_mm=float(
                string_vars["deck_nominal_bar_diameter"].get()
            ),
        )
        fatigue = FatigueApplicationSettings(
            movement_step_m=float(string_vars["fatigue_movement_step"].get()),
            section_step_m=float(string_vars["fatigue_section_step"].get()),
            axle_load_factor=float(string_vars["fatigue_axle_factor"].get()),
            lambda_s=float(string_vars["fatigue_lambda_s"].get()),
            characteristic_fatigue_strength_mpa=float(
                string_vars["fatigue_strength"].get()
            ),
            shear_link_lambda_s=float(
                string_vars["fatigue_link_lambda_s"].get()
            ),
            shear_link_characteristic_fatigue_strength_mpa=float(
                string_vars["fatigue_link_strength"].get()
            ),
        )
        return ApplicationPreferences(
            units=new_units,
            eurocode=basis,
            analysis=analysis,
            design=design,
            actions=actions,
            local_deck=local_deck,
            fatigue=fatigue,
        )

    def load_case_fields_from_form() -> ApplicationLoadCaseFields:
        def nonnegative_float(key: str) -> float:
            value = float(string_vars[key].get() or 0.0)
            if value < 0.0:
                raise ValueError(f"{key} cannot be negative.")
            return value

        def optional_position_m(key: str) -> float | None:
            value = string_vars[key].get().strip()
            return None if not value else displayed_unit.to_metres(float(value))

        return ApplicationLoadCaseFields(
            surfacing_thickness_m=displayed_unit.to_metres(
                nonnegative_float("load_surfacing_thickness")
            ),
            surfacing_density_kn_m3=nonnegative_float("load_surfacing_density"),
            surfacing_extent=SurfacingExtent(
                string_vars["load_surfacing_extent"].get()
            ),
            left_barrier_kn_m=nonnegative_float("load_left_barrier"),
            right_barrier_kn_m=nonnegative_float("load_right_barrier"),
            left_services_kn_m=nonnegative_float("load_left_services"),
            right_services_kn_m=nonnegative_float("load_right_services"),
            left_services_y_m=optional_position_m("load_left_services_y"),
            right_services_y_m=optional_position_m("load_right_services_y"),
        )

    def set_optional_length(key: str, value_m: float | None) -> None:
        if value_m is None:
            string_vars[key].set("")
        else:
            string_vars[key].set(f"{displayed_unit.from_metres(value_m):g}")

    def refresh_project_preview(_event=None) -> None:
        draw_bridge_preview(
            project_preview_canvas,
            bridge_preview_data(session.project),
        )

    def refresh_analysis_chart(_event=None) -> None:
        result = session.last_lm1_search
        if result is None:
            draw_line_chart(
                analysis_chart_canvas,
                x_values=(),
                series=(),
                title="Governing longitudinal response",
                y_unit="",
            )
            return
        metric = analysis_chart_metric_var.get()
        raw_girder = analysis_chart_girder_var.get().strip().upper()
        try:
            girder_index = int(raw_girder.removeprefix("G"))
        except ValueError:
            girder_index = 1
        try:
            diagram = analysis_girder_diagram(
                result,
                girder_index=girder_index,
                metric=metric,
            )
        except (ValueError, RuntimeError):
            draw_line_chart(
                analysis_chart_canvas,
                x_values=(),
                series=(),
                title=f"Governing {metric.lower()} diagram",
                y_unit="",
            )
            return
        draw_line_chart(
            analysis_chart_canvas,
            x_values=diagram.stations_m,
            series=((f"G{girder_index} · case {diagram.case_id}", diagram.values),),
            title=f"LM1 governing {diagram.metric.lower()} diagram",
            y_unit=diagram.unit,
        )

    def refresh_design_dashboard(_event=None) -> None:
        result = session.last_design_interpretation
        if result is None:
            design_worst_var.set("—")
            design_governing_var.set("—")
            design_blocker_var.set("—")
            draw_bar_chart(
                design_chart_canvas,
                labels=(),
                values=(),
                title="Governing design utilization by girder",
                unit="utilization",
                threshold=1.0,
            )
            return
        dashboard = design_dashboard_data(result)
        design_worst_var.set(f"{dashboard.worst_utilization:.3f}")
        design_governing_var.set(
            "—"
            if dashboard.governing_girder_index is None
            else f"G{dashboard.governing_girder_index}"
        )
        design_blocker_var.set(str(dashboard.blocker_count))
        draw_bar_chart(
            design_chart_canvas,
            labels=[f"G{item.girder_index}" for item in dashboard.girders],
            values=[item.governing_utilization for item in dashboard.girders],
            title="Governing ULS/SLS utilization by girder",
            unit="utilization",
            threshold=1.0,
        )

    def refresh_local_dashboard(_event=None) -> None:
        deck = session.last_local_deck_design
        fatigue = session.last_fatigue
        if deck is None:
            local_bottom_var.set("Bottom: —")
            local_top_var.set("Top: —")
            local_shear_var.set("Shear: —")
            local_fatigue_var.set(
                "Fatigue: —" if fatigue is None else f"Fatigue: {fatigue.status}"
            )
            draw_line_chart(
                local_chart_canvas,
                x_values=(),
                series=(),
                title="Transverse deck moment response",
                y_unit="kNm/m",
            )
            return
        dashboard = deck_dashboard_data(deck, fatigue)
        local_bottom_var.set(
            f"{dashboard.bottom_reinforcement} · util {dashboard.bottom_utilization:.3f}"
        )
        local_top_var.set(
            f"{dashboard.top_reinforcement} · util {dashboard.top_utilization:.3f}"
        )
        local_shear_var.set(f"util {dashboard.shear_utilization:.3f}")
        local_fatigue_var.set(dashboard.fatigue_status)
        series = [
            ("Permanent", dashboard.permanent_moments_knm_per_m),
        ]
        if dashboard.lm2_moments_knm_per_m is not None:
            series.append(("Governing LM2", dashboard.lm2_moments_knm_per_m))
        draw_line_chart(
            local_chart_canvas,
            x_values=dashboard.stations_y_m,
            series=tuple(series),
            title="Transverse deck moment response",
            y_unit="kNm/m",
        )

    def refresh_verification_dashboard(_event=None) -> None:
        report = session.last_verification_import
        if report is None:
            verification_status_metric_var.set("NOT IMPORTED")
            verification_coverage_metric_var.set("—")
            verification_error_metric_var.set("—")
            draw_bar_chart(
                verification_error_canvas,
                labels=(),
                values=(),
                title="External-result relative error",
                unit="%",
            )
            return
        dashboard = verification_dashboard_data(report)
        verification_status_metric_var.set(dashboard.status)
        verification_coverage_metric_var.set(
            f"{dashboard.imported_count}/{dashboard.requested_count}"
        )
        verification_error_metric_var.set(
            "—"
            if dashboard.max_relative_error is None
            else f"{100.0 * dashboard.max_relative_error:.3f}%"
        )
        draw_bar_chart(
            verification_error_canvas,
            labels=[str(item.result_id) for item in dashboard.results],
            values=[
                0.0
                if item.max_relative_error is None
                else 100.0 * item.max_relative_error
                for item in dashboard.results
            ],
            title=f"{dashboard.source_name} maximum relative error by result set",
            unit="%",
        )

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
        composite_guidance = ""
        if (
            project.geometry.girder_profile is not None
            and project.geometry.composite_flange_depth_m > 0.0
        ):
            slab_widths = girder_tributary_slab_widths_m(project.geometry)
            representative_width = max(slab_widths)
            description = composite_section_description(
                project.geometry,
                slab_width_m=representative_width,
                slab_width_basis="representative interior tributary slab width",
            )
            false_slab_depth_mm = (
                1000.0
                * float(
                    project.geometry.deck_construction.precast_false_slab_depth_m
                )
            )
            false_slab_note = (
                f"{false_slab_depth_mm:g} mm false slab remains weight-only "
                "in stiffness."
                if description.false_slab_weight_only
                else (
                    f"{false_slab_depth_mm:g} mm false slab is included in "
                    "composite stiffness."
                )
            )
            composite_guidance = (
                f" Precast {description.precast_section_type} section → final composite "
                f"{description.final_section_form}-section; participating deck flange "
                f"{description.flange_width_m:.3f} m × "
                f"{description.participating_flange_depth_m:.3f} m; "
                f"overall physical depth = {description.overall_depth_m:.3f} m. "
                f"{false_slab_note}"
            )
        guidance_var.set(
            "Layout guidance: "
            f"edge overhang = {layout.implied_edge_overhang_m:.3f} m; "
            f"minimum deck width for current girder lines = "
            f"{layout.minimum_deck_width_m:.3f} m."
            + composite_guidance
        )
        refresh_project_preview()

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
        string_vars["gamma_q_nontraffic"].set(
            f"{basis.gamma_q_nontraffic:g}"
        )
        string_vars["psi1_traffic"].set(f"{basis.psi1_traffic:g}")
        string_vars["psi2_traffic"].set(f"{basis.psi2_traffic:g}")
        string_vars["psi1_lm2"].set(f"{basis.psi1_lm2:g}")
        string_vars["psi0_thermal_uls"].set(
            f"{basis.psi0_thermal_uls:g}"
        )
        string_vars["psi0_thermal_sls"].set(
            f"{basis.psi0_thermal_sls:g}"
        )
        string_vars["psi1_thermal"].set(f"{basis.psi1_thermal:g}")
        string_vars["psi2_thermal"].set(f"{basis.psi2_thermal:g}")
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
        design = preferences.design
        string_vars["design_cover"].set(f"{design.cover_mm:g}")
        string_vars["design_durability_cover"].set(
            f"{design.durability_minimum_cover_mm:g}"
        )
        string_vars["design_cover_deviation"].set(
            f"{design.cover_deviation_mm:g}"
        )
        string_vars["design_aggregate"].set(f"{design.aggregate_size_mm:g}")
        string_vars["design_link_diameter"].set(
            f"{design.nominal_link_diameter_mm:g}"
        )
        string_vars["design_crack_combination"].set(
            design.crack_combination.value
        )
        string_vars["design_deflection_combination"].set(
            design.deflection_combination.value
        )
        string_vars["design_creep"].set(f"{design.creep_coefficient:g}")
        string_vars["design_beta"].set(f"{design.deflection_beta:g}")
        string_vars["design_crack_kt"].set(f"{design.crack_kt:g}")
        string_vars["design_cot_theta"].set(f"{design.cot_theta:g}")
        actions = preferences.actions
        bool_vars["action_braking_enabled"].set(actions.braking_enabled)
        string_vars["action_braking_alpha_q1"].set(
            f"{actions.braking_alpha_q1:g}"
        )
        string_vars["action_braking_alpha_Q1"].set(
            f"{actions.braking_alpha_Q1:g}"
        )
        string_vars["action_braking_length"].set(
            ""
            if actions.braking_loaded_length_m is None
            else f"{displayed_unit.from_metres(actions.braking_loaded_length_m):g}"
        )
        bool_vars["action_thermal_enabled"].set(actions.thermal_enabled)
        string_vars["action_thermal_alpha"].set(f"{actions.thermal_alpha_per_c:g}")
        string_vars["action_thermal_expansion"].set(
            f"{actions.thermal_uniform_expansion_delta_c:g}"
        )
        string_vars["action_thermal_contraction"].set(
            f"{actions.thermal_uniform_contraction_delta_c:g}"
        )
        string_vars["action_thermal_gradient_heat"].set(
            f"{actions.thermal_gradient_heat_c:g}"
        )
        string_vars["action_thermal_gradient_cool"].set(
            f"{actions.thermal_gradient_cool_c:g}"
        )
        string_vars["action_thermal_restraint"].set(
            f"{actions.thermal_longitudinal_restraint_fraction:g}"
        )
        bool_vars["action_pedestrian_enabled"].set(actions.pedestrian_enabled)
        string_vars["action_pedestrian_q"].set(
            f"{actions.pedestrian_load_kn_m2:g}"
        )
        string_vars["action_pedestrian_reduced_q"].set(
            f"{actions.pedestrian_reduced_with_lm1_kn_m2:g}"
        )
        string_vars["action_gr2_ts_factor"].set(
            f"{actions.gr2_lm1_tandem_factor:g}"
        )
        string_vars["action_gr2_udl_factor"].set(
            f"{actions.gr2_lm1_udl_factor:g}"
        )
        string_vars["action_left_footway"].set(
            f"{displayed_unit.from_metres(actions.left_footway_width_m):g}"
        )
        string_vars["action_right_footway"].set(
            f"{displayed_unit.from_metres(actions.right_footway_width_m):g}"
        )
        bool_vars["action_lm2_enabled"].set(actions.lm2_enabled)
        string_vars["action_lm2_beta"].set(f"{actions.lm2_beta_Q:g}")
        string_vars["action_lm2_x_step"].set(
            f"{displayed_unit.from_metres(actions.lm2_longitudinal_step_m):g}"
        )
        string_vars["action_lm2_y_step"].set(
            f"{displayed_unit.from_metres(actions.lm2_transverse_step_m):g}"
        )
        bool_vars["action_barrier_enabled"].set(actions.barrier_impact_enabled)
        string_vars["action_barrier_force"].set(
            f"{actions.barrier_transverse_force_kn:g}"
        )
        string_vars["action_barrier_height"].set(
            f"{actions.barrier_load_height_m:g}"
        )
        string_vars["action_barrier_vertical_factor"].set(
            f"{actions.barrier_vertical_factor:g}"
        )
        string_vars["action_barrier_alpha_Q1"].set(
            f"{actions.barrier_alpha_Q1:g}"
        )
        string_vars["action_bearing_force_capacity"].set(
            f"{actions.bearing_longitudinal_capacity_per_bearing_kn:g}"
        )
        string_vars["action_bearing_movement_capacity"].set(
            f"{actions.bearing_movement_capacity_mm:g}"
        )
        string_vars["action_barrier_transverse_resistance"].set(
            f"{actions.barrier_transverse_resistance_kn:g}"
        )
        string_vars["action_barrier_moment_resistance"].set(
            f"{actions.barrier_base_moment_resistance_knm:g}"
        )
        bool_vars["action_wind_enabled"].set(actions.wind_enabled)
        string_vars["action_wind_velocity"].set(
            f"{actions.wind_basic_velocity_m_s:g}"
        )
        string_vars["action_wind_density"].set(
            f"{actions.wind_air_density_kg_m3:g}"
        )
        string_vars["action_wind_exposure"].set(
            f"{actions.wind_exposure_factor:g}"
        )
        string_vars["action_wind_transverse_cf"].set(
            f"{actions.wind_transverse_force_coefficient:g}"
        )
        string_vars["action_wind_vertical_cf"].set(
            f"{actions.wind_vertical_force_coefficient:g}"
        )
        string_vars["action_wind_height"].set(
            f"{actions.wind_loaded_height_m:g}"
        )
        string_vars["action_bearing_transverse_capacity"].set(
            f"{actions.bearing_transverse_capacity_per_bearing_kn:g}"
        )
        bool_vars["action_construction_enabled"].set(actions.construction_enabled)
        string_vars["action_construction_udl"].set(
            f"{actions.construction_execution_udl_kn_m2:g}"
        )
        deck = preferences.local_deck
        string_vars["deck_dispersion_ratio"].set(
            f"{deck.load_dispersion_horizontal_per_vertical:g}"
        )
        string_vars["deck_additional_dispersion"].set(
            f"{deck.additional_dispersion_depth_m:g}"
        )
        string_vars["deck_nominal_bar_diameter"].set(
            f"{deck.nominal_bar_diameter_mm:g}"
        )
        fatigue = preferences.fatigue
        string_vars["fatigue_movement_step"].set(
            f"{fatigue.movement_step_m:g}"
        )
        string_vars["fatigue_section_step"].set(
            f"{fatigue.section_step_m:g}"
        )
        string_vars["fatigue_axle_factor"].set(
            f"{fatigue.axle_load_factor:g}"
        )
        string_vars["fatigue_lambda_s"].set(f"{fatigue.lambda_s:g}")
        string_vars["fatigue_strength"].set(
            f"{fatigue.characteristic_fatigue_strength_mpa:g}"
        )
        string_vars["fatigue_link_lambda_s"].set(
            f"{fatigue.shear_link_lambda_s:g}"
        )
        string_vars["fatigue_link_strength"].set(
            f"{fatigue.shear_link_characteristic_fatigue_strength_mpa:g}"
        )

    def populate_load_cases(project) -> None:
        fields = ApplicationLoadCaseFields.from_project(project)
        string_vars["load_surfacing_thickness"].set(
            f"{displayed_unit.from_metres(fields.surfacing_thickness_m):g}"
        )
        string_vars["load_surfacing_density"].set(
            f"{fields.surfacing_density_kn_m3:g}"
        )
        string_vars["load_surfacing_extent"].set(fields.surfacing_extent.value)
        string_vars["load_left_barrier"].set(f"{fields.left_barrier_kn_m:g}")
        string_vars["load_right_barrier"].set(f"{fields.right_barrier_kn_m:g}")
        string_vars["load_left_services"].set(f"{fields.left_services_kn_m:g}")
        string_vars["load_right_services"].set(f"{fields.right_services_kn_m:g}")
        string_vars["load_left_services_y"].set(
            ""
            if fields.left_services_y_m is None
            else f"{displayed_unit.from_metres(fields.left_services_y_m):g}"
        )
        string_vars["load_right_services_y"].set(
            ""
            if fields.right_services_y_m is None
            else f"{displayed_unit.from_metres(fields.right_services_y_m):g}"
        )

    def refresh_permanent_load_chart(_event=None) -> None:
        audit_rows = session.permanent_load_audit()
        refresh_permanent_load_chart()

    def refresh_load_case_views() -> None:
        for item in permanent_audit_tree.get_children():
            permanent_audit_tree.delete(item)
        audit_rows = session.permanent_load_audit()
        for row in audit_rows:
            permanent_audit_tree.insert(
                "",
                tk.END,
                values=(
                    row.girder_index,
                    f"{row.girder_self_weight_kn_m:.3f}",
                    f"{row.false_slab_kn_m:.3f}",
                    f"{row.in_situ_slab_kn_m:.3f}",
                    f"{row.surfacing_kn_m:.3f}",
                    f"{row.barriers_kn_m:.3f}",
                    f"{row.services_kn_m:.3f}",
                    f"{row.other_kn_m:.3f}",
                    f"{row.total_equivalent_kn_m:.3f}",
                ),
            )
        draw_bar_chart(
            permanent_load_canvas,
            labels=[f"G{row.girder_index}" for row in audit_rows],
            values=[row.total_equivalent_kn_m for row in audit_rows],
            title="Characteristic permanent line load by girder",
            unit="kN/m",
        )

        for item in action_scope_tree.get_children():
            action_scope_tree.delete(item)
        for action in eurocode_variable_action_scope():
            action_scope_tree.insert(
                "",
                tk.END,
                values=(action.name, action.status, action.detail),
            )

        for item in combination_tree.get_children():
            combination_tree.delete(item)
        if session.last_lm1_search is None:
            return
        try:
            combinations = session.combination_summary()
        except (TypeError, ValueError, RuntimeError):
            return
        for row in combinations:
            combination_tree.insert(
                "",
                tk.END,
                values=(
                    row.girder_index,
                    f"{row.permanent_characteristic.moment_knm:.2f}",
                    f"{row.traffic_characteristic.moment_knm:.2f}",
                    f"{row.uls.moment_knm:.2f}",
                    f"{row.permanent_characteristic.shear_kn:.2f}",
                    f"{row.traffic_characteristic.shear_kn:.2f}",
                    f"{row.uls.shear_kn:.2f}",
                    f"{row.sls_characteristic.moment_knm:.2f}",
                    f"{row.sls_frequent.moment_knm:.2f}",
                    f"{row.sls_quasi_permanent.moment_knm:.2f}",
                ),
            )

    def clear_results() -> None:
        for tree in (
            effect_tree,
            deflection_tree,
            package_tree,
            verification_result_tree,
            combination_tree,
            design_tree,
            action_result_tree,
            local_result_tree,
            calculation_tree,
        ):
            for item in tree.get_children():
                tree.delete(item)
        search_status_var.set("No native LM1 analysis has been run.")
        design_status_var.set(
            "Run native LM1 and required additional actions + wind before the "
            "integrated design interpretation, or use Run Full Analysis & Design."
        )
        calculation_item_map.clear()
        _set_text(
            calculation_detail,
            "Run analysis, then open Calculations to review the deterministic "
            "equation/substitution/result trace.",
        )
        for variable in analysis_metric_vars.values():
            variable.set("—")
        design_selected_var.set(
            "Select a girder result to inspect its reinforcement and governing checks."
        )
        for item in design_stage_tree.get_children():
            design_stage_tree.delete(item)
        design_section_canvas.delete("all")
        refresh_analysis_chart()
        refresh_design_dashboard()
        refresh_local_dashboard()
        refresh_verification_dashboard()

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

        dashboard = analysis_dashboard_data(result)
        girder_values = tuple(f"G{item.girder_index}" for item in dashboard.girders)
        analysis_chart_girder.configure(values=girder_values)
        if analysis_chart_girder_var.get() not in girder_values and girder_values:
            analysis_chart_girder_var.set(girder_values[0])
        analysis_metric_vars["moment"].set(f"{dashboard.max_moment_knm:.2f} kNm")
        analysis_metric_vars["shear"].set(f"{dashboard.max_shear_kn:.2f} kN")
        analysis_metric_vars["torsion"].set(f"{dashboard.max_torsion_knm:.2f} kNm")
        analysis_metric_vars["deflection"].set(
            "—"
            if dashboard.max_deflection_mm is None
            else f"{dashboard.max_deflection_mm:.3f} mm"
        )
        refresh_analysis_chart()

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
            f"{result.search_strategy}; factorized "
            f"{result.prepared_structure_count} structural system(s), reused "
            f"{result.reused_factorization_solve_count} solve(s), and retained "
            f"{result.retained_case_count} governing case model(s)."
        )
        progress["value"] = 100.0
        status_var.set("Native LM1 analysis complete.")
        refresh_load_case_views()
        refresh_dashboard()

    def show_extended_action_result(result) -> None:
        for item in action_result_tree.get_children():
            action_result_tree.delete(item)

        def add(action: str, name: str, value: str, scope: str) -> None:
            action_result_tree.insert(
                "",
                tk.END,
                values=(action, name, value, scope),
            )

        if result.braking is not None:
            item = result.braking
            add(
                "Braking / acceleration",
                "Characteristic Qlk",
                f"{item.characteristic_force_kn:.2f} kN",
                item.status,
            )
            add(
                "Braking / acceleration",
                "Loaded length",
                f"{item.loaded_length_m:.3f} m",
                "Both longitudinal signs are required.",
            )

        if result.thermal is not None:
            item = result.thermal
            add(
                "Thermal",
                "Free expansion / contraction",
                (
                    f"+{item.expansion_movement_mm:.2f} / "
                    f"-{item.contraction_movement_mm:.2f} mm"
                ),
                item.status,
            )
            add(
                "Thermal",
                "Gradient free midspan",
                (
                    f"heat {item.heat_gradient_free_midspan_mm:.2f} mm; "
                    f"cool {item.cool_gradient_free_midspan_mm:.2f} mm"
                ),
                (
                    "Linear free-curvature reference; continuity/restraint changes "
                    "the structural effects."
                ),
            )
            add(
                "Thermal",
                "Modelled restraint force",
                (
                    f"exp {item.modelled_restraint_expansion_force_kn:.1f} kN; "
                    f"con {item.modelled_restraint_contraction_force_kn:.1f} kN"
                ),
                (
                    "Input incomplete: set project climate ranges."
                    if not item.climate_input_complete
                    else "Uses the entered longitudinal restraint fraction."
                ),
            )

        if result.gr2_frequent_lm1 is not None:
            item = result.gr2_frequent_lm1
            add(
                "Braking / acceleration",
                "gr2 frequent LM1 search",
                f"{item.search.evaluated_case_count:,} cases",
                (
                    f"TS factor={item.tandem_factor:g}; "
                    f"UDL factor={item.udl_factor:g}. {item.status}"
                ),
            )

        if result.pedestrian is not None:
            item = result.pedestrian
            add(
                "Pedestrian / footway",
                "Characteristic total load",
                f"{item.total_characteristic_load_kn:.2f} kN",
                item.status,
            )
            if item.girders:
                maximum = max(
                    row.effects.moment_knm for row in item.girders
                )
                add(
                    "Pedestrian / footway",
                    "Maximum girder |M|",
                    f"{maximum:.2f} kNm",
                    "Native final-stage vertical grillage.",
                )

        if result.lm2 is not None:
            item = result.lm2
            add(
                "LM2",
                "Axle / wheel",
                f"{item.axle_load_kn:.1f} / {item.wheel_load_kn:.1f} kN",
                item.status,
            )
            add(
                "LM2",
                "Wheel contact pressure",
                f"{item.contact_pressure_kn_m2:.1f} kN/m²",
                "0.35 m × 0.60 m contact patch retained for local slab design.",
            )
            add(
                "LM2",
                "Evaluated placements",
                f"{item.evaluated_case_count:,}",
                "Longitudinal/transverse scan across the carriageway.",
            )
            if item.girders:
                maximum = max(
                    row.effects.moment_knm for row in item.girders
                )
                add(
                    "LM2",
                    "Maximum girder |M|",
                    f"{maximum:.2f} kNm",
                    "Global grillage response; local plate/punching check remains separate.",
                )

        if result.barrier_impact is not None:
            item = result.barrier_impact
            add(
                "Safety-barrier impact",
                "Transverse accidental force",
                f"{item.transverse_characteristic_force_kn:.1f} kN",
                item.status,
            )
            add(
                "Safety-barrier impact",
                "Base moment / vertical wheel",
                (
                    f"{item.barrier_base_moment_knm:.1f} kNm / "
                    f"{item.accompanying_vertical_wheel_load_kn:.1f} kN"
                ),
                "Local barrier anchorage/deck-edge demand; horizontal solver not invented.",
            )

        if result.wind is not None:
            item = result.wind
            add(
                "Wind",
                "Static transverse resultant",
                f"{item.transverse_characteristic_force_kn:.1f} kN",
                item.status,
            )
            add(
                "Wind",
                "Effective pressure",
                f"{item.effective_pressure_kn_m2:.3f} kN/m²",
                (
                    "Input incomplete: enter project/basic wind speed."
                    if not item.input_complete
                    else f"v={item.basic_velocity_m_s:.2f} m/s; projected height "
                    f"{item.projected_height_m:.3f} m"
                ),
            )
            if abs(item.vertical_characteristic_force_kn) > 1.0e-9:
                add(
                    "Wind",
                    "Vertical resultant",
                    f"{item.vertical_characteristic_force_kn:.1f} kN",
                    "Optional vertical coefficient input; review sign/direction for the project.",
                )

        if result.construction is not None:
            for stage in ("precast_girder", "deck_construction", "superimposed"):
                rows = [
                    row
                    for row in result.construction.girders
                    if row.stage.value == stage
                ]
                if not rows:
                    continue
                add(
                    "Construction stage",
                    stage,
                    (
                        f"max M={max(row.characteristic_max_moment_knm for row in rows):.2f} "
                        f"kNm; max |V|={max(row.characteristic_max_abs_shear_kn for row in rows):.2f} kN"
                    ),
                    rows[0].status,
                )

        unresolved = result.unresolved_inputs
        status_var.set(
            "Required actions + wind complete."
            if not unresolved
            else "Actions + wind calculated; project inputs remain: "
            + ", ".join(unresolved)
        )
        refresh_dashboard()

    def run_extended_action_suite() -> None:
        try:
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Additional actions", str(exc))
            return

        run_actions_button.configure(state=tk.DISABLED)
        started_at = time.monotonic()
        status_var.set(
            "Running braking, thermal, pedestrian, LM2, barrier, construction and wind actions..."
        )

        def gr2_progress(completed: int, total: int) -> None:
            if total <= 0:
                return
            root.after(
                0,
                lambda: (
                    progress.configure(value=50.0 * completed / total),
                    status_var.set(
                        f"gr2 frequent-LM1 case {completed:,}/{total:,} — "
                        f"{100.0 * completed / total:.1f}% of gr2 search"
                    ),
                ),
            )

        def lm2_progress(completed: int, total: int) -> None:
            if total <= 0:
                return
            root.after(
                0,
                lambda: (
                    progress.configure(value=50.0 + 50.0 * completed / total),
                    status_var.set(
                        f"LM2 placement {completed:,}/{total:,} — "
                        f"{100.0 * completed / total:.1f}%"
                    ),
                ),
            )

        def worker() -> None:
            try:
                result = session.run_extended_actions(
                    lm2_progress_callback=lm2_progress,
                    gr2_progress_callback=gr2_progress,
                )
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                message = str(exc)

                def failed() -> None:
                    run_actions_button.configure(state=tk.NORMAL)
                    status_var.set("Additional actions failed.")
                    messagebox.showerror("Additional actions", message)

                root.after(0, failed)
                return

            def complete() -> None:
                run_actions_button.configure(state=tk.NORMAL)
                progress["value"] = 100.0
                show_extended_action_result(result)
                elapsed = time.monotonic() - started_at
                status_var.set(
                    f"Actions + wind complete in {format_duration(elapsed)}"
                    + (
                        ""
                        if not result.unresolved_inputs
                        else "; inputs still required: "
                        + ", ".join(result.unresolved_inputs)
                    )
                )

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def _clear_local_results() -> None:
        for item in local_result_tree.get_children():
            local_result_tree.delete(item)

    def show_local_deck_result(result) -> None:
        _clear_local_results()
        local_result_tree.insert(
            "",
            tk.END,
            values=(
                "Local deck",
                "ULS positive / negative transverse moment",
                (
                    f"+{result.uls_positive_moment_knm_per_m:.2f} / "
                    f"-{result.uls_negative_moment_knm_per_m:.2f} kNm/m"
                ),
                result.status,
            ),
        )
        local_result_tree.insert(
            "",
            tk.END,
            values=(
                "Local deck",
                "Barrier accidental + / - moment",
                (
                    f"+{result.accidental_positive_moment_knm_per_m:.2f} / "
                    f"-{result.accidental_negative_moment_knm_per_m:.2f} kNm/m"
                ),
                "Gk + accidental accompanying vertical wheel local strip response.",
            ),
        )
        local_result_tree.insert(
            "",
            tk.END,
            values=(
                "Local deck shear",
                "One-way transverse strip",
                (
                    f"VEd={result.one_way_shear.design_shear_kn_per_m:.2f} kN/m; "
                    f"VRdc={result.one_way_shear.concrete_resistance_kn_per_m:.2f} kN/m; "
                    f"util={result.one_way_shear.utilization:.3f}"
                ),
                result.one_way_shear.status,
            ),
        )
        for reinforcement in (
            result.bottom_transverse,
            result.top_transverse,
        ):
            local_result_tree.insert(
                "",
                tk.END,
                values=(
                    "Local deck reinforcement",
                    reinforcement.face,
                    (
                        f"{reinforcement.arrangement.label}; "
                        f"As={reinforcement.arrangement.provided_area_mm2_per_m:.0f} mm²/m; "
                        f"util={reinforcement.utilization:.3f}"
                    ),
                    reinforcement.status,
                ),
            )
        status_var.set("Local deck/slab design complete.")
        refresh_local_dashboard()
        refresh_dashboard()

    def run_local_deck_workflow() -> None:
        try:
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Local deck design", str(exc))
            return

        def completed(result, elapsed: float) -> None:
            show_local_deck_result(result)
            record = session.last_performance_record
            cache_text = " (cached)" if record is not None and record.cache_hit else ""
            status_var.set(
                f"Local deck/slab design complete in {format_duration(elapsed)}{cache_text}."
            )

        run_background_operation(
            title="Local deck design",
            status="Running local deck/slab analysis and design...",
            operation=session.run_local_deck_design,
            on_success=completed,
        )

    def show_fatigue_result(result, *, clear: bool = True) -> None:
        if clear:
            _clear_local_results()
        local_result_tree.insert(
            "",
            tk.END,
            values=(
                "FLM3",
                "Native search",
                (
                    f"{len(result.search.cases):,} cases; "
                    f"{len(result.search.vehicle_centres_y_m)} transverse vehicle line(s)"
                ),
                result.status,
            ),
        )
        for row in result.girders:
            steel = row.fatigue.reinforcement
            local_result_tree.insert(
                "",
                tk.END,
                values=(
                    f"Girder {row.girder_index}",
                    "Longitudinal reinforcement fatigue",
                    (
                        f"Δσ={row.reference_steel_stress_range_mpa:.2f} MPa; "
                        f"util={steel.utilization:.3f}"
                    ),
                    "PASS" if steel.passes else "CHECK",
                ),
            )
            if row.fatigue.concrete is not None:
                concrete = row.fatigue.concrete
                local_result_tree.insert(
                    "",
                    tk.END,
                    values=(
                        f"Girder {row.girder_index}",
                        "Concrete compression fatigue",
                        f"util={concrete.utilization:.3f}",
                        "PASS" if concrete.passes else "CHECK",
                    ),
                )
            if row.shear_links is not None:
                links = row.shear_links.fatigue
                local_result_tree.insert(
                    "",
                    tk.END,
                    values=(
                        f"Girder {row.girder_index}",
                        "Vertical-link fatigue",
                        (
                            f"Δσ={row.shear_links.reference_link_stress_range_mpa:.2f} MPa; "
                            f"util={links.utilization:.3f}"
                        ),
                        "PASS" if links.passes else "CHECK",
                    ),
                )
        if result.blockers:
            local_result_tree.insert(
                "",
                tk.END,
                values=(
                    "FLM3",
                    "Inputs required",
                    "; ".join(result.blockers),
                    "Fatigue traffic analysis is complete; resistance acceptance waits for these explicit detail inputs.",
                ),
            )
        status_var.set(
            "FLM3 fatigue complete."
            if not result.blockers
            else "FLM3 analysis complete; fatigue resistance inputs remain."
        )
        refresh_local_dashboard()
        refresh_dashboard()

    def run_fatigue_workflow() -> None:
        try:
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("FLM3 fatigue", str(exc))
            return
        if session.last_design_interpretation is None:
            messagebox.showinfo(
                "FLM3 fatigue",
                "Run the integrated Design & checks workflow first so the selected "
                "reinforcement cage is available.",
            )
            return
        run_fatigue_button.configure(state=tk.DISABLED)
        status_var.set("Running native FLM3 fatigue...")
        started_at = time.monotonic()

        def worker() -> None:
            try:
                result = session.run_fatigue()
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                message = str(exc)

                def failed() -> None:
                    run_fatigue_button.configure(state=tk.NORMAL)
                    status_var.set("FLM3 fatigue failed.")
                    messagebox.showerror("FLM3 fatigue", message)

                root.after(0, failed)
                return

            def complete() -> None:
                run_fatigue_button.configure(state=tk.NORMAL)
                show_fatigue_result(result)
                status_var.set(
                    f"FLM3 fatigue finished in {format_duration(time.monotonic() - started_at)}"
                )

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def run_full_workflow() -> None:
        try:
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Full analysis & design", str(exc))
            return

        if session.project.design_code is not DesignCode.EUROCODE:
            messagebox.showinfo(
                "Full analysis & design",
                (
                    "The one-click workflow currently targets the Eurocode bridge path "
                    "(EN 1991-2 traffic + EC2 design)."
                ),
            )
            return

        cancel_event.clear()
        started_at = time.monotonic()
        set_busy(True)
        status_var.set("Stage 1/5 — Preparing native LM1 analysis...")
        search_status_var.set("Full workflow started: native LM1 analysis.")

        def set_stage_progress(
            *,
            stage: str,
            base_percent: float,
            span_percent: float,
            completed: int,
            total: int,
        ) -> None:
            if total <= 0:
                return
            fraction = completed / total
            percent = base_percent + span_percent * fraction
            root.after(
                0,
                lambda: (
                    progress.configure(value=percent),
                    status_var.set(
                        f"{stage} — {completed:,}/{total:,} "
                        f"({100.0 * fraction:.1f}%)"
                    ),
                ),
            )

        def lm1_progress(completed: int, total: int) -> None:
            set_stage_progress(
                stage="Stage 1/5 — Native LM1",
                base_percent=0.0,
                span_percent=45.0,
                completed=completed,
                total=total,
            )

        def gr2_progress(completed: int, total: int) -> None:
            set_stage_progress(
                stage="Stage 2/5 — gr2 frequent LM1",
                base_percent=45.0,
                span_percent=15.0,
                completed=completed,
                total=total,
            )

        def lm2_progress(completed: int, total: int) -> None:
            set_stage_progress(
                stage="Stage 2/5 — LM2 / additional actions",
                base_percent=60.0,
                span_percent=15.0,
                completed=completed,
                total=total,
            )

        def worker() -> None:
            try:
                lm1 = session.run_native_lm1(
                    progress_callback=lm1_progress,
                    cancel_check=cancel_event.is_set,
                )
                root.after(
                    0,
                    lambda: status_var.set(
                        "Stage 2/5 — Additional actions + wind..."
                    ),
                )
                actions = session.run_extended_actions(
                    lm2_progress_callback=lm2_progress,
                    gr2_progress_callback=gr2_progress,
                )
                root.after(
                    0,
                    lambda: (
                        progress.configure(value=78.0),
                        status_var.set(
                            "Stage 3/5 — Local deck/slab analysis and design..."
                        ),
                    ),
                )
                local_deck = session.run_local_deck_design()
                root.after(
                    0,
                    lambda: (
                        progress.configure(value=84.0),
                        status_var.set(
                            "Stage 4/5 — Integrated girder design & checks..."
                        ),
                    ),
                )
                design = session.run_design_interpretation()
                root.after(
                    0,
                    lambda: (
                        progress.configure(value=90.0),
                        status_var.set("Stage 5/5 — Native FLM3 fatigue..."),
                    ),
                )
                fatigue = session.run_fatigue()
            except LM1SearchCancelled as exc:
                message = str(exc)

                def cancelled() -> None:
                    set_busy(False)
                    status_var.set("Full workflow cancelled during LM1 analysis.")
                    search_status_var.set(message)

                root.after(0, cancelled)
                return
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                message = str(exc)
                root.after(
                    0,
                    lambda: fail("Full analysis & design", message),
                )
                return

            def complete() -> None:
                set_busy(False)
                show_result(lm1)
                show_extended_action_result(actions)
                show_local_deck_result(local_deck)
                show_design_result(design)
                show_fatigue_result(fatigue, clear=False)
                progress["value"] = 100.0

                blockers = list(actions.unresolved_inputs)
                blockers.extend(design.coverage_blockers)
                blockers.extend(fatigue.blockers)
                unique_blockers = tuple(dict.fromkeys(blockers))
                elapsed = format_duration(time.monotonic() - started_at)
                if unique_blockers:
                    status_var.set(
                        "Full workflow complete in "
                        f"{elapsed}; inputs/checks still required: "
                        + "; ".join(unique_blockers)
                    )
                else:
                    status_var.set(
                        f"Full analysis & design complete in {elapsed}."
                    )
                notebook.select(design_tab)
                refresh_dashboard()

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def selected_design_girder_index() -> int | None:
        selected = design_tree.selection()
        if not selected:
            return None
        values = design_tree.item(selected[0], "values")
        if not values:
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError):
            return None

    def show_selected_design_result(_event=None) -> None:
        girder_index = selected_design_girder_index()
        result = session.last_design_interpretation
        if girder_index is None or result is None:
            return
        row = next(
            (item for item in result.girders if item.girder_index == girder_index),
            None,
        )
        if row is None:
            return

        flex = row.design.uls_design.flexure
        design_selected_var.set(
            f"Girder {girder_index}: "
            f"{row.selected_bars.bar_count}-Y{row.selected_bars.bar_diameter_mm:g} "
            f"longitudinal bars; {row.selected_links.leg_count}L-Y"
            f"{row.selected_links.link_diameter_mm:g}@{row.selected_links.spacing_mm:g} links. "
            f"MEd={row.design.uls_design.design_effects.moment_knm:.2f} kNm, "
            f"MRd={flex.resistance_knm:.2f} kNm, flexure util={flex.utilization:.3f}; "
            f"shear util={row.design.shear_utilization:.3f}; "
            f"crack util={row.design.crack.utilization:.3f}; "
            f"deflection util={row.design.deflection.utilization:.3f}. "
            f"Current status: {'PASS' if row.passes_current_checks else 'CHECK'}."
        )
        draw_reinforcement_section(
            design_section_canvas,
            bridge=bridge_preview_data(session.project),
            bar_count=row.selected_bars.bar_count,
            bar_label=(
                f"{row.selected_bars.bar_count}-Y"
                f"{row.selected_bars.bar_diameter_mm:g}"
            ),
            link_label=(
                f"{row.selected_links.leg_count}L-Y"
                f"{row.selected_links.link_diameter_mm:g}"
                f"@{row.selected_links.spacing_mm:g}"
            ),
        )

        for item in design_stage_tree.get_children():
            design_stage_tree.delete(item)
        for check in row.construction_stage_checks:
            design_stage_tree.insert(
                "",
                tk.END,
                values=(
                    check.stage.value,
                    f"{check.design_moment_knm:.2f}",
                    f"{check.design_shear_kn:.2f}",
                    f"{check.flexural_utilization:.3f}",
                    f"{check.shear_utilization:.3f}",
                    "PASS" if check.passes else "CHECK",
                ),
            )

    def open_selected_design_calculations() -> None:
        girder_index = selected_design_girder_index()
        if girder_index is None:
            messagebox.showinfo(
                "Worked calculations",
                "Select a girder result first.",
            )
            return
        notebook.select(calculations_tab)
        refresh_calculation_view()
        preferred_item: str | None = None
        block_item: str | None = None
        target_title = f"Girder {girder_index} - longitudinal RC design"
        for item_id, (block, step) in calculation_item_map.items():
            if getattr(block, "title", "") != target_title:
                continue
            if step is None:
                block_item = item_id
            elif getattr(step, "label", "") == "Required longitudinal reinforcement":
                preferred_item = item_id
                break
            elif preferred_item is None:
                preferred_item = item_id
        selected_item = preferred_item or block_item
        if selected_item is not None:
            calculation_tree.selection_set(selected_item)
            calculation_tree.focus(selected_item)
            calculation_tree.see(selected_item)
            show_calculation_detail()

    def show_design_result(result) -> None:
        for item in design_tree.get_children():
            design_tree.delete(item)
        inserted_design_items: list[str] = []
        for row in result.girders:
            flex = row.design.uls_design.flexure
            bars = row.selected_bars
            links = row.selected_links
            inserted_design_items.append(
                design_tree.insert(
                    "",
                    tk.END,
                    values=(
                    row.girder_index,
                    f"{row.effective_depth_m * 1000.0:.1f}",
                    f"{row.design.uls_design.design_effects.moment_knm:.2f}",
                    f"{flex.required_steel_area_mm2:.0f}",
                    (
                        f"{bars.bar_count}-Y{bars.bar_diameter_mm:g} "
                        f"({bars.layer_count} layer)"
                    ),
                    f"{flex.resistance_knm:.2f}",
                    f"{flex.utilization:.3f}",
                    f"{abs(row.design.uls_design.design_effects.shear_kn):.2f}",
                    (
                        f"{links.leg_count}L-Y{links.link_diameter_mm:g}"
                        f"@{links.spacing_mm:g}"
                    ),
                    f"{row.design.shear_utilization:.3f}",
                    f"{row.design.crack.crack_width_mm:.3f}",
                    f"{row.design.crack.utilization:.3f}",
                    f"{row.design.deflection.interpolated_deflection_mm:.3f}",
                    f"{row.design.deflection.utilization:.3f}",
                    row.governing_uls_moment_situation,
                    row.governing_uls_shear_situation,
                    (
                        "none"
                        if not row.construction_stage_checks
                        else max(
                            row.construction_stage_checks,
                            key=lambda item: max(
                                item.flexural_utilization,
                                item.shear_utilization,
                            ),
                        ).stage.value
                        + " "
                        + f"util={max(max(item.flexural_utilization, item.shear_utilization) for item in row.construction_stage_checks):.3f}"
                    ),
                    "PASS" if row.passes_current_checks else "CHECK",
                    ),
                )
            )
        refresh_design_dashboard()
        if inserted_design_items:
            design_tree.selection_set(inserted_design_items[0])
            design_tree.focus(inserted_design_items[0])
            design_tree.see(inserted_design_items[0])
            show_selected_design_result()
        summary = result.status
        if result.action_combinations is not None:
            bearing = result.action_combinations.bearing
            barrier = result.action_combinations.barrier
            extras: list[str] = []
            if bearing is not None:
                extras.append(
                    "Bearing ULS longitudinal="
                    f"{bearing.persistent_uls_total_longitudinal_kn:.1f} kN "
                    f"({bearing.persistent_uls_per_bearing_kn:.1f} kN/bearing); "
                    f"movement={bearing.required_movement_mm:.1f} mm; "
                    f"wind transverse={bearing.persistent_uls_total_transverse_kn:.1f} kN "
                    f"({bearing.persistent_uls_transverse_per_bearing_kn:.1f} kN/bearing)"
                )
            if barrier is not None:
                extras.append(
                    "Barrier accidental demand="
                    f"{barrier.transverse_accidental_demand_kn:.1f} kN, "
                    f"{barrier.base_moment_accidental_demand_knm:.1f} kNm"
                )
            local_deck = result.action_combinations.local_deck
            if local_deck is not None:
                extras.append(
                    "Local deck="
                    f"{local_deck.bottom_transverse.arrangement.label} bottom / "
                    f"{local_deck.top_transverse.arrangement.label} top; "
                    f"max util={max(local_deck.bottom_transverse.utilization, local_deck.top_transverse.utilization):.3f}"
                )
            if extras:
                summary += "\n" + " | ".join(extras)
        if result.coverage_blockers:
            summary += (
                "\nDESIGN BLOCKERS: "
                + "; ".join(result.coverage_blockers)
            )
            status_var.set("Design interpretation complete with unresolved blockers.")
        else:
            status_var.set("Integrated design interpretation complete.")
        design_status_var.set(summary)
        refresh_dashboard()

    def run_design_interpretation() -> None:
        try:
            project_before = session.project
            search_before = session.last_lm1_search
            commit_forms()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Design assumptions", str(exc))
            return
        if (
            project_before != session.project
            or search_before is not session.last_lm1_search
            or session.last_lm1_search is None
        ):
            messagebox.showinfo(
                "Design interpretation",
                "Project or analysis settings changed. Run native LM1 and then "
                "required additional actions + wind again before design.",
            )
            return

        def completed(result, elapsed: float) -> None:
            show_design_result(result)
            record = session.last_performance_record
            cache_text = " (cached)" if record is not None and record.cache_hit else ""
            status_var.set(
                f"Integrated design interpretation complete in "
                f"{format_duration(elapsed)}{cache_text}."
            )

        run_background_operation(
            title="Design interpretation",
            status="Running integrated girder design and serviceability checks...",
            operation=session.run_design_interpretation,
            on_success=completed,
        )

    def refresh_overview() -> None:
        snapshot = build_application_view_snapshot(session)
        project_header_var.set(
            f"{snapshot.project_name}  ·  {snapshot.project_subtitle}"
        )
        overview_project_var.set(
            f"{snapshot.project_name}\n{snapshot.project_subtitle}"
        )
        overview_progress_var.set(
            f"{snapshot.completed_stage_count} / {snapshot.total_stage_count}"
        )

        design_stage = next(
            stage for stage in snapshot.stages if stage.key == "design"
        )
        overview_design_var.set(
            {
                "complete": "READY",
                "review": "REVIEW",
                "pending": "PENDING",
                "ready": "READY",
            }[design_stage.state]
        )
        overview_verification_var.set(snapshot.verification_summary)
        overview_performance_var.set(snapshot.last_operation)
        overview_performance_detail_var.set(snapshot.last_operation_detail)

        for item in overview_stage_tree.get_children():
            overview_stage_tree.delete(item)
        overview_stage_tree.tag_configure("complete", foreground="#177245")
        overview_stage_tree.tag_configure("review", foreground="#A06000")
        overview_stage_tree.tag_configure("pending", foreground="#5F6F82")
        overview_stage_tree.tag_configure("ready", foreground="#2F6FB3")
        for stage in snapshot.stages:
            overview_stage_tree.insert(
                "",
                tk.END,
                values=(
                    stage.state.upper(),
                    f"{stage.title} — {stage.detail}",
                ),
                tags=(stage.state,),
            )

    def show_calculation_detail(_event=None) -> None:
        selected = calculation_tree.selection()
        if not selected:
            return
        item = calculation_item_map.get(selected[0])
        if item is None:
            return
        block, step = item
        if step is None:
            detail = (
                f"{block.title}\n\n"
                f"Scope\n{block.scope}\n\n"
                f"This block contains {len(block.steps)} calculation step(s). "
                "Select an individual step to review the equation, substitution, "
                "result and engineering reference."
            )
        else:
            lines = [
                step.label,
                "",
                "ENGINEERING REFERENCE",
                step.reference or "No additional reference text recorded.",
                "",
                "EQUATION / METHOD",
                step.expression,
                "",
                "NUMERICAL SUBSTITUTION",
                f"= {step.substitution}",
                "",
                "RESULT",
                step.result,
            ]
            if step.status:
                lines.extend(("", "CHECK STATUS", step.status))
            detail = "\n".join(lines)
        _set_text(calculation_detail, detail)

    def refresh_calculation_view() -> None:
        calculation_item_map.clear()
        for item in calculation_tree.get_children():
            calculation_tree.delete(item)
        if session.last_lm1_search is None:
            placeholder = calculation_tree.insert(
                "",
                tk.END,
                text="Run native LM1 or the full workflow first",
                values=("PENDING",),
            )
            calculation_tree.selection_set(placeholder)
            calculation_tree.focus(placeholder)
            calculation_item_map[placeholder] = (
                type(
                    "_Placeholder",
                    (),
                    {
                        "title": "Calculations are not available yet.",
                        "scope": (
                            "The calculation viewer is fed by the deterministic "
                            "CalculationTrace. Run analysis before reviewing equations."
                        ),
                        "steps": (),
                    },
                )(),
                None,
            )
            show_calculation_detail()
            return

        try:
            trace = session.calculation_trace()
        except (TypeError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Calculation review", str(exc))
            return

        first_step_id: str | None = None
        for block_index, block in enumerate(trace.blocks, start=1):
            block_id = calculation_tree.insert(
                "",
                tk.END,
                text=f"{block_index}. {block.title}",
                values=("",),
                open=block_index <= 2,
            )
            calculation_item_map[block_id] = (block, None)
            for step_index, step in enumerate(block.steps, start=1):
                step_id = calculation_tree.insert(
                    block_id,
                    tk.END,
                    text=f"{block_index}.{step_index}  {step.label}",
                    values=(step.status,),
                )
                calculation_item_map[step_id] = (block, step)
                if first_step_id is None:
                    first_step_id = step_id
        if first_step_id is not None:
            calculation_tree.selection_set(first_step_id)
            calculation_tree.focus(first_step_id)
            calculation_tree.see(first_step_id)
            show_calculation_detail()
        status_var.set(
            f"Calculation trace loaded: {trace.step_count} worked step(s) "
            f"across {len(trace.blocks)} block(s)."
        )

    def open_calculation_workspace() -> None:
        notebook.select(calculations_tab)
        refresh_calculation_view()

    def refresh_dashboard() -> None:
        refresh_overview()
        refresh_project_preview()
        refresh_verification_dashboard()
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
                "Independent structural acceptance boundary\n\n"
                "The application can generate the exact MIDAS Civil .mct and STAAD.Pro "
                ".std models used by the native analysis. Those files must be run in the "
                "installed external programs and their genuine returned results checked "
                "for geometry, stiffness, loading, result axes, signs and justified "
                "tolerances before production certification.\n\n"
                + case_text
                + (
                    "\n\nLatest external import: "
                    + (
                        "none."
                        if session.last_verification_import is None
                        else (
                            f"{session.last_verification_import.source_name}; "
                            f"{'PASS' if session.last_verification_import.passes else 'REVIEW / FAIL'}; "
                            f"{len(session.last_verification_import.result_sets)}/"
                            f"{len(session.last_verification_import.requested_result_ids)} "
                            "Stage-5 result sets imported."
                        )
                    )
                )
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
                "After genuine external acceptance, the applicable verification manifest "
                "can be closed. The research phase then defines justified random-variable "
                "distributions/bounds/correlations before generating verified datasets, "
                "training/validating the ANN and running reliability analysis/RBDO."
            ),
        )

    def set_busy(busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in analysis_buttons:
            button.configure(state=state)
        cancel_button.configure(state=tk.NORMAL if busy else tk.DISABLED)
        if busy:
            progress["value"] = 0.0

    def format_duration(seconds: float) -> str:
        seconds = max(round(seconds), 0)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def update_analysis_progress(
        completed: int,
        total: int,
        started_at: float,
    ) -> None:
        if total <= 0:
            return
        percent = 100.0 * completed / total
        progress["value"] = percent
        elapsed = time.monotonic() - started_at
        eta_text = "calculating"
        if completed > 0:
            eta = elapsed * (total - completed) / completed
            eta_text = format_duration(eta)
        message = (
            f"LM1 case {completed:,} / {total:,} — {percent:5.1f}% — "
            f"elapsed {format_duration(elapsed)} — ETA {eta_text}"
        )
        status_var.set(message)
        search_status_var.set(message)

    def cancel_analysis() -> None:
        cancel_event.set()
        cancel_button.configure(state=tk.DISABLED)
        status_var.set("Cancelling native LM1 analysis after the current case...")

    def fail(title: str, message: str) -> None:
        set_busy(False)
        status_var.set("Operation failed")
        messagebox.showerror(title, message)

    def run_background_operation(
        *,
        title: str,
        status: str,
        operation,
        on_success,
    ) -> None:
        """Run a potentially expensive application operation without blocking Tk."""
        started_at = time.monotonic()
        set_busy(True)
        status_var.set(status)

        def worker() -> None:
            try:
                value = operation()
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                message = str(exc)
                root.after(0, lambda: fail(title, message))
                return

            def complete() -> None:
                set_busy(False)
                on_success(value, time.monotonic() - started_at)

            root.after(0, complete)

        threading.Thread(target=worker, daemon=True).start()

    def commit_forms() -> None:
        nonlocal displayed_unit
        project = load_case_fields_from_form().apply(project_from_form())
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
        populate_load_cases(session.project)
        if project_changed or settings_changed:
            clear_results()
        refresh_load_case_views()
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
        populate_load_cases(session.project)
        refresh_load_case_views()
        refresh_dashboard()
        status_var.set("Project definition applied.")

    def apply_load_cases() -> None:
        try:
            project = project_from_form()
            updated = load_case_fields_from_form().apply(project)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Load cases", str(exc))
            return
        if updated != session.project:
            session.replace_project(updated)
            clear_results()
        populate_project(session.project)
        populate_load_cases(session.project)
        refresh_load_case_views()
        refresh_dashboard()
        status_var.set("Permanent load cases applied.")

    def apply_basis() -> None:
        nonlocal displayed_unit
        try:
            project = load_case_fields_from_form().apply(project_from_form())
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
        populate_load_cases(session.project)
        refresh_load_case_views()
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

        cancel_event.clear()
        started_at = time.monotonic()
        last_ui_update = [0.0]
        set_busy(True)
        status_var.set("Preparing native full-width LM1 analysis...")

        def progress_callback(completed: int, total: int) -> None:
            now = time.monotonic()
            if (
                completed not in {0, total}
                and now - last_ui_update[0] < 0.20
            ):
                return
            last_ui_update[0] = now
            root.after(
                0,
                lambda current=completed, count=total: update_analysis_progress(
                    current,
                    count,
                    started_at,
                ),
            )

        def worker() -> None:
            try:
                result = session.run_native_lm1(
                    progress_callback=progress_callback,
                    cancel_check=cancel_event.is_set,
                )
            except LM1SearchCancelled as exc:
                message = str(exc)

                def cancelled() -> None:
                    set_busy(False)
                    status_var.set("Native LM1 analysis cancelled.")
                    search_status_var.set(message)

                root.after(0, cancelled)
                return
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
        session.replace_project(application_default_project())
        session.project_path = None
        session.set_preferences(ApplicationPreferences())
        displayed_unit = session.preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        populate_load_cases(session.project)
        clear_results()
        refresh_load_case_views()
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
        session.replace_project(opened.project)
        session.project_path = opened.project_path
        session.set_preferences(opened.preferences)
        displayed_unit = session.preferences.units
        populate_project(session.project)
        populate_preferences(session.preferences)
        populate_load_cases(session.project)
        clear_results()
        refresh_load_case_views()
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

        run_background_operation(
            title="Calculation report",
            status="Generating step-by-step HTML calculation report...",
            operation=lambda: session.write_last_lm1_report(path),
            on_success=lambda report, elapsed: status_var.set(
                f"HTML report saved: {report.name} "
                f"({format_duration(elapsed)})."
            ),
        )

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

        run_background_operation(
            title="PDF calculation report",
            status="Generating step-by-step PDF calculation report...",
            operation=lambda: session.write_last_lm1_pdf_report(path),
            on_success=lambda report, elapsed: status_var.set(
                f"PDF report saved: {report.name} "
                f"({format_duration(elapsed)})."
            ),
        )

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

        def completed(written, elapsed: float) -> None:
            status_var.set(
                "Exported full independent-verification campaign with "
                f"{written.model_count} structural model package(s) across "
                f"{len(written.families)} action families in "
                f"{format_duration(elapsed)}; campaign manifest: "
                f"{written.manifest_json.name}."
            )

        run_background_operation(
            title="Verification export",
            status="Building MIDAS/STAAD verification campaign...",
            operation=lambda: session.export_verification_campaign(
                directory,
                base_name="application_verification",
            ),
            on_success=completed,
        )


    def show_verification_import(report) -> None:
        for item in verification_result_tree.get_children():
            verification_result_tree.delete(item)
        by_id = {item.result_id: item for item in report.result_sets}
        for result_id in report.requested_result_ids:
            item = by_id.get(result_id)
            if item is None:
                verification_result_tree.insert(
                    "",
                    tk.END,
                    values=(
                        f"{result_id} - missing from external output",
                        "",
                        "MISSING",
                        "",
                        report.source_name,
                    ),
                )
                continue
            max_error = item.maximum_relative_error
            verification_result_tree.insert(
                "",
                tk.END,
                values=(
                    f"{item.result_id} - {item.result_name}",
                    item.result_kind.replace("_", " "),
                    "PASS" if item.passes else "FAIL",
                    "" if max_error is None else f"{100.0 * max_error:.3f}%",
                    item.source_name,
                ),
            )
        refresh_verification_dashboard()
        status = "PASS" if report.passes else "REVIEW / FAIL"
        status_var.set(
            f"{report.source_name} Stage-5 import: {status}; "
            f"{len(report.result_sets)}/{len(report.requested_result_ids)} result "
            f"sets imported; {len(report.failed_result_ids)} failed and "
            f"{len(report.missing_result_ids)} missing."
        )
        refresh_dashboard()

    def import_staad_verification_results() -> None:
        path = filedialog.askopenfilename(
            title="Import STAAD.Pro analysis output",
            filetypes=(
                ("STAAD analysis output", "*.anl"),
                ("Text output", "*.txt"),
                ("All files", "*.*"),
            ),
        )
        if not path:
            return
        run_background_operation(
            title="STAAD verification import",
            status="Importing and comparing STAAD Stage-5 results...",
            operation=lambda: session.import_stage5_staad_anl(path),
            on_success=lambda report, elapsed: show_verification_import(report),
        )

    def import_midas_verification_results() -> None:
        common_types = (
            ("CSV / text table", "*.csv *.txt *.tsv"),
            ("All files", "*.*"),
        )
        reaction_path = filedialog.askopenfilename(
            title="MIDAS reaction result table",
            filetypes=common_types,
        )
        if not reaction_path:
            return
        displacement_path = filedialog.askopenfilename(
            title="MIDAS displacement result table",
            filetypes=common_types,
        )
        if not displacement_path:
            return
        member_force_path = filedialog.askopenfilename(
            title="MIDAS beam-force result table",
            filetypes=common_types,
        )
        if not member_force_path:
            return
        delimiter = "\t" if Path(reaction_path).suffix.lower() == ".tsv" else ","
        run_background_operation(
            title="MIDAS verification import",
            status="Importing and comparing MIDAS Stage-5 result tables...",
            operation=lambda: session.import_stage5_midas_tables(
                reaction_path=reaction_path,
                displacement_path=displacement_path,
                member_force_path=member_force_path,
                delimiter=delimiter,
            ),
            on_success=lambda report, elapsed: show_verification_import(report),
        )

    def save_verification_evidence() -> None:
        if session.last_verification_import is None:
            messagebox.showinfo(
                "Verification evidence",
                "Import STAAD or MIDAS Stage-5 results first.",
            )
            return
        directory = filedialog.askdirectory(
            title="Choose folder for verification comparison evidence"
        )
        if not directory:
            return
        run_background_operation(
            title="Verification evidence",
            status="Writing verification comparison evidence...",
            operation=lambda: session.write_last_verification_evidence(directory),
            on_success=lambda written, elapsed: status_var.set(
                "Saved verification evidence: "
                f"{written.summary_json.name} and {written.comparisons_csv.name} "
                f"({format_duration(elapsed)})."
            ),
        )

    project_preview_canvas.bind("<Configure>", refresh_project_preview)
    permanent_load_canvas.bind("<Configure>", refresh_permanent_load_chart)
    analysis_chart_metric.bind("<<ComboboxSelected>>", refresh_analysis_chart)
    analysis_chart_girder.bind("<<ComboboxSelected>>", refresh_analysis_chart)
    analysis_chart_canvas.bind("<Configure>", refresh_analysis_chart)
    design_chart_canvas.bind("<Configure>", refresh_design_dashboard)
    design_tree.bind("<<TreeviewSelect>>", show_selected_design_result)
    design_section_canvas.bind("<Configure>", show_selected_design_result)
    design_show_calculation_button.configure(
        command=open_selected_design_calculations
    )
    local_chart_canvas.bind("<Configure>", refresh_local_dashboard)
    verification_error_canvas.bind("<Configure>", refresh_verification_dashboard)

    def refresh_active_workspace_visuals(_event=None) -> None:
        active_key = page_keys.get(notebook.select())
        if active_key == "project":
            refresh_project_preview()
        elif active_key == "loads":
            refresh_permanent_load_chart()
        elif active_key == "analysis":
            refresh_analysis_chart()
        elif active_key == "design":
            refresh_design_dashboard()
            show_selected_design_result()
        elif active_key == "deck":
            refresh_local_dashboard()
        elif active_key == "calculations":
            refresh_calculation_view()
        elif active_key == "verification":
            refresh_verification_dashboard()

    notebook.bind(
        "<<NotebookTabChanged>>",
        refresh_active_workspace_visuals,
        add="+",
    )

    calculation_tree.bind("<<TreeviewSelect>>", show_calculation_detail)
    calculation_refresh_button.configure(command=refresh_calculation_view)
    header_open_button.configure(command=open_project)
    header_save_button.configure(command=save_current)
    header_run_button.configure(command=run_full_workflow)
    overview_run_button.configure(command=run_full_workflow)
    overview_calculations_button.configure(command=open_calculation_workspace)
    overview_verification_button.configure(
        command=lambda: notebook.select(verification_tab)
    )

    apply_project_button.configure(command=apply_project)
    apply_load_cases_button.configure(command=apply_load_cases)
    revert_load_cases_button.configure(
        command=lambda: (
            populate_load_cases(session.project),
            refresh_load_case_views(),
        )
    )
    revert_project_button.configure(
        command=lambda: populate_project(session.project)
    )
    apply_basis_button.configure(command=apply_basis)
    revert_basis_button.configure(
        command=lambda: populate_preferences(session.preferences)
    )
    run_button.configure(command=run_analysis)
    full_run_button.configure(command=run_full_workflow)
    run_actions_button.configure(command=run_extended_action_suite)
    run_design_button.configure(command=run_design_interpretation)
    run_local_deck_button.configure(command=run_local_deck_workflow)
    run_fatigue_button.configure(command=run_fatigue_workflow)
    cancel_button.configure(command=cancel_analysis)
    refresh_dashboard_button.configure(command=refresh_dashboard)
    html_button.configure(command=save_html_report)
    pdf_button.configure(command=save_pdf_report)
    print_button.configure(command=print_preview)
    export_button.configure(command=export_verification)
    import_staad_button.configure(command=import_staad_verification_results)
    import_midas_button.configure(command=import_midas_verification_results)
    save_verification_evidence_button.configure(command=save_verification_evidence)

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
    analysis_menu.add_command(
        label="Run Full Analysis & Design",
        command=run_full_workflow,
    )
    analysis_menu.add_separator()
    analysis_menu.add_command(label="Run native LM1", command=run_analysis)
    menu.add_cascade(label="Analysis", menu=analysis_menu)

    design_menu = tk.Menu(menu, tearoff=False)
    design_menu.add_command(
        label="Run design interpretation",
        command=run_design_interpretation,
    )
    design_menu.add_command(
        label="Run local deck design",
        command=run_local_deck_workflow,
    )
    design_menu.add_command(
        label="Run FLM3 fatigue",
        command=run_fatigue_workflow,
    )
    menu.add_cascade(label="Design", menu=design_menu)

    report_menu = tk.Menu(menu, tearoff=False)
    report_menu.add_command(label="Save HTML...", command=save_html_report)
    report_menu.add_command(label="Save PDF...", command=save_pdf_report)
    report_menu.add_command(label="Print / preview", command=print_preview)
    menu.add_cascade(label="Reports", menu=report_menu)

    verification_menu = tk.Menu(menu, tearoff=False)
    verification_menu.add_command(
        label="Export full MIDAS / STAAD campaign...",
        command=export_verification,
    )
    verification_menu.add_separator()
    verification_menu.add_command(
        label="Import STAAD .ANL results...",
        command=import_staad_verification_results,
    )
    verification_menu.add_command(
        label="Import MIDAS result tables...",
        command=import_midas_verification_results,
    )
    verification_menu.add_command(
        label="Save comparison evidence...",
        command=save_verification_evidence,
    )
    menu.add_cascade(label="Verification", menu=verification_menu)
    root.configure(menu=menu)

    populate_project(session.project)
    populate_preferences(session.preferences)
    populate_load_cases(session.project)
    clear_results()
    refresh_load_case_views()
    refresh_dashboard()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
