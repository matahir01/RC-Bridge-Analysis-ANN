from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesktopPalette:
    canvas: str = "#F4F7FB"
    surface: str = "#FFFFFF"
    surface_muted: str = "#EEF3F8"
    border: str = "#D6E0EA"
    ink: str = "#172033"
    ink_muted: str = "#5F6F82"
    primary: str = "#163B65"
    primary_hover: str = "#1F4F84"
    accent: str = "#2F6FB3"
    success: str = "#177245"
    warning: str = "#A06000"
    danger: str = "#A73434"
    sidebar: str = "#102A43"
    sidebar_hover: str = "#173E63"
    sidebar_active: str = "#1E527F"
    sidebar_text: str = "#EAF2F8"


PALETTE = DesktopPalette()


def configure_desktop_theme(root, ttk) -> DesktopPalette:
    """Apply the dependency-free professional desktop theme used by the Tk shell."""

    palette = PALETTE
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=palette.canvas)

    style.configure(
        ".",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI", 10),
    )
    style.configure("TFrame", background=palette.surface)
    style.configure("Surface.TFrame", background=palette.surface)
    style.configure("Sidebar.TFrame", background=palette.sidebar)
    style.configure("Header.TFrame", background=palette.surface)
    style.configure("Status.TFrame", background=palette.surface)

    style.configure(
        "TLabel",
        background=palette.canvas,
        foreground=palette.ink,
        font=("Segoe UI", 10),
    )
    style.configure(
        "HeaderTitle.TLabel",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI Semibold", 17),
    )
    style.configure(
        "PageTitle.TLabel",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI Semibold", 17),
    )
    style.configure(
        "HeaderSubtitle.TLabel",
        background=palette.surface,
        foreground=palette.ink_muted,
        font=("Segoe UI", 9),
    )
    style.configure(
        "SidebarBrand.TLabel",
        background=palette.sidebar,
        foreground="#FFFFFF",
        font=("Segoe UI Semibold", 15),
    )
    style.configure(
        "SidebarCaption.TLabel",
        background=palette.sidebar,
        foreground="#B9CCDD",
        font=("Segoe UI", 8),
    )
    style.configure(
        "SidebarSection.TLabel",
        background=palette.sidebar,
        foreground="#8FB1CC",
        font=("Segoe UI Semibold", 8),
    )
    style.configure(
        "CardTitle.TLabel",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI Semibold", 11),
    )
    style.configure(
        "Muted.TLabel",
        background=palette.surface,
        foreground=palette.ink_muted,
        font=("Segoe UI", 9),
    )
    style.configure(
        "SurfaceMuted.TLabel",
        background=palette.surface,
        foreground=palette.ink_muted,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Metric.TLabel",
        background=palette.surface,
        foreground=palette.primary,
        font=("Segoe UI Semibold", 18),
    )

    style.configure(
        "TButton",
        padding=(12, 7),
        font=("Segoe UI Semibold", 9),
    )
    style.configure(
        "Primary.TButton",
        background=palette.primary,
        foreground="#FFFFFF",
        bordercolor=palette.primary,
        lightcolor=palette.primary,
        darkcolor=palette.primary,
        padding=(14, 8),
    )
    style.map(
        "Primary.TButton",
        background=[("active", palette.primary_hover), ("disabled", "#AAB8C5")],
        foreground=[("disabled", "#F4F7FB")],
    )
    style.configure(
        "Ribbon.TButton",
        background=palette.surface,
        foreground=palette.ink,
        bordercolor=palette.border,
        padding=(12, 10),
        anchor="center",
        font=("Segoe UI Semibold", 9),
    )
    style.map(
        "Ribbon.TButton",
        background=[("active", palette.surface_muted)],
        foreground=[("active", palette.primary)],
    )
    style.configure(
        "RibbonGroup.TLabelframe",
        background=palette.surface,
        bordercolor=palette.border,
        relief="solid",
        borderwidth=1,
        padding=(5, 3),
    )
    style.configure(
        "RibbonGroup.TLabelframe.Label",
        background=palette.surface,
        foreground=palette.ink_muted,
        font=("Segoe UI", 8),
    )

    style.configure(
        "Secondary.TButton",
        background=palette.surface,
        foreground=palette.primary,
        bordercolor=palette.border,
        padding=(12, 7),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", palette.surface_muted)],
    )
    style.configure(
        "Nav.TButton",
        background=palette.sidebar,
        foreground=palette.sidebar_text,
        borderwidth=0,
        relief="flat",
        anchor="w",
        padding=(16, 9),
        font=("Segoe UI", 9),
    )
    style.map(
        "Nav.TButton",
        background=[("active", palette.sidebar_hover)],
        foreground=[("active", "#FFFFFF")],
    )
    style.configure(
        "NavActive.TButton",
        background=palette.sidebar_active,
        foreground="#FFFFFF",
        borderwidth=0,
        relief="flat",
        anchor="w",
        padding=(16, 9),
        font=("Segoe UI Semibold", 9),
    )
    style.map(
        "NavActive.TButton",
        background=[("active", palette.sidebar_active)],
        foreground=[("active", "#FFFFFF")],
    )

    style.configure(
        "TLabelframe",
        background=palette.surface,
        bordercolor=palette.border,
        relief="solid",
        borderwidth=1,
        padding=10,
    )
    style.configure(
        "TLabelframe.Label",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI Semibold", 10),
    )
    style.configure(
        "Card.TLabelframe",
        background=palette.surface,
        bordercolor=palette.border,
        relief="solid",
        borderwidth=1,
        padding=12,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=palette.surface,
        foreground=palette.ink,
        font=("Segoe UI Semibold", 10),
    )

    style.configure(
        "Treeview",
        background=palette.surface,
        fieldbackground=palette.surface,
        foreground=palette.ink,
        bordercolor=palette.border,
        rowheight=27,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Treeview.Heading",
        background=palette.surface_muted,
        foreground=palette.ink,
        bordercolor=palette.border,
        relief="flat",
        font=("Segoe UI Semibold", 9),
        padding=(7, 6),
    )
    style.map(
        "Treeview",
        background=[("selected", "#D9EAF8")],
        foreground=[("selected", palette.ink)],
    )

    style.configure(
        "TNotebook",
        background=palette.surface,
        borderwidth=0,
        tabmargins=0,
    )
    # The professional shell uses its own left navigation. Keep Notebook as the
    # stable page container while hiding the legacy tab strip.
    style.layout("Workspace.TNotebook.Tab", [])
    style.configure("Workspace.TNotebook", background=palette.surface, borderwidth=0)

    style.configure(
        "Horizontal.TProgressbar",
        background=palette.accent,
        troughcolor=palette.surface_muted,
        bordercolor=palette.surface_muted,
        lightcolor=palette.accent,
        darkcolor=palette.accent,
    )
    return palette
