from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import (
    EurocodeFactors,
    ServiceabilityPsiFactors,
    characteristic_sls,
    frequent_sls,
    persistent_uls,
    quasi_permanent_sls,
)
from rc_bridge.core.models import (
    PermanentActionModel,
    PermanentActionStage,
    PermanentLineAction,
    PermanentLineActionCategory,
    ProjectInput,
    SupportSystem,
    SurfacingLayer,
)
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
)
from rc_bridge.workflow.project_bridge import (
    girder_characteristic_permanent_effects,
    girder_permanent_load_segments,
)

_MANAGED_PREFIX = "APP:"


class SurfacingExtent(str, Enum):
    CARRIAGEWAY = "carriageway"
    FULL_DECK = "full_deck"


@dataclass(frozen=True)
class ApplicationLoadCaseFields:
    """Common permanent actions editable from the desktop workbench.

    The fields deliberately cover only physical actions the deterministic engine
    already understands. Unsupported variable actions are exposed separately in
    the UI rather than being approximated here.
    """

    surfacing_thickness_m: float = 0.0
    surfacing_density_kn_m3: float = 22.0
    surfacing_extent: SurfacingExtent = SurfacingExtent.CARRIAGEWAY
    left_barrier_kn_m: float = 0.0
    right_barrier_kn_m: float = 0.0
    left_services_kn_m: float = 0.0
    right_services_kn_m: float = 0.0
    left_services_y_m: float | None = None
    right_services_y_m: float | None = None

    def __post_init__(self) -> None:
        nonnegative = (
            self.surfacing_thickness_m,
            self.surfacing_density_kn_m3,
            self.left_barrier_kn_m,
            self.right_barrier_kn_m,
            self.left_services_kn_m,
            self.right_services_kn_m,
        )
        if any(value < 0.0 for value in nonnegative):
            raise ValueError("Application load-case magnitudes cannot be negative.")
        if self.surfacing_thickness_m > 0.0 and self.surfacing_density_kn_m3 <= 0.0:
            raise ValueError("Surfacing density must be positive when surfacing is present.")

    @classmethod
    def from_project(cls, project: ProjectInput) -> ApplicationLoadCaseFields:
        geometry = project.geometry
        half_deck = float(geometry.deck_width_m) / 2.0
        surfacing_thickness = 0.0
        surfacing_density = 22.0
        surfacing_extent = SurfacingExtent.CARRIAGEWAY
        left_barrier = 0.0
        right_barrier = 0.0
        left_services = 0.0
        right_services = 0.0
        left_services_y: float | None = None
        right_services_y: float | None = None

        for layer in project.permanent_actions.surfacing_layers:
            if layer.name != f"{_MANAGED_PREFIX}surfacing":
                continue
            surfacing_thickness = float(layer.thickness_m)
            surfacing_density = float(layer.density_kn_m3)
            full_deck = (
                abs(float(layer.y_start_m) + half_deck) <= 1.0e-9
                and abs(float(layer.y_end_m) - half_deck) <= 1.0e-9
            )
            surfacing_extent = (
                SurfacingExtent.FULL_DECK
                if full_deck
                else SurfacingExtent.CARRIAGEWAY
            )

        for action in project.permanent_actions.line_actions:
            if not action.name.startswith(_MANAGED_PREFIX):
                continue
            if action.name == f"{_MANAGED_PREFIX}left barrier":
                left_barrier = float(action.magnitude_kn_m)
            elif action.name == f"{_MANAGED_PREFIX}right barrier":
                right_barrier = float(action.magnitude_kn_m)
            elif action.name == f"{_MANAGED_PREFIX}left services":
                left_services = float(action.magnitude_kn_m)
                left_services_y = float(action.y_m)
            elif action.name == f"{_MANAGED_PREFIX}right services":
                right_services = float(action.magnitude_kn_m)
                right_services_y = float(action.y_m)

        return cls(
            surfacing_thickness_m=surfacing_thickness,
            surfacing_density_kn_m3=surfacing_density,
            surfacing_extent=surfacing_extent,
            left_barrier_kn_m=left_barrier,
            right_barrier_kn_m=right_barrier,
            left_services_kn_m=left_services,
            right_services_kn_m=right_services,
            left_services_y_m=left_services_y,
            right_services_y_m=right_services_y,
        )

    def apply(self, project: ProjectInput) -> ProjectInput:
        geometry = project.geometry
        half_deck = float(geometry.deck_width_m) / 2.0
        total_length = sum(float(value) for value in geometry.span_lengths_m)

        preserved_layers = [
            layer
            for layer in project.permanent_actions.surfacing_layers
            if not layer.name.startswith(_MANAGED_PREFIX)
        ]
        preserved_lines = [
            action
            for action in project.permanent_actions.line_actions
            if not action.name.startswith(_MANAGED_PREFIX)
        ]

        managed_layers: list[SurfacingLayer] = []
        if self.surfacing_thickness_m > 0.0:
            if self.surfacing_extent is SurfacingExtent.FULL_DECK:
                y_start, y_end = -half_deck, half_deck
            else:
                y_start = float(geometry.carriageway_left_edge_m)
                y_end = float(geometry.carriageway_right_edge_m)
            managed_layers.append(
                SurfacingLayer(
                    name=f"{_MANAGED_PREFIX}surfacing",
                    thickness_m=self.surfacing_thickness_m,
                    density_kn_m3=self.surfacing_density_kn_m3,
                    y_start_m=y_start,
                    y_end_m=y_end,
                    x_start_m=0.0,
                    x_end_m=total_length,
                    stage=PermanentActionStage.SUPERIMPOSED,
                )
            )

        managed_lines: list[PermanentLineAction] = []

        def add_line(
            *,
            name: str,
            magnitude_kn_m: float,
            y_m: float,
            category: PermanentLineActionCategory,
        ) -> None:
            if magnitude_kn_m <= 0.0:
                return
            if y_m < -half_deck - 1.0e-9 or y_m > half_deck + 1.0e-9:
                raise ValueError(f"{name} transverse position lies outside the deck.")
            managed_lines.append(
                PermanentLineAction(
                    name=f"{_MANAGED_PREFIX}{name}",
                    magnitude_kn_m=magnitude_kn_m,
                    y_m=y_m,
                    category=category,
                    x_start_m=0.0,
                    x_end_m=total_length,
                    stage=PermanentActionStage.SUPERIMPOSED,
                )
            )

        add_line(
            name="left barrier",
            magnitude_kn_m=self.left_barrier_kn_m,
            y_m=-half_deck,
            category=PermanentLineActionCategory.BARRIER,
        )
        add_line(
            name="right barrier",
            magnitude_kn_m=self.right_barrier_kn_m,
            y_m=half_deck,
            category=PermanentLineActionCategory.BARRIER,
        )
        add_line(
            name="left services",
            magnitude_kn_m=self.left_services_kn_m,
            y_m=(
                -half_deck
                if self.left_services_y_m is None
                else self.left_services_y_m
            ),
            category=PermanentLineActionCategory.SERVICES,
        )
        add_line(
            name="right services",
            magnitude_kn_m=self.right_services_kn_m,
            y_m=(
                half_deck
                if self.right_services_y_m is None
                else self.right_services_y_m
            ),
            category=PermanentLineActionCategory.SERVICES,
        )

        data = project.model_dump(mode="python")
        data["permanent_actions"] = PermanentActionModel(
            surfacing_layers=[*preserved_layers, *managed_layers],
            line_actions=[*preserved_lines, *managed_lines],
        ).model_dump(mode="python")
        return ProjectInput.model_validate(data)


