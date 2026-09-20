from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.physical_sections import girder_web_width_m
from rc_bridge.application.design_checks import ApplicationDesignInterpretationSuite
from rc_bridge.application.fatigue import FatigueApplicationResult
from rc_bridge.application.load_cases import (
    application_combination_summary,
    permanent_load_audit,
)
from rc_bridge.application.local_deck import LocalDeckDesignResult
from rc_bridge.application.math_notation import (
    MathExpr,
    absolute,
    fraction,
    identifier,
    number,
    operator,
    parenthesized,
    sqrt,
    sub,
    sup,
    text,
)
from rc_bridge.application.math_notation import (
    row as math_row,
)
from rc_bridge.application.preferences import ApplicationPreferences
from rc_bridge.core.models import ProjectInput
from rc_bridge.design.eurocode_layered_section import layered_singly_reinforced_resistance
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult


@dataclass(frozen=True)
class CalculationStep:
    label: str
    expression: str
    substitution: str
    result: str
    reference: str = ""
    status: str = ""
    equation: MathExpr | None = None
    substitution_equation: MathExpr | None = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Calculation-step label cannot be empty.")
        if not self.result.strip():
            raise ValueError("Calculation-step result cannot be empty.")


@dataclass(frozen=True)
class CalculationBlock:
    title: str
    scope: str
    steps: tuple[CalculationStep, ...]

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("Calculation-block title cannot be empty.")
        if not self.steps:
            raise ValueError("Calculation blocks require at least one step.")


@dataclass(frozen=True)
class CalculationTrace:
    project_name: str
    blocks: tuple[CalculationBlock, ...]

    @property
    def step_count(self) -> int:
        return sum(len(block.steps) for block in self.blocks)


