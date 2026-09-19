from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.application.extended_actions import (
    ExtendedActionSettings,
    ExtendedActionSuite,
)
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import EurocodeFactors
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
)
from rc_bridge.workflow.project_bridge import girder_characteristic_permanent_effects


@dataclass(frozen=True)
class BridgeActionCombinationFactors:
    """User-visible first-generation bridge action combination parameters."""

    uls: EurocodeFactors
    gamma_q_nontraffic: float = 1.50
    psi1_lm2: float = 0.75
    psi0_thermal_uls: float = 0.0
    psi0_thermal_sls: float = 0.60
    psi1_thermal: float = 0.60
    psi2_thermal: float = 0.50

    def __post_init__(self) -> None:
        if self.gamma_q_nontraffic <= 0.0:
            raise ValueError("gamma_q_nontraffic must be positive.")
        for name, value in (
            ("psi1_lm2", self.psi1_lm2),
            ("psi0_thermal_uls", self.psi0_thermal_uls),
            ("psi0_thermal_sls", self.psi0_thermal_sls),
            ("psi1_thermal", self.psi1_thermal),
            ("psi2_thermal", self.psi2_thermal),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie between 0 and 1.")


@dataclass(frozen=True)
class VerticalActionSituation:
    name: str
    group: str
    variable_effects: LoadEffects
    uls_effects: LoadEffects
    characteristic_sls_effects: LoadEffects
    frequent_sls_effects: LoadEffects
    quasi_permanent_sls_effects: LoadEffects
    basis: str


@dataclass(frozen=True)
class GirderActionEnvelope:
    girder_index: int
    permanent: LoadEffects
    situations: tuple[VerticalActionSituation, ...]
    uls_effects: LoadEffects
    characteristic_sls_effects: LoadEffects
    frequent_sls_effects: LoadEffects
    quasi_permanent_sls_effects: LoadEffects
    governing_uls_moment_situation: str
    governing_uls_shear_situation: str
    governing_uls_torsion_situation: str
    governing_characteristic_moment_situation: str
    governing_frequent_moment_situation: str

    def equivalent_variable_for_uls(
        self,
        factors: EurocodeFactors,
    ) -> LoadEffects:
        """Return a synthetic Q envelope reproducing the governing ULS components.

        Moment, shear and torsion may come from different compatible situations.
        This envelope is used for independent component design checks, not as a
        claim that all three effects occur in one physical load arrangement.
        """

        gamma_g = factors.gamma_g_unfavourable
        gamma_q = factors.gamma_q_traffic

        def q_from(uls: float, permanent: float) -> float:
            return max((uls - gamma_g * permanent) / gamma_q, 0.0)

        return LoadEffects(
            moment_knm=q_from(
                self.uls_effects.moment_knm,
                self.permanent.moment_knm,
            ),
            shear_kn=q_from(
                self.uls_effects.shear_kn,
                self.permanent.shear_kn,
            ),
            torsion_knm=q_from(
                self.uls_effects.torsion_knm,
                self.permanent.torsion_knm,
            ),
        )


@dataclass(frozen=True)
class BearingActionDesignResult:
    restrained_support_line: int
    bearing_count_on_restrained_line: int
    braking_characteristic_kn: float
    thermal_restrained_expansion_kn: float
    thermal_restrained_contraction_kn: float
    persistent_uls_total_longitudinal_kn: float
    persistent_uls_governing_situation: str
    persistent_uls_per_bearing_kn: float
    characteristic_sls_total_longitudinal_kn: float
    characteristic_sls_per_bearing_kn: float
    required_movement_mm: float
    force_capacity_per_bearing_kn: float | None
    movement_capacity_mm: float | None
    force_utilization: float | None
    movement_utilization: float | None
    passes_specified_capacities: bool | None
    status: str


@dataclass(frozen=True)
class BarrierLocalDesignResult:
    transverse_accidental_demand_kn: float
    base_moment_accidental_demand_knm: float
    accompanying_vertical_wheel_kn: float
    transverse_resistance_kn: float | None
    base_moment_resistance_knm: float | None
    transverse_utilization: float | None
    moment_utilization: float | None
    passes_specified_capacities: bool | None
    status: str


@dataclass(frozen=True)
class IntegratedActionCombinationSuite:
    girders: tuple[GirderActionEnvelope, ...]
    bearing: BearingActionDesignResult | None
    barrier: BarrierLocalDesignResult | None
    blockers: tuple[str, ...]

    @property
    def complete_for_available_models(self) -> bool:
        return not self.blockers


def _effects_from_lm1(
    result: ProjectNativeLM1GrillageSearchResult,
    girder_index: int,
) -> LoadEffects:
    row = result.girders[girder_index - 1]
    return LoadEffects(
        moment_knm=row.moment_knm.value,
        shear_kn=row.shear_kn.value,
        torsion_knm=row.torsion_knm.value,
    )


def _effects_from_action_rows(rows, girder_index: int) -> LoadEffects:
    for row in rows:
        if row.girder_index == girder_index:
            return row.effects
    return LoadEffects()


def _component_envelope(
    situations: tuple[VerticalActionSituation, ...],
    *,
    attribute: str,
) -> tuple[LoadEffects, str]:
    if not situations:
        raise ValueError("At least one vertical action situation is required.")
    if attribute == "uls":
        getter = lambda item: item.uls_effects
    elif attribute == "characteristic":
        getter = lambda item: item.characteristic_sls_effects
    elif attribute == "frequent":
        getter = lambda item: item.frequent_sls_effects
    elif attribute == "quasi":
        getter = lambda item: item.quasi_permanent_sls_effects
    else:
        raise ValueError(f"Unsupported envelope attribute: {attribute}")

    effects = tuple((item.name, getter(item)) for item in situations)
    moment_name, moment = max(effects, key=lambda item: abs(item[1].moment_knm))
    shear_name, shear = max(effects, key=lambda item: abs(item[1].shear_kn))
    torsion_name, torsion = max(effects, key=lambda item: abs(item[1].torsion_knm))
    return (
        LoadEffects(
            moment_knm=abs(moment.moment_knm),
            shear_kn=abs(shear.shear_kn),
            torsion_knm=abs(torsion.torsion_knm),
        ),
        f"M:{moment_name}; V:{shear_name}; T:{torsion_name}",
    )


def _traffic_situation(
    *,
    name: str,
    group: str,
    permanent: LoadEffects,
    variable: LoadEffects,
    uls_factors: EurocodeFactors,
    frequent_variable: LoadEffects,
    quasi_variable: LoadEffects | None = None,
    basis: str,
) -> VerticalActionSituation:
    quasi = LoadEffects() if quasi_variable is None else quasi_variable
    return VerticalActionSituation(
        name=name,
        group=group,
        variable_effects=variable,
        uls_effects=(
            permanent.scaled(uls_factors.gamma_g_unfavourable)
            + variable.scaled(uls_factors.gamma_q_traffic)
        ),
        characteristic_sls_effects=permanent + variable,
        frequent_sls_effects=permanent + frequent_variable,
        quasi_permanent_sls_effects=permanent + quasi,
        basis=basis,
    )


def build_vertical_action_envelopes(
    project: ProjectInput,
    lm1: ProjectNativeLM1GrillageSearchResult,
    actions: ExtendedActionSuite,
    *,
    settings: ExtendedActionSettings,
    factors: BridgeActionCombinationFactors,
) -> tuple[GirderActionEnvelope, ...]:
    """Build mutually compatible road-traffic group envelopes per girder.

    The implementation follows the first-generation EN 1991-2 group concept:
    gr1a = LM1 + reduced pedestrian footway value, gr1b = LM2, gr2 =
    horizontal traffic with frequent LM1 vertical component, and gr3 =
    pedestrian loading. These groups are evaluated separately and then enveloped.
    """

    rows: list[GirderActionEnvelope] = []
    count = int(project.geometry.girder_count)
    for girder_index in range(1, count + 1):
        permanent = girder_characteristic_permanent_effects(
            project,
            girder_index=girder_index,
        )
        lm1_effects = _effects_from_lm1(lm1, girder_index)

        pedestrian = LoadEffects()
        pedestrian_reduced = LoadEffects()
        if actions.pedestrian is not None and actions.pedestrian.applied:
            pedestrian = _effects_from_action_rows(
                actions.pedestrian.girders,
                girder_index,
            )
            ratio = min(
                settings.pedestrian_reduced_with_lm1_kn_m2
                / settings.pedestrian_load_kn_m2,
                1.0,
            )
            pedestrian_reduced = pedestrian.scaled(ratio)

        frequent_lm1 = LoadEffects()
        if actions.gr2_frequent_lm1 is not None:
            frequent_lm1 = _effects_from_lm1(
                actions.gr2_frequent_lm1.search,
                girder_index,
            )

        situations: list[VerticalActionSituation] = []
        situations.append(
            _traffic_situation(
                name="gr1a LM1 + reduced footway",
                group="gr1a",
                permanent=permanent,
                variable=lm1_effects + pedestrian_reduced,
                uls_factors=factors.uls,
                frequent_variable=frequent_lm1,
                basis=(
                    "LM1 characteristic vertical traffic with reduced footway "
                    "pedestrian value; compatible EN 1991-2 traffic group gr1a."
                ),
            )
        )

        if actions.lm2 is not None:
            lm2 = _effects_from_action_rows(actions.lm2.girders, girder_index)
            situations.append(
                _traffic_situation(
                    name="gr1b LM2 isolated axle",
                    group="gr1b",
                    permanent=permanent,
                    variable=lm2,
                    uls_factors=factors.uls,
                    frequent_variable=lm2.scaled(factors.psi1_lm2),
                    basis=(
                        "LM2 isolated axle as separate EN 1991-2 group gr1b; "
                        "not combined at full value with LM1."
                    ),
                )
            )

        if actions.braking is not None and actions.gr2_frequent_lm1 is not None:
            situations.append(
                _traffic_situation(
                    name="gr2 braking with frequent LM1 vertical",
                    group="gr2",
                    permanent=permanent,
                    variable=frequent_lm1,
                    uls_factors=factors.uls,
                    frequent_variable=LoadEffects(),
                    basis=(
                        "Vertical component of gr2 uses native frequent LM1; "
                        "the associated braking/acceleration force is checked in "
                        "the longitudinal bearing/restraint path."
                    ),
                )
            )

        if actions.pedestrian is not None and actions.pedestrian.applied:
            situations.append(
                _traffic_situation(
                    name="gr3 pedestrian footway",
                    group="gr3",
                    permanent=permanent,
                    variable=pedestrian,
                    uls_factors=factors.uls,
                    frequent_variable=LoadEffects(),
                    basis=(
                        "Characteristic pedestrian footway load as separate "
                        "EN 1991-2 traffic group gr3."
                    ),
                )
            )

        situation_tuple = tuple(situations)
        uls, uls_names = _component_envelope(situation_tuple, attribute="uls")
        char, char_names = _component_envelope(
            situation_tuple,
            attribute="characteristic",
        )
        freq, freq_names = _component_envelope(
            situation_tuple,
            attribute="frequent",
        )
        quasi, _ = _component_envelope(situation_tuple, attribute="quasi")

        def governing_name(effect_kind: str, summary: str) -> str:
            prefix = {"moment": "M:", "shear": "V:", "torsion": "T:"}[effect_kind]
            for item in summary.split("; "):
                if item.startswith(prefix):
                    return item[len(prefix) :]
            raise RuntimeError("Governing situation summary is malformed.")

        rows.append(
            GirderActionEnvelope(
                girder_index=girder_index,
                permanent=permanent,
                situations=situation_tuple,
                uls_effects=uls,
                characteristic_sls_effects=char,
                frequent_sls_effects=freq,
                quasi_permanent_sls_effects=quasi,
                governing_uls_moment_situation=governing_name(
                    "moment",
                    uls_names,
                ),
                governing_uls_shear_situation=governing_name(
                    "shear",
                    uls_names,
                ),
                governing_uls_torsion_situation=governing_name(
                    "torsion",
                    uls_names,
                ),
                governing_characteristic_moment_situation=governing_name(
                    "moment",
                    char_names,
                ),
                governing_frequent_moment_situation=governing_name(
                    "moment",
                    freq_names,
                ),
            )
        )
    return tuple(rows)


def build_bearing_action_design(
    project: ProjectInput,
    actions: ExtendedActionSuite,
    *,
    settings: ExtendedActionSettings,
    factors: BridgeActionCombinationFactors,
) -> BearingActionDesignResult | None:
    if actions.braking is None and actions.thermal is None:
        return None

    braking = 0.0 if actions.braking is None else actions.braking.characteristic_force_kn
    thermal_exp = (
        0.0
        if actions.thermal is None
        else actions.thermal.modelled_restraint_expansion_force_kn
    )
    thermal_con = (
        0.0
        if actions.thermal is None
        else actions.thermal.modelled_restraint_contraction_force_kn
    )
    thermal_force = max(abs(thermal_exp), abs(thermal_con))

    braking_leading = (
        factors.uls.gamma_q_traffic * braking
        + factors.gamma_q_nontraffic * factors.psi0_thermal_uls * thermal_force
    )
    thermal_leading = factors.gamma_q_nontraffic * thermal_force
    if braking_leading >= thermal_leading:
        uls_total = braking_leading
        governing = "gr2 braking leading + accompanying thermal"
    else:
        uls_total = thermal_leading
        governing = "thermal leading; gr2 accompanying factor = 0"

    sls_braking_leading = braking + factors.psi0_thermal_sls * thermal_force
    sls_thermal_leading = thermal_force
    sls_total = max(sls_braking_leading, sls_thermal_leading)

    bearing_count = int(project.geometry.girder_count)
    per_bearing = uls_total / bearing_count if bearing_count > 0 else 0.0
    per_bearing_sls = sls_total / bearing_count if bearing_count > 0 else 0.0
    movement = 0.0
    if actions.thermal is not None:
        movement = max(
            abs(actions.thermal.expansion_movement_mm),
            abs(actions.thermal.contraction_movement_mm),
        )

    force_capacity = (
        settings.bearing_longitudinal_capacity_per_bearing_kn
        if settings.bearing_longitudinal_capacity_per_bearing_kn > 0.0
        else None
    )
    movement_capacity = (
        settings.bearing_movement_capacity_mm
        if settings.bearing_movement_capacity_mm > 0.0
        else None
    )
    force_util = (
        per_bearing / force_capacity
        if force_capacity is not None
        else None
    )
    movement_util = (
        movement / movement_capacity
        if movement_capacity is not None
        else None
    )
    passes = None
    if force_util is not None or movement_util is not None:
        passes = (
            (force_util is None or force_util <= 1.0 + 1.0e-9)
            and (movement_util is None or movement_util <= 1.0 + 1.0e-9)
        )

    return BearingActionDesignResult(
        restrained_support_line=1,
        bearing_count_on_restrained_line=bearing_count,
        braking_characteristic_kn=braking,
        thermal_restrained_expansion_kn=thermal_exp,
        thermal_restrained_contraction_kn=thermal_con,
        persistent_uls_total_longitudinal_kn=uls_total,
        persistent_uls_governing_situation=governing,
        persistent_uls_per_bearing_kn=per_bearing,
        characteristic_sls_total_longitudinal_kn=sls_total,
        characteristic_sls_per_bearing_kn=per_bearing_sls,
        required_movement_mm=movement,
        force_capacity_per_bearing_kn=force_capacity,
        movement_capacity_mm=movement_capacity,
        force_utilization=force_util,
        movement_utilization=movement_util,
        passes_specified_capacities=passes,
        status=(
            "Equilibrium bearing/restraint design path: the restrained support line "
            "takes the longitudinal resultant and shares it equally between girder "
            "bearings. This is not a substitute for a detailed substructure/bearing "
            "stiffness model where load sharing is non-uniform."
        ),
    )


def build_barrier_local_design(
    actions: ExtendedActionSuite,
    *,
    settings: ExtendedActionSettings,
) -> BarrierLocalDesignResult | None:
    if actions.barrier_impact is None:
        return None
    demand = actions.barrier_impact
    transverse_resistance = (
        settings.barrier_transverse_resistance_kn
        if settings.barrier_transverse_resistance_kn > 0.0
        else None
    )
    moment_resistance = (
        settings.barrier_base_moment_resistance_knm
        if settings.barrier_base_moment_resistance_knm > 0.0
        else None
    )
    transverse_util = (
        demand.transverse_characteristic_force_kn / transverse_resistance
        if transverse_resistance is not None
        else None
    )
    moment_util = (
        demand.barrier_base_moment_knm / moment_resistance
        if moment_resistance is not None
        else None
    )
    passes = None
    if transverse_util is not None or moment_util is not None:
        passes = (
            (transverse_util is None or transverse_util <= 1.0 + 1.0e-9)
            and (moment_util is None or moment_util <= 1.0 + 1.0e-9)
        )
    return BarrierLocalDesignResult(
        transverse_accidental_demand_kn=demand.transverse_characteristic_force_kn,
        base_moment_accidental_demand_knm=demand.barrier_base_moment_knm,
        accompanying_vertical_wheel_kn=demand.accompanying_vertical_wheel_load_kn,
        transverse_resistance_kn=transverse_resistance,
        base_moment_resistance_knm=moment_resistance,
        transverse_utilization=transverse_util,
        moment_utilization=moment_util,
        passes_specified_capacities=passes,
        status=(
            "Accidental local barrier demand is retained separately from normal "
            "traffic groups. If certified barrier/deck-edge design resistances are "
            "entered, demand/capacity checks are reported; otherwise the result is "
            "demand-only and remains a project-design blocker."
        ),
    )


def build_integrated_action_combinations(
    project: ProjectInput,
    lm1: ProjectNativeLM1GrillageSearchResult,
    actions: ExtendedActionSuite,
    *,
    settings: ExtendedActionSettings,
    factors: BridgeActionCombinationFactors,
) -> IntegratedActionCombinationSuite:
    girders = build_vertical_action_envelopes(
        project,
        lm1,
        actions,
        settings=settings,
        factors=factors,
    )
    bearing = build_bearing_action_design(
        project,
        actions,
        settings=settings,
        factors=factors,
    )
    barrier = build_barrier_local_design(actions, settings=settings)

    blockers: list[str] = []
    blockers.extend(actions.unresolved_inputs)
    if bearing is not None:
        if bearing.force_capacity_per_bearing_kn is None:
            blockers.append("bearing longitudinal resistance not specified")
        if bearing.movement_capacity_mm is None:
            blockers.append("bearing movement capacity not specified")
        if bearing.passes_specified_capacities is False:
            blockers.append("bearing longitudinal/movement capacity exceeded")
    if barrier is not None:
        if barrier.transverse_resistance_kn is None:
            blockers.append("safety-barrier transverse resistance not specified")
        if barrier.base_moment_resistance_knm is None:
            blockers.append("safety-barrier base-moment resistance not specified")
        if barrier.passes_specified_capacities is False:
            blockers.append("safety-barrier local resistance exceeded")

    return IntegratedActionCombinationSuite(
        girders=girders,
        bearing=bearing,
        barrier=barrier,
        blockers=tuple(dict.fromkeys(blockers)),
    )