@dataclass(frozen=True)
class PermanentGirderLoadAudit:
    girder_index: int
    girder_self_weight_kn_m: float
    false_slab_kn_m: float
    in_situ_slab_kn_m: float
    surfacing_kn_m: float
    barriers_kn_m: float
    services_kn_m: float
    other_kn_m: float
    total_equivalent_kn_m: float


def permanent_load_audit(project: ProjectInput) -> tuple[PermanentGirderLoadAudit, ...]:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    rows: list[PermanentGirderLoadAudit] = []
    for girder_index in range(1, int(project.geometry.girder_count) + 1):
        buckets = {
            "girder_self_weight": 0.0,
            "false_slab": 0.0,
            "in_situ_slab": 0.0,
            "surfacing": 0.0,
            "barriers": 0.0,
            "services": 0.0,
            "other": 0.0,
        }
        for segment in girder_permanent_load_segments(
            project,
            girder_index=girder_index,
        ):
            equivalent = segment.total_load_kn / total_length
            if segment.category == "girder_self_weight":
                buckets["girder_self_weight"] += equivalent
            elif segment.source == "physical precast false slab self-weight":
                buckets["false_slab"] += equivalent
            elif segment.source == "physical wet in-situ deck self-weight":
                buckets["in_situ_slab"] += equivalent
            elif segment.category == "surfacing":
                buckets["surfacing"] += equivalent
            elif segment.category in {
                PermanentLineActionCategory.BARRIER.value,
                "barriers_and_services",
            }:
                buckets["barriers"] += equivalent
            elif segment.category == PermanentLineActionCategory.SERVICES.value:
                buckets["services"] += equivalent
            else:
                buckets["other"] += equivalent
        total = sum(buckets.values())
        rows.append(
            PermanentGirderLoadAudit(
                girder_index=girder_index,
                girder_self_weight_kn_m=buckets["girder_self_weight"],
                false_slab_kn_m=buckets["false_slab"],
                in_situ_slab_kn_m=buckets["in_situ_slab"],
                surfacing_kn_m=buckets["surfacing"],
                barriers_kn_m=buckets["barriers"],
                services_kn_m=buckets["services"],
                other_kn_m=buckets["other"],
                total_equivalent_kn_m=total,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class ApplicationGirderCombinationSummary:
    girder_index: int
    permanent_characteristic: LoadEffects
    traffic_characteristic: LoadEffects
    uls: LoadEffects
    sls_characteristic: LoadEffects
    sls_frequent: LoadEffects
    sls_quasi_permanent: LoadEffects


def application_combination_summary(
    project: ProjectInput,
    search: ProjectNativeLM1GrillageSearchResult,
    *,
    uls_factors: EurocodeFactors,
    sls_factors: ServiceabilityPsiFactors,
) -> tuple[ApplicationGirderCombinationSummary, ...]:
    """Combine Gk with native LM1 envelope magnitudes for application interpretation.

    This is intentionally limited to one simply-supported span, where the native
    LM1 result is an absolute per-girder M/V/T envelope. Continuous design needs
    the signed station-side workflow and is not approximated by this summary.
    """

    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Application combination summary for continuous spans requires the "
            "signed station-side continuous workflow."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError(
            "Application combination summary currently requires one simple span."
        )

    rows: list[ApplicationGirderCombinationSummary] = []
    for traffic_row in search.girders:
        permanent = girder_characteristic_permanent_effects(
            project,
            girder_index=traffic_row.girder_index,
        )
        traffic = LoadEffects(
            moment_knm=traffic_row.moment_knm.value,
            shear_kn=traffic_row.shear_kn.value,
            torsion_knm=traffic_row.torsion_knm.value,
        )
        uls = persistent_uls(permanent, traffic, uls_factors).effects
        characteristic = characteristic_sls(permanent, traffic).effects
        frequent = frequent_sls(permanent, traffic, sls_factors).effects
        quasi = quasi_permanent_sls(permanent, traffic, sls_factors).effects
        rows.append(
            ApplicationGirderCombinationSummary(
                girder_index=traffic_row.girder_index,
                permanent_characteristic=permanent,
                traffic_characteristic=traffic,
                uls=uls,
                sls_characteristic=characteristic,
                sls_frequent=frequent,
                sls_quasi_permanent=quasi,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class VariableActionScope:
    name: str
    status: str
    detail: str


def eurocode_variable_action_scope() -> tuple[VariableActionScope, ...]:
    """Expose implemented and missing bridge variable-action families."""

    return (
        VariableActionScope(
            "LM1 vertical road traffic",
            "implemented",
            "Native full-width moving tandem + UDL search.",
        ),
        VariableActionScope(
            "FLM3 fatigue traffic",
            "engine implemented",
            "Dedicated fatigue engine exists; not yet a one-click desktop run.",
        ),
        VariableActionScope(
            "LM2 local axle",
            "implemented / verification-gated",
            (
                "The Additional actions workspace scans the 400 kN isolated axle "
                "across the carriageway on the native vertical grillage and retains "
                "the 0.35 m x 0.60 m wheel contact patch for local slab checks."
            ),
        ),
        VariableActionScope(
            "LM3 special vehicles",
            "not wired",
            "Project-specific abnormal/special vehicle loading is not yet connected.",
        ),
        VariableActionScope(
            "LM4 crowd loading",
            "not wired",
            "Crowd loading is not yet connected to the global bridge analysis.",
        ),
        VariableActionScope(
            "Braking / acceleration",
            "action implemented / horizontal solver pending",
            (
                "EN 1991-2 characteristic Qlk is calculated with explicit adjustment "
                "factors and loaded length. Longitudinal deck/bearing/substructure "
                "response remains outside the vertical grillage."
            ),
        ),
        VariableActionScope(
            "Centrifugal traffic action",
            "not wired",
            "Curved-bridge centrifugal traffic action is not yet connected.",
        ),
        VariableActionScope(
            "Pedestrian / footway live load",
            "implemented / verification-gated",
            (
                "User-defined usable footway strips are solved as characteristic "
                "vertical area loads on the physical final-stage grillage."
            ),
        ),
        VariableActionScope(
            "Thermal action",
            "kinematics implemented / restraint model explicit",
            (
                "Uniform expansion/contraction movement, linear gradient curvature "
                "and transparent restraint-force benchmarks are calculated from "
                "project inputs. Climate/National Annex values and bearing/restraint "
                "conditions remain explicit inputs."
            ),
        ),
        VariableActionScope(
            "Wind action",
            "not wired",
            "Wind loading and accompanying-action combinations are not yet connected.",
        ),
        VariableActionScope(
            "Vehicle impact on safety barrier",
            "local accidental action implemented / horizontal solver pending",
            (
                "The Additional actions workspace calculates the transverse accidental "
                "force, associated barrier-base moment and accompanying vertical wheel "
                "reference action. Restraint-class/anchorage/deck-edge verification remains "
                "a local horizontal design task."
            ),
        ),
        VariableActionScope(
            "Construction-stage actions",
            "implemented / verification-gated",
            (
                "Precast-girder, wet-deck and superimposed permanent actions are "
                "separated by physical stage, with an explicit optional execution UDL. "
                "The detailed construction grillage remains the route for temporary "
                "transverse members, propping or changed supports/continuity."
            ),
        ),
    )