def _f(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def _num(value: float, digits: int = 3) -> MathExpr:
    return number(_f(value, digits))


def _var(name: str, script: str | None = None) -> MathExpr:
    base = identifier(name)
    return base if script is None else sub(base, script)


def _eq(left: MathExpr, right: MathExpr) -> MathExpr:
    return math_row(left, operator("="), right)


def _sum(*items: MathExpr) -> MathExpr:
    parts: list[MathExpr] = []
    for index, item in enumerate(items):
        if index:
            parts.append(operator("+"))
        parts.append(item)
    return math_row(*parts)


def _product(*items: MathExpr) -> MathExpr:
    parts: list[MathExpr] = []
    for index, item in enumerate(items):
        if index:
            parts.append(operator("×"))
        parts.append(item)
    return math_row(*parts)


def _analysis_formulation_block(
    result: ProjectNativeLM1GrillageSearchResult,
) -> CalculationBlock | None:
    """Expose one actual grillage-member stiffness path used by the native solver."""

    if not result.cases:
        return None
    model = result.cases[0].model
    nodes = {node.node_id: node for node in model.nodes}
    representative = next(
        (
            beam
            for beam in model.beams
            if abs(nodes[beam.node_j].x_m - nodes[beam.node_i].x_m) > 1.0e-9
            and abs(nodes[beam.node_j].y_m - nodes[beam.node_i].y_m) <= 1.0e-9
        ),
        None,
    )
    if representative is None:
        return None

    material = next(
        item for item in model.materials if item.material_id == representative.material_id
    )
    section = next(
        item for item in model.sections if item.section_id == representative.section_id
    )
    length_m = model.member_length_m(representative.member_id)
    e_kn_m2 = material.elastic_modulus_kn_m2
    nu = material.poisson_ratio
    g_kn_m2 = e_kn_m2 / (2.0 * (1.0 + nu))
    ei_kn_m2 = e_kn_m2 * section.iy_m4
    gj_kn_m2 = g_kn_m2 * section.torsion_constant_m4
    bending_stiffness = 12.0 * ei_kn_m2 / length_m**3
    torsional_stiffness = gj_kn_m2 / length_m

    return CalculationBlock(
        title="Native grillage analysis - representative member formulation",
        scope=(
            f"Member {representative.member_id} is taken directly from a retained native "
            "LM1 grillage model. The report exposes the stiffness quantities used by the "
            "solver without recreating a separate analysis engine."
        ),
        steps=(
            CalculationStep(
                label="Concrete shear modulus",
                expression="G = E / [2(1 + nu)]",
                substitution=(
                    f"{_f(e_kn_m2)} / [2(1 + {_f(nu)})]"
                ),
                result=f"{_f(g_kn_m2)} kN/m2",
                reference="Linear-elastic isotropic material relation",
                equation=_eq(
                    identifier("G"),
                    fraction(
                        identifier("E"),
                        _product(number("2"), parenthesized(_sum(number("1"), identifier("ν")))),
                    ),
                ),
                substitution_equation=_eq(
                    identifier("G"),
                    fraction(
                        _num(e_kn_m2),
                        _product(number("2"), parenthesized(_sum(number("1"), _num(nu)))),
                    ),
                ),
            ),
            CalculationStep(
                label="Vertical-bending rigidity",
                expression="EI = E Iy",
                substitution=f"{_f(e_kn_m2)} x {_f(section.iy_m4, 9)}",
                result=f"{_f(ei_kn_m2)} kN m2",
                reference="Native vertical grillage element",
                equation=_eq(
                    math_row(identifier("E"), _var("I", "y")),
                    _product(identifier("E"), _var("I", "y")),
                ),
                substitution_equation=_eq(
                    math_row(identifier("E"), _var("I", "y")),
                    _product(_num(e_kn_m2), _num(section.iy_m4, 9)),
                ),
            ),
            CalculationStep(
                label="Saint-Venant torsional rigidity",
                expression="GJ = G J",
                substitution=f"{_f(g_kn_m2)} x {_f(section.torsion_constant_m4, 9)}",
                result=f"{_f(gj_kn_m2)} kN m2",
                reference="Native vertical grillage element",
                equation=_eq(
                    math_row(identifier("G"), identifier("J")),
                    _product(identifier("G"), identifier("J")),
                ),
                substitution_equation=_eq(
                    math_row(identifier("G"), identifier("J")),
                    _product(_num(g_kn_m2), _num(section.torsion_constant_m4, 9)),
                ),
            ),
            CalculationStep(
                label="Representative vertical member stiffness coefficient",
                expression="kww = 12 EI / L^3",
                substitution=(
                    f"12 x {_f(ei_kn_m2)} / {_f(length_m)}^3"
                ),
                result=f"{_f(bending_stiffness)} kN/m",
                reference="Euler-Bernoulli grillage member stiffness matrix",
                equation=_eq(
                    _var("k", "ww"),
                    fraction(
                        _product(number("12"), identifier("E"), _var("I", "y")),
                        sup(identifier("L"), 3),
                    ),
                ),
                substitution_equation=_eq(
                    _var("k", "ww"),
                    fraction(
                        _product(number("12"), _num(ei_kn_m2)),
                        sup(_num(length_m), 3),
                    ),
                ),
            ),
            CalculationStep(
                label="Representative torsional stiffness coefficient",
                expression="kt = GJ / L",
                substitution=f"{_f(gj_kn_m2)} / {_f(length_m)}",
                result=f"{_f(torsional_stiffness)} kNm/rad",
                reference="Saint-Venant torsion in native grillage member",
                equation=_eq(
                    _var("k", "t"),
                    fraction(math_row(identifier("G"), identifier("J")), identifier("L")),
                ),
                substitution_equation=_eq(
                    _var("k", "t"),
                    fraction(_num(gj_kn_m2), _num(length_m)),
                ),
            ),
            CalculationStep(
                label="Global displacement solution",
                expression="K u = F",
                substitution="assembled sparse grillage system; constrained DOFs removed",
                result="nodal w, Rx and Ry",
                reference="Native sparse grillage solver",
                equation=_eq(
                    math_row(identifier("K"), identifier("u")),
                    identifier("F"),
                ),
            ),
            CalculationStep(
                label="Recovered member-end actions",
                expression="qe = ke ue - fe",
                substitution="element displacement vector transformed back to local axes",
                result="V, M and T at I/J ends",
                reference="Native grillage member-force recovery",
                equation=_eq(
                    _var("q", "e"),
                    math_row(
                        _var("k", "e"),
                        _var("u", "e"),
                        operator("−"),
                        _var("f", "e"),
                    ),
                ),
            ),
        ),
    )


def _combination_blocks(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
    preferences: ApplicationPreferences,
) -> tuple[CalculationBlock, ...]:
    try:
        combinations = application_combination_summary(
            project,
            result,
            uls_factors=preferences.eurocode.uls_factors,
            sls_factors=preferences.eurocode.sls_factors,
        )
    except ValueError:
        return ()

    blocks: list[CalculationBlock] = []
    ec = preferences.eurocode
    for row in combinations:
        g_m = row.permanent_characteristic.moment_knm
        q_m = row.traffic_characteristic.moment_knm
        g_v = row.permanent_characteristic.shear_kn
        q_v = row.traffic_characteristic.shear_kn
        blocks.append(
            CalculationBlock(
                title=f"Girder {row.girder_index} - action combinations",
                scope="Characteristic permanent and LM1 traffic effects combined for the simple-span application path.",
                steps=(
                    CalculationStep(
                        label="ULS bending moment",
                        expression="MEd = gamma_G * MGk + gamma_Q * MQk",
                        substitution=(
                            f"{ec.gamma_g_unfavourable:g} x {_f(g_m)} + "
                            f"{ec.gamma_q_traffic:g} x {_f(q_m)}"
                        ),
                        result=f"{_f(row.uls.moment_knm)} kNm",
                        reference="EN 1990 persistent design situation; EN 1991-2 traffic action",
                        equation=_eq(
                            _var("M", "Ed"),
                            _sum(
                                _product(_var("γ", "G"), _var("M", "Gk")),
                                _product(_var("γ", "Q"), _var("M", "Qk")),
                            ),
                        ),
                        substitution_equation=_eq(
                            _var("M", "Ed"),
                            _sum(
                                _product(number(f"{ec.gamma_g_unfavourable:g}"), _num(g_m)),
                                _product(number(f"{ec.gamma_q_traffic:g}"), _num(q_m)),
                            ),
                        ),
                    ),
                    CalculationStep(
                        label="ULS shear",
                        expression="VEd = gamma_G * VGk + gamma_Q * VQk",
                        substitution=(
                            f"{ec.gamma_g_unfavourable:g} x {_f(g_v)} + "
                            f"{ec.gamma_q_traffic:g} x {_f(q_v)}"
                        ),
                        result=f"{_f(row.uls.shear_kn)} kN",
                        reference="EN 1990 persistent design situation; EN 1991-2 traffic action",
                        equation=_eq(
                            _var("V", "Ed"),
                            _sum(
                                _product(_var("γ", "G"), _var("V", "Gk")),
                                _product(_var("γ", "Q"), _var("V", "Qk")),
                            ),
                        ),
                        substitution_equation=_eq(
                            _var("V", "Ed"),
                            _sum(
                                _product(number(f"{ec.gamma_g_unfavourable:g}"), _num(g_v)),
                                _product(number(f"{ec.gamma_q_traffic:g}"), _num(q_v)),
                            ),
                        ),
                    ),
                    CalculationStep(
                        label="SLS characteristic moment",
                        expression="M = MGk + MQk",
                        substitution=f"{_f(g_m)} + {_f(q_m)}",
                        result=f"{_f(row.sls_characteristic.moment_knm)} kNm",
                        reference="EN 1990 characteristic serviceability combination",
                        equation=_eq(
                            identifier("M"),
                            _sum(_var("M", "Gk"), _var("M", "Qk")),
                        ),
                        substitution_equation=_eq(
                            identifier("M"),
                            _sum(_num(g_m), _num(q_m)),
                        ),
                    ),
                    CalculationStep(
                        label="SLS frequent moment",
                        expression="M = MGk + psi1 * MQk",
                        substitution=(
                            f"{_f(g_m)} + {ec.psi1_traffic:g} x {_f(q_m)}"
                        ),
                        result=f"{_f(row.sls_frequent.moment_knm)} kNm",
                        reference="EN 1990 frequent serviceability combination",
                        equation=_eq(
                            identifier("M"),
                            _sum(
                                _var("M", "Gk"),
                                _product(_var("ψ", "1"), _var("M", "Qk")),
                            ),
                        ),
                        substitution_equation=_eq(
                            identifier("M"),
                            _sum(
                                _num(g_m),
                                _product(number(f"{ec.psi1_traffic:g}"), _num(q_m)),
                            ),
                        ),
                    ),
                    CalculationStep(
                        label="SLS quasi-permanent moment",
                        expression="M = MGk + psi2 * MQk",
                        substitution=(
                            f"{_f(g_m)} + {ec.psi2_traffic:g} x {_f(q_m)}"
                        ),
                        result=f"{_f(row.sls_quasi_permanent.moment_knm)} kNm",
                        reference="EN 1990 quasi-permanent serviceability combination",
                        equation=_eq(
                            identifier("M"),
                            _sum(
                                _var("M", "Gk"),
                                _product(_var("ψ", "2"), _var("M", "Qk")),
                            ),
                        ),
                        substitution_equation=_eq(
                            identifier("M"),
                            _sum(
                                _num(g_m),
                                _product(number(f"{ec.psi2_traffic:g}"), _num(q_m)),
                            ),
                        ),
                    ),
                ),
            )
        )
    return tuple(blocks)


def build_application_calculation_trace(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
    *,
    preferences: ApplicationPreferences,
    local_deck_design: LocalDeckDesignResult | None = None,
    design_interpretation: ApplicationDesignInterpretationSuite | None = None,
    fatigue: FatigueApplicationResult | None = None,
) -> CalculationTrace:
    """Build reusable worked-calculation records for both GUI and reports.

    The trace records the values actually used by the deterministic engine. It does
    not invent hidden intermediate values that are not exposed by the solver.
    """

    blocks: list[CalculationBlock] = []

    analysis_block = _analysis_formulation_block(result)
    if analysis_block is not None:
        blocks.append(analysis_block)

    for row in permanent_load_audit(project):
        components = (
            row.girder_self_weight_kn_m,
            row.false_slab_kn_m,
            row.in_situ_slab_kn_m,
            row.surfacing_kn_m,
            row.barriers_kn_m,
            row.services_kn_m,
            row.other_kn_m,
        )
        blocks.append(
            CalculationBlock(
                title=f"Girder {row.girder_index} - permanent actions",
                scope="Equivalent characteristic line-load audit over the bridge length.",
                steps=(
                    CalculationStep(
                        label="Total characteristic permanent line load",
                        expression=(
                            "Gk = g_girder + g_false + g_insitu + g_surfacing + "
                            "g_barriers + g_services + g_other"
                        ),
                        substitution=" + ".join(_f(value) for value in components),
                        result=f"{_f(row.total_equivalent_kn_m)} kN/m",
                        reference="Project permanent-action model and physical self-weight",
                        equation=_eq(
                            _var("G", "k"),
                            _sum(
                                _var("g", "girder"),
                                _var("g", "false"),
                                _var("g", "insitu"),
                                _var("g", "surf"),
                                _var("g", "bar"),
                                _var("g", "serv"),
                                _var("g", "other"),
                            ),
                        ),
                        substitution_equation=_eq(
                            _var("G", "k"),
                            _sum(*(_num(value) for value in components)),
                        ),
                    ),
                ),
            )
        )

    for girder in result.girders:
        blocks.append(
            CalculationBlock(
                title=f"Girder {girder.girder_index} - LM1 governing traffic effects",
                scope="Envelope values retained from the native full-width moving LM1 search.",
                steps=(
                    CalculationStep(
                        label="Governing LM1 bending moment",
                        expression="MQk = max over analysed LM1 placements |M|",
                        substitution=f"governing case {girder.moment_knm.case_id}",
                        result=f"{_f(girder.moment_knm.value)} kNm",
                        reference="EN 1991-2 LM1; native grillage search",
                    ),
                    CalculationStep(
                        label="Governing LM1 shear",
                        expression="VQk = max over analysed LM1 placements |V|",
                        substitution=f"governing case {girder.shear_kn.case_id}",
                        result=f"{_f(girder.shear_kn.value)} kN",
                        reference="EN 1991-2 LM1; native grillage search",
                    ),
                    CalculationStep(
                        label="Governing LM1 torsion",
                        expression="TQk = max over analysed LM1 placements |T|",
                        substitution=f"governing case {girder.torsion_knm.case_id}",
                        result=f"{_f(girder.torsion_knm.value)} kNm",
                        reference="EN 1991-2 LM1; native grillage search",
                    ),
                ),
            )
        )

    blocks.extend(_combination_blocks(project, result, preferences))

    if design_interpretation is not None:
        for row in design_interpretation.girders:
            flexure = row.design.uls_design.flexure
            ved = abs(row.design.uls_design.design_effects.shear_kn)
            provided_flexure = layered_singly_reinforced_resistance(
                layers=row.design.concrete_layers,
                effective_depth_m=row.effective_depth_m,
                steel_area_mm2=row.selected_bars.provided_area_mm2,
                fck_mpa=float(project.materials.fck_mpa),
                fyk_mpa=float(project.materials.fyk_mpa),
            )
            fcd_mpa = float(project.materials.fck_mpa) / 1.50
            fyd_mpa = float(project.materials.fyk_mpa) / 1.15
            bw_mm = girder_web_width_m(project.geometry) * 1000.0
            d_mm = row.effective_depth_m * 1000.0
            k_shear = min(1.0 + (200.0 / d_mm) ** 0.5, 2.0)
            rho_l = min(
                row.selected_bars.provided_area_mm2 / (bw_mm * d_mm),
                0.02,
            )
            vrdc_mpa = max(
                (0.18 / 1.50)
                * k_shear
                * (100.0 * rho_l * float(project.materials.fck_mpa)) ** (1.0 / 3.0),
                0.035 * k_shear**1.5 * float(project.materials.fck_mpa) ** 0.5,
            )
            shear_resistance = (
                ved / row.design.shear_utilization
                if row.design.shear_utilization > 0.0
                else 0.0
            )
            span_m = float(project.geometry.span_lengths_m[0])
            deflection_limit_mm = (
                span_m * 1000.0 / preferences.eurocode.deflection_limit_span_ratio
            )
            blocks.append(
                CalculationBlock(
                    title=f"Girder {row.girder_index} - longitudinal RC design",
                    scope=(
                        f"Governing ULS moment: {row.governing_uls_moment_situation}; "
                        f"governing shear: {row.governing_uls_shear_situation}."
                    ),
                    steps=(
                        CalculationStep(
                            label="Design concrete strength",
                            expression="fcd = alpha_cc fck / gamma_c",
                            substitution=(
                                f"{_f(float(project.materials.fck_mpa), 1)} / 1.50"
                            ),
                            result=f"{_f(fcd_mpa)} MPa",
                            reference="EN 1992 material design strength",
                            equation=_eq(
                                _var("f", "cd"),
                                fraction(
                                    _product(_var("α", "cc"), _var("f", "ck")),
                                    _var("γ", "c"),
                                ),
                            ),
                            substitution_equation=_eq(
                                _var("f", "cd"),
                                fraction(
                                    _num(float(project.materials.fck_mpa), 1),
                                    number("1.50"),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Design reinforcement strength",
                            expression="fyd = fyk / gamma_s",
                            substitution=(
                                f"{_f(float(project.materials.fyk_mpa), 1)} / 1.15"
                            ),
                            result=f"{_f(fyd_mpa)} MPa",
                            reference="EN 1992 reinforcement design strength",
                            equation=_eq(
                                _var("f", "yd"),
                                fraction(_var("f", "yk"), _var("γ", "s")),
                            ),
                            substitution_equation=_eq(
                                _var("f", "yd"),
                                fraction(
                                    _num(float(project.materials.fyk_mpa), 1),
                                    number("1.15"),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Effective depth",
                            expression="d = effective tension-steel depth used by layered section solver",
                            substitution="from selected section geometry, cover and bar arrangement",
                            result=f"{_f(row.effective_depth_m * 1000.0, 1)} mm",
                            reference="EN 1992-2 / EC2 section design basis",
                            equation=_eq(identifier("d"), text("effective tension-steel depth")),
                            substitution_equation=_eq(
                                identifier("d"),
                                _num(row.effective_depth_m * 1000.0, 1),
                            ),
                        ),
                        CalculationStep(
                            label="Required longitudinal reinforcement",
                            expression="As,req = layered-section flexural solution for MEd",
                            substitution=f"MEd = {_f(row.design.uls_design.design_effects.moment_knm)} kNm",
                            result=f"{_f(flexure.required_steel_area_mm2, 0)} mm2",
                            reference="EN 1992-1-1 / EN 1992-2 flexure",
                            equation=_eq(
                                _var("M", "Rd"),
                                _product(_var("A", "s"), _var("f", "yd"), identifier("z")),
                            ),
                            substitution_equation=_eq(
                                _var("M", "Ed"),
                                _num(row.design.uls_design.design_effects.moment_knm),
                            ),
                        ),
                        CalculationStep(
                            label="Provided longitudinal reinforcement",
                            expression="As,prov >= As,req",
                            substitution=(
                                f"{row.selected_bars.bar_count}-Y"
                                f"{row.selected_bars.bar_diameter_mm:g}"
                            ),
                            result=f"{_f(row.selected_bars.provided_area_mm2, 0)} mm2",
                            reference="Selected reinforcement arrangement",
                            status="PASS" if row.selected_bars.provided_area_mm2 + 1e-9 >= flexure.required_steel_area_mm2 else "CHECK",
                            equation=_eq(
                                _var("A", "s,prov"),
                                _product(
                                    number(str(row.selected_bars.bar_count)),
                                    fraction(
                                        _product(identifier("π"), sup(identifier("ϕ"), 2)),
                                        number("4"),
                                    ),
                                ),
                            ),
                            substitution_equation=_eq(
                                _var("A", "s,prov"),
                                _product(
                                    number(str(row.selected_bars.bar_count)),
                                    fraction(
                                        _product(
                                            identifier("π"),
                                            sup(_num(row.selected_bars.bar_diameter_mm, 0), 2),
                                        ),
                                        number("4"),
                                    ),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Tension steel force",
                            expression="T = As,prov fyd",
                            substitution=(
                                f"{_f(row.selected_bars.provided_area_mm2, 0)} x "
                                f"{_f(fyd_mpa)}"
                            ),
                            result=f"{_f(provided_flexure.steel_force_kn)} kN",
                            reference="EC2 layered-section force equilibrium",
                            equation=_eq(
                                identifier("T"),
                                _product(_var("A", "s,prov"), _var("f", "yd")),
                            ),
                            substitution_equation=_eq(
                                identifier("T"),
                                _product(
                                    _num(row.selected_bars.provided_area_mm2, 0),
                                    _num(fyd_mpa),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Compression block and lever arm",
                            expression="z = d - yc",
                            substitution=(
                                f"{_f(row.effective_depth_m * 1000.0, 1)} - "
                                f"{_f(provided_flexure.compression_centroid_from_top_m * 1000.0, 1)}"
                            ),
                            result=f"{_f(provided_flexure.lever_arm_m * 1000.0, 1)} mm",
                            reference="Layered participating concrete compression block",
                            equation=_eq(
                                identifier("z"),
                                math_row(identifier("d"), operator("−"), _var("y", "c")),
                            ),
                            substitution_equation=_eq(
                                identifier("z"),
                                math_row(
                                    _num(row.effective_depth_m * 1000.0, 1),
                                    operator("−"),
                                    _num(
                                        provided_flexure.compression_centroid_from_top_m * 1000.0,
                                        1,
                                    ),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Flexural resistance",
                            expression="utilization = MEd / MRd",
                            substitution=(
                                f"{_f(row.design.uls_design.design_effects.moment_knm)} / "
                                f"{_f(flexure.resistance_knm)}"
                            ),
                            result=f"{_f(flexure.utilization)}",
                            reference="EN 1992-1-1 / EN 1992-2 flexure",
                            status="PASS" if flexure.utilization <= 1.0 + 1e-9 else "CHECK",
                            equation=_eq(
                                _var("η", "M"),
                                fraction(_var("M", "Ed"), _var("M", "Rd")),
                            ),
                            substitution_equation=_eq(
                                _var("η", "M"),
                                fraction(
                                    _num(row.design.uls_design.design_effects.moment_knm),
                                    _num(flexure.resistance_knm),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Shear depth factor",
                            expression="k = min[1 + sqrt(200/d), 2.0]",
                            substitution=(
                                f"min[1 + sqrt(200/{_f(d_mm, 1)}), 2.0]"
                            ),
                            result=f"{_f(k_shear)}",
                            reference="EN 1992 concrete shear resistance",
                            equation=_eq(
                                identifier("k"),
                                math_row(
                                    text("min"),
                                    operator("("),
                                    _sum(
                                        number("1"),
                                        sqrt(fraction(number("200"), identifier("d"))),
                                    ),
                                    operator(","),
                                    number("2.0"),
                                    operator(")"),
                                ),
                            ),
                            substitution_equation=_eq(
                                identifier("k"),
                                math_row(
                                    text("min"),
                                    operator("("),
                                    _sum(
                                        number("1"),
                                        sqrt(fraction(number("200"), _num(d_mm, 1))),
                                    ),
                                    operator(","),
                                    number("2.0"),
                                    operator(")"),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Longitudinal reinforcement ratio",
                            expression="rho_l = min[As/(bw d), 0.02]",
                            substitution=(
                                f"min[{_f(row.selected_bars.provided_area_mm2, 0)} / "
                                f"({_f(bw_mm, 0)} x {_f(d_mm, 1)}), 0.02]"
                            ),
                            result=f"{_f(rho_l, 5)}",
                            reference="EN 1992 concrete shear resistance",
                            equation=_eq(
                                _var("ρ", "l"),
                                math_row(
                                    text("min"),
                                    operator("("),
                                    fraction(
                                        _var("A", "s"),
                                        _product(_var("b", "w"), identifier("d")),
                                    ),
                                    operator(","),
                                    number("0.02"),
                                    operator(")"),
                                ),
                            ),
                            substitution_equation=_eq(
                                _var("ρ", "l"),
                                math_row(
                                    text("min"),
                                    operator("("),
                                    fraction(
                                        _num(row.selected_bars.provided_area_mm2, 0),
                                        _product(_num(bw_mm, 0), _num(d_mm, 1)),
                                    ),
                                    operator(","),
                                    number("0.02"),
                                    operator(")"),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Concrete shear stress resistance",
                            expression=(
                                "vRdc = max[(0.18/gamma_c) k (100 rho_l fck)^(1/3), "
                                "0.035 k^(3/2) sqrt(fck)]"
                            ),
                            substitution=(
                                f"max[0.12 x {_f(k_shear)} x "
                                f"(100 x {_f(rho_l, 5)} x "
                                f"{_f(float(project.materials.fck_mpa), 1)})^(1/3), "
                                f"0.035 x {_f(k_shear)}^(3/2) x "
                                f"sqrt({_f(float(project.materials.fck_mpa), 1)})]"
                            ),
                            result=f"{_f(vrdc_mpa)} MPa",
                            reference="EN 1992 concrete shear resistance",
                            equation=_eq(
                                _var("v", "Rd,c"),
                                math_row(
                                    text("max"),
                                    operator("("),
                                    _product(
                                        fraction(number("0.18"), _var("γ", "c")),
                                        identifier("k"),
                                        sup(
                                            parenthesized(
                                                _product(
                                                    number("100"),
                                                    _var("ρ", "l"),
                                                    _var("f", "ck"),
                                                )
                                            ),
                                            fraction(number("1"), number("3")),
                                        ),
                                    ),
                                    operator(","),
                                    _product(
                                        number("0.035"),
                                        sup(identifier("k"), fraction(number("3"), number("2"))),
                                        sqrt(_var("f", "ck")),
                                    ),
                                    operator(")"),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Shear resistance",
                            expression="utilization = |VEd| / VRd",
                            substitution=f"{_f(ved)} / {_f(shear_resistance)}",
                            result=f"{_f(row.design.shear_utilization)}",
                            reference="EN 1992-1-1 / EN 1992-2 shear",
                            status="PASS" if row.design.shear_utilization <= 1.0 + 1e-9 else "CHECK",
                            equation=_eq(
                                _var("η", "V"),
                                fraction(absolute(_var("V", "Ed")), _var("V", "Rd")),
                            ),
                            substitution_equation=_eq(
                                _var("η", "V"),
                                fraction(_num(ved), _num(shear_resistance)),
                            ),
                        ),
                        CalculationStep(
                            label="Effective tension reinforcement ratio",
                            expression="rho_p,eff = As / Ac,eff",
                            substitution=(
                                f"{_f(row.selected_bars.provided_area_mm2, 0)} / "
                                f"{_f(row.design.crack.effective_tension_area_mm2, 0)}"
                            ),
                            result=f"{_f(row.design.crack.effective_reinforcement_ratio, 5)}",
                            reference="EN 1992 crack-control effective tension zone",
                            equation=_eq(
                                _var("ρ", "p,eff"),
                                fraction(_var("A", "s"), _var("A", "c,eff")),
                            ),
                            substitution_equation=_eq(
                                _var("ρ", "p,eff"),
                                fraction(
                                    _num(row.selected_bars.provided_area_mm2, 0),
                                    _num(row.design.crack.effective_tension_area_mm2, 0),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Maximum crack spacing",
                            expression="sr,max from EC2 7.3.4 spacing expression",
                            substitution=(
                                f"c={_f(preferences.design.cover_mm, 1)} mm; "
                                f"phi={_f(row.selected_bars.bar_diameter_mm, 0)} mm; "
                                f"rho_p,eff={_f(row.design.crack.effective_reinforcement_ratio, 5)}"
                            ),
                            result=f"{_f(row.design.crack.max_crack_spacing_mm)} mm",
                            reference="EN 1992 crack spacing",
                            equation=_eq(
                                _var("s", "r,max"),
                                _sum(
                                    _product(number("3.4"), identifier("c")),
                                    fraction(
                                        _product(
                                            number("0.8"),
                                            number("0.5"),
                                            number("0.425"),
                                            identifier("ϕ"),
                                        ),
                                        _var("ρ", "p,eff"),
                                    ),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Crack width",
                            expression="wk = sr,max (epsilon_sm - epsilon_cm)",
                            substitution=(
                                f"{_f(row.design.crack.max_crack_spacing_mm)} x "
                                f"{_f(row.design.crack.strain_difference, 7)}"
                            ),
                            result=f"{_f(row.design.crack.crack_width_mm)} mm",
                            reference="EN 1992 serviceability crack control",
                            equation=_eq(
                                _var("w", "k"),
                                _product(
                                    _var("s", "r,max"),
                                    parenthesized(
                                        math_row(
                                            _var("ε", "sm"),
                                            operator("−"),
                                            _var("ε", "cm"),
                                        )
                                    ),
                                ),
                            ),
                            substitution_equation=_eq(
                                _var("w", "k"),
                                _product(
                                    _num(row.design.crack.max_crack_spacing_mm),
                                    _num(row.design.crack.strain_difference, 7),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Crack-width check",
                            expression="wk <= wlim",
                            substitution=(
                                f"{_f(row.design.crack.crack_width_mm)} <= "
                                f"{_f(preferences.eurocode.crack_limit_mm)} mm"
                            ),
                            result=f"{_f(row.design.crack.utilization)} utilization",
                            reference="EN 1992 serviceability crack control",
                            status="PASS" if row.design.crack.utilization <= 1.0 + 1e-9 else "CHECK",
                            equation=math_row(_var("w", "k"), operator("≤"), _var("w", "lim")),
                            substitution_equation=math_row(
                                _num(row.design.crack.crack_width_mm),
                                operator("≤"),
                                _num(preferences.eurocode.crack_limit_mm),
                            ),
                        ),
                        CalculationStep(
                            label="Effective concrete modulus for deflection",
                            expression="Ec,eff = Ecm / (1 + phi)",
                            substitution=(
                                f"{_f(row.design.deflection.effective_concrete_modulus_mpa)} MPa "
                                "(engine result after creep adjustment)"
                            ),
                            result=f"{_f(row.design.deflection.effective_concrete_modulus_mpa)} MPa",
                            reference="EC2 serviceability effective modulus",
                            equation=_eq(
                                _var("E", "c,eff"),
                                fraction(
                                    _var("E", "cm"),
                                    parenthesized(_sum(number("1"), identifier("φ"))),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="EC2 tension-stiffening interpolation",
                            expression="delta = zeta delta_II + (1-zeta) delta_I",
                            substitution=(
                                f"{_f(row.design.deflection.zeta)} x "
                                f"{_f(row.design.deflection.fully_cracked_deflection_mm)} + "
                                f"(1-{_f(row.design.deflection.zeta)}) x "
                                f"{_f(row.design.deflection.uncracked_deflection_mm)}"
                            ),
                            result=f"{_f(row.design.deflection.interpolated_deflection_mm)} mm",
                            reference="EN 1992 serviceability interpolation between states I and II",
                            equation=_eq(
                                identifier("δ"),
                                _sum(
                                    _product(identifier("ζ"), _var("δ", "II")),
                                    _product(
                                        parenthesized(
                                            math_row(number("1"), operator("−"), identifier("ζ"))
                                        ),
                                        _var("δ", "I"),
                                    ),
                                ),
                            ),
                            substitution_equation=_eq(
                                identifier("δ"),
                                _sum(
                                    _product(
                                        _num(row.design.deflection.zeta),
                                        _num(row.design.deflection.fully_cracked_deflection_mm),
                                    ),
                                    _product(
                                        parenthesized(
                                            math_row(
                                                number("1"),
                                                operator("−"),
                                                _num(row.design.deflection.zeta),
                                            )
                                        ),
                                        _num(row.design.deflection.uncracked_deflection_mm),
                                    ),
                                ),
                            ),
                        ),
                        CalculationStep(
                            label="Deflection check",
                            expression="delta <= L / limit ratio",
                            substitution=(
                                f"{_f(row.design.deflection.interpolated_deflection_mm)} <= "
                                f"{_f(deflection_limit_mm)} mm"
                            ),
                            result=f"{_f(row.design.deflection.utilization)} utilization",
                            reference="Project serviceability deflection criterion",
                            status="PASS" if row.design.deflection.utilization <= 1.0 + 1e-9 else "CHECK",
                            equation=math_row(
                                identifier("δ"),
                                operator("≤"),
                                fraction(identifier("L"), identifier("n")),
                            ),
                            substitution_equation=math_row(
                                _num(row.design.deflection.interpolated_deflection_mm),
                                operator("≤"),
                                fraction(
                                    _num(span_m * 1000.0, 0),
                                    _num(preferences.eurocode.deflection_limit_span_ratio, 0),
                                ),
                            ),
                        ),
                    ),
                )
            )
            if row.construction_stage_checks:
                stage_steps = tuple(
                    CalculationStep(
                        label=f"{check.stage.value} construction-stage check",
                        expression="max(MEd/MRd, VEd/VRd) <= 1.0",
                        substitution=(
                            f"max({_f(check.flexural_utilization)}, "
                            f"{_f(check.shear_utilization)})"
                        ),
                        result=f"{_f(max(check.flexural_utilization, check.shear_utilization))}",
                        reference="Construction-stage section active at time of loading",
                        status="PASS" if check.passes else "CHECK",
                        equation=math_row(
                            text("max"),
                            operator("("),
                            fraction(_var("M", "Ed"), _var("M", "Rd")),
                            operator(","),
                            fraction(_var("V", "Ed"), _var("V", "Rd")),
                            operator(")"),
                            operator("≤"),
                            number("1.0"),
                        ),
                        substitution_equation=math_row(
                            text("max"),
                            operator("("),
                            _num(check.flexural_utilization),
                            operator(","),
                            _num(check.shear_utilization),
                            operator(")"),
                            operator("≤"),
                            number("1.0"),
                        ),
                    )
                    for check in row.construction_stage_checks
                )
                blocks.append(
                    CalculationBlock(
                        title=f"Girder {row.girder_index} - construction-stage resistance",
                        scope="Earlier permanent loads are checked against the section stiffness/resistance active when applied.",
                        steps=stage_steps,
                    )
                )

    if local_deck_design is not None:
        deck = local_deck_design
        blocks.append(
            CalculationBlock(
                title="Local deck/slab design",
                scope="Transverse strip flexure and one-way shear from permanent, LM2 and barrier-related local actions.",
                steps=(
                    CalculationStep(
                        label="Bottom transverse reinforcement",
                        expression="As,prov >= max(As,req, As,min)",
                        substitution=(
                            f"max({_f(deck.bottom_transverse.required_area_mm2_per_m, 0)}, "
                            f"{_f(deck.bottom_transverse.minimum_area_mm2_per_m, 0)})"
                        ),
                        result=(
                            f"{deck.bottom_transverse.arrangement.label}; "
                            f"{_f(deck.bottom_transverse.arrangement.provided_area_mm2_per_m, 0)} mm2/m"
                        ),
                        reference="EN 1992 slab flexure/minimum reinforcement",
                        status="PASS" if deck.bottom_transverse.passes else "CHECK",
                        equation=math_row(
                            _var("A", "s,prov"),
                            operator("≥"),
                            text("max"),
                            operator("("),
                            _var("A", "s,req"),
                            operator(","),
                            _var("A", "s,min"),
                            operator(")"),
                        ),
                        substitution_equation=math_row(
                            _num(deck.bottom_transverse.arrangement.provided_area_mm2_per_m, 0),
                            operator("≥"),
                            text("max"),
                            operator("("),
                            _num(deck.bottom_transverse.required_area_mm2_per_m, 0),
                            operator(","),
                            _num(deck.bottom_transverse.minimum_area_mm2_per_m, 0),
                            operator(")"),
                        ),
                    ),
                    CalculationStep(
                        label="Top transverse reinforcement",
                        expression="As,prov >= max(As,req, As,min)",
                        substitution=(
                            f"max({_f(deck.top_transverse.required_area_mm2_per_m, 0)}, "
                            f"{_f(deck.top_transverse.minimum_area_mm2_per_m, 0)})"
                        ),
                        result=(
                            f"{deck.top_transverse.arrangement.label}; "
                            f"{_f(deck.top_transverse.arrangement.provided_area_mm2_per_m, 0)} mm2/m"
                        ),
                        reference="EN 1992 slab flexure/minimum reinforcement",
                        status="PASS" if deck.top_transverse.passes else "CHECK",
                        equation=math_row(
                            _var("A", "s,prov"),
                            operator("≥"),
                            text("max"),
                            operator("("),
                            _var("A", "s,req"),
                            operator(","),
                            _var("A", "s,min"),
                            operator(")"),
                        ),
                        substitution_equation=math_row(
                            _num(deck.top_transverse.arrangement.provided_area_mm2_per_m, 0),
                            operator("≥"),
                            text("max"),
                            operator("("),
                            _num(deck.top_transverse.required_area_mm2_per_m, 0),
                            operator(","),
                            _num(deck.top_transverse.minimum_area_mm2_per_m, 0),
                            operator(")"),
                        ),
                    ),
                    CalculationStep(
                        label="One-way slab shear",
                        expression="utilization = VEd / VRdc",
                        substitution=(
                            f"{_f(deck.one_way_shear.design_shear_kn_per_m)} / "
                            f"{_f(deck.one_way_shear.concrete_resistance_kn_per_m)}"
                        ),
                        result=f"{_f(deck.one_way_shear.utilization)}",
                        reference="EN 1992 concrete shear resistance",
                        status="PASS" if deck.one_way_shear.passes else "CHECK",
                        equation=_eq(
                            _var("η", "V"),
                            fraction(_var("V", "Ed"), _var("V", "Rd,c")),
                        ),
                        substitution_equation=_eq(
                            _var("η", "V"),
                            fraction(
                                _num(deck.one_way_shear.design_shear_kn_per_m),
                                _num(deck.one_way_shear.concrete_resistance_kn_per_m),
                            ),
                        ),
                    ),
                ),
            )
        )

    if fatigue is not None:
        steps: list[CalculationStep] = []
        for row in fatigue.girders:
            steps.append(
                CalculationStep(
                    label=f"Girder {row.girder_index} longitudinal reinforcement fatigue",
                    expression="fatigue utilization from FLM3 stress range / detail resistance",
                    substitution=f"Delta sigma_s = {_f(row.reference_steel_stress_range_mpa)} MPa",
                    result=f"{_f(row.fatigue.reinforcement.utilization)}",
                    reference="EN 1991-2 FLM3 and EN 1992 fatigue resistance",
                    status="PASS" if row.fatigue.reinforcement.passes else "CHECK",
                    equation=_eq(
                        math_row(identifier("Δ"), _var("σ", "s")),
                        _num(row.reference_steel_stress_range_mpa),
                    ),
                )
            )
        if steps:
            blocks.append(
                CalculationBlock(
                    title="FLM3 fatigue checks",
                    scope="Native moving FLM3 response connected to the selected reinforcement cage.",
                    steps=tuple(steps),
                )
            )

    return CalculationTrace(project_name=project.name, blocks=tuple(blocks))
