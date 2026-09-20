from __future__ import annotations

from html import escape
from pathlib import Path

from rc_bridge.analysis.physical_sections import (
    composite_section_description,
    girder_tributary_slab_widths_m,
)
from rc_bridge.application.calculation_trace import CalculationTrace
from rc_bridge.application.dashboard import build_application_dashboard
from rc_bridge.application.design_checks import ApplicationDesignInterpretationSuite
from rc_bridge.application.extended_actions import ExtendedActionSuite
from rc_bridge.application.fatigue import FatigueApplicationResult
from rc_bridge.application.load_cases import (
    application_combination_summary,
    eurocode_variable_action_scope,
    permanent_load_audit,
)
from rc_bridge.application.local_deck import LocalDeckDesignResult
from rc_bridge.application.math_notation import MathFormulaFlowable, mathml
from rc_bridge.application.preferences import ApplicationPreferences
from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult


def _number(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def calculation_trace_html(trace: CalculationTrace | None) -> str:
    if trace is None or not trace.blocks:
        return ""
    blocks: list[str] = []
    for block in trace.blocks:
        rows = []
        for step in block.steps:
            status = (
                f"<div><strong>{escape(step.status)}</strong></div>"
                if step.status
                else ""
            )
            equation_html = (
                mathml(step.equation)
                if step.equation is not None
                else f"<div class=\"formula-fallback\">{escape(step.expression)}</div>"
            )
            substitution_html = (
                mathml(step.substitution_equation)
                if step.substitution_equation is not None
                else f"<div class=\"formula-fallback\">{escape(step.substitution)}</div>"
            )
            rows.append(
                "<tr>"
                f"<td class=\"left ref\">{escape(step.reference)}</td>"
                "<td class=\"left calc\">"
                f"<strong class=\"calc-label\">{escape(step.label)}</strong>"
                "<div class=\"equation-caption\">Equation</div>"
                f"<div class=\"formula\">{equation_html}</div>"
                "<div class=\"equation-caption\">Substitution</div>"
                f"<div class=\"substitution\">{substitution_html}</div>"
                "</td>"
                f"<td class=\"left result\"><strong>{escape(step.result)}</strong>{status}</td>"
                "</tr>"
            )
        blocks.append(
            f"<h3>{escape(block.title)}</h3>"
            f"<p class=\"small\">{escape(block.scope)}</p>"
            "<table class=\"calculation-sheet\"><thead><tr>"
            "<th class=\"left\">Reference</th>"
            "<th class=\"left\">Calculation / substitution</th>"
            "<th class=\"left\">Result</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    return (
        "<h2>Step-by-step calculation sheets</h2>"
        "<p class=\"note\">The following sheets expose the calculation path used by "
        "the deterministic engine: input/effect, equation, numerical substitution, "
        "result and design reference. Summary tables later in the report do not "
        "replace these calculations.</p>"
        + "".join(blocks)
    )


def application_html_report(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
    *,
    preferences: ApplicationPreferences | None = None,
    extended_actions: ExtendedActionSuite | None = None,
    local_deck_design: LocalDeckDesignResult | None = None,
    design_interpretation: ApplicationDesignInterpretationSuite | None = None,
    fatigue: FatigueApplicationResult | None = None,
    calculation_trace: CalculationTrace | None = None,
) -> str:
    """Render the desktop calculation/reporting view without claiming validation."""

    prefs = preferences or ApplicationPreferences()
    geometry = project.geometry
    profile = geometry.girder_profile
    profile_name = "not defined" if profile is None else profile.section_type.value
    composite = None
    if profile is not None and geometry.composite_flange_depth_m > 0.0:
        composite = composite_section_description(
            geometry,
            slab_width_m=max(girder_tributary_slab_widths_m(geometry)),
            slab_width_basis="representative interior tributary slab width",
        )
    dashboard = build_application_dashboard(
        project,
        has_native_lm1_analysis=True,
        has_extended_actions=extended_actions is not None,
        has_integrated_design=design_interpretation is not None,
        has_local_deck_design=local_deck_design is not None,
        has_fatigue=fatigue is not None,
        design_blocker_count=(
            0
            if design_interpretation is None
            else len(design_interpretation.coverage_blockers)
        ),
    )

    permanent_audit = permanent_load_audit(project)
    try:
        combination_rows_data = application_combination_summary(
            project,
            result,
            uls_factors=prefs.eurocode.uls_factors,
            sls_factors=prefs.eurocode.sls_factors,
        )
        combination_scope_note = (
            "Simple-span magnitude interpretation using characteristic Gk and "
            "native LM1 Qk. Production design remains benchmark-gated."
        )
    except ValueError as exc:
        combination_rows_data = ()
        combination_scope_note = str(exc)

    rows = []
    for girder in result.girders:
        rows.append(
            "<tr>"
            f"<td>{girder.girder_index}</td>"
            f"<td>{_number(girder.y_m)}</td>"
            f"<td>{_number(girder.moment_knm.value)}</td>"
            f"<td>{girder.moment_knm.case_id}</td>"
            f"<td>{_number(girder.shear_kn.value)}</td>"
            f"<td>{girder.shear_kn.case_id}</td>"
            f"<td>{_number(girder.torsion_knm.value)}</td>"
            f"<td>{girder.torsion_knm.case_id}</td>"
            "</tr>"
        )

    deflection_rows = []
    for item in result.deflections:
        deflection_rows.append(
            "<tr>"
            f"<td>{item.girder_index}</td>"
            f"<td>{_number(item.value_mm)}</td>"
            f"<td>{_number(item.position_m)}</td>"
            f"<td>{item.case_id}</td>"
            "</tr>"
        )
    deflection_section = ""
    if deflection_rows:
        deflection_section = (
            "<h2>Native LM1 traffic deflection trace</h2>"
            "<table><thead><tr><th>Girder</th><th>|DZ| (mm)</th>"
            "<th>x (m)</th><th>Case</th></tr></thead><tbody>"
            + "".join(deflection_rows)
            + "</tbody></table>"
        )

    permanent_rows = "".join(
        "<tr>"
        f"<td>{row.girder_index}</td>"
        f"<td>{_number(row.girder_self_weight_kn_m)}</td>"
        f"<td>{_number(row.false_slab_kn_m)}</td>"
        f"<td>{_number(row.in_situ_slab_kn_m)}</td>"
        f"<td>{_number(row.surfacing_kn_m)}</td>"
        f"<td>{_number(row.barriers_kn_m)}</td>"
        f"<td>{_number(row.services_kn_m)}</td>"
        f"<td>{_number(row.other_kn_m)}</td>"
        f"<td>{_number(row.total_equivalent_kn_m)}</td>"
        "</tr>"
        for row in permanent_audit
    )
    variable_action_rows = "".join(
        "<tr>"
        f"<td class=\"left\">{escape(item.name)}</td>"
        f"<td>{escape(item.status)}</td>"
        f"<td class=\"left\">{escape(item.detail)}</td>"
        "</tr>"
        for item in eurocode_variable_action_scope()
    )
    combination_rows = "".join(
        "<tr>"
        f"<td>{row.girder_index}</td>"
        f"<td>{_number(row.permanent_characteristic.moment_knm)}</td>"
        f"<td>{_number(row.traffic_characteristic.moment_knm)}</td>"
        f"<td>{_number(row.uls.moment_knm)}</td>"
        f"<td>{_number(row.permanent_characteristic.shear_kn)}</td>"
        f"<td>{_number(row.traffic_characteristic.shear_kn)}</td>"
        f"<td>{_number(row.uls.shear_kn)}</td>"
        f"<td>{_number(row.sls_characteristic.moment_knm)}</td>"
        f"<td>{_number(row.sls_frequent.moment_knm)}</td>"
        f"<td>{_number(row.sls_quasi_permanent.moment_knm)}</td>"
        "</tr>"
        for row in combination_rows_data
    )

    additional_action_html = ""
    if extended_actions is not None:
        action_rows: list[str] = []
        if extended_actions.wind is not None:
            wind = extended_actions.wind
            action_rows.append(
                "<tr><td class=\"left\">Wind</td>"
                "<td>Static transverse resultant</td>"
                f"<td>{_number(wind.transverse_characteristic_force_kn)} kN</td>"
                f"<td class=\"left\">{escape(wind.status)}</td></tr>"
            )
            action_rows.append(
                "<tr><td class=\"left\">Wind</td>"
                "<td>Effective pressure / speed</td>"
                f"<td>{_number(wind.effective_pressure_kn_m2)} kN/m² / "
                f"{_number(wind.basic_velocity_m_s)} m/s</td>"
                "<td class=\"left\">"
                + (
                    "Project wind input complete."
                    if wind.input_complete
                    else "Project/basic wind speed remains an explicit input."
                )
                + "</td></tr>"
            )
        if extended_actions.braking is not None:
            braking = extended_actions.braking
            action_rows.append(
                "<tr><td class=\"left\">Braking</td>"
                "<td>Characteristic longitudinal force</td>"
                f"<td>{_number(braking.characteristic_force_kn)} kN</td>"
                f"<td class=\"left\">{escape(braking.status)}</td></tr>"
            )
        if extended_actions.thermal is not None:
            thermal = extended_actions.thermal
            action_rows.append(
                "<tr><td class=\"left\">Thermal</td>"
                "<td>Free movement + / -</td>"
                f"<td>{_number(thermal.expansion_movement_mm)} / "
                f"{_number(thermal.contraction_movement_mm)} mm</td>"
                f"<td class=\"left\">{escape(thermal.status)}</td></tr>"
            )
        additional_action_html = (
            "<h2>Additional actions</h2>"
            "<table><thead><tr><th class=\"left\">Action</th>"
            "<th>Result</th><th>Value</th><th class=\"left\">Boundary</th>"
            "</tr></thead><tbody>"
            + "".join(action_rows)
            + "</tbody></table>"
            if action_rows
            else ""
        )

    local_deck_html = ""
    if local_deck_design is not None:
        deck = local_deck_design
        local_deck_html = (
            "<h2>Native local deck/slab design</h2>"
            "<table><thead><tr><th>Check</th><th>Demand / provision</th>"
            "<th>Utilization</th></tr></thead><tbody>"
            "<tr><td>ULS transverse moments</td>"
            f"<td>+{_number(deck.uls_positive_moment_knm_per_m)} / "
            f"-{_number(deck.uls_negative_moment_knm_per_m)} kNm/m</td>"
            "<td>-</td></tr>"
            "<tr><td>Bottom transverse steel</td>"
            f"<td>{escape(deck.bottom_transverse.arrangement.label)}; "
            f"{_number(deck.bottom_transverse.arrangement.provided_area_mm2_per_m, 0)} "
            "mm²/m</td>"
            f"<td>{_number(deck.bottom_transverse.utilization)}</td></tr>"
            "<tr><td>Top transverse steel</td>"
            f"<td>{escape(deck.top_transverse.arrangement.label)}; "
            f"{_number(deck.top_transverse.arrangement.provided_area_mm2_per_m, 0)} "
            "mm²/m</td>"
            f"<td>{_number(deck.top_transverse.utilization)}</td></tr>"
            "<tr><td>One-way strip shear</td>"
            f"<td>VEd={_number(deck.one_way_shear.design_shear_kn_per_m)} kN/m; "
            f"VRdc={_number(deck.one_way_shear.concrete_resistance_kn_per_m)} kN/m</td>"
            f"<td>{_number(deck.one_way_shear.utilization)}</td></tr>"
            "</tbody></table>"
            f"<p class=\"note\">{escape(deck.status)}</p>"
        )

    fatigue_html = ""
    if fatigue is not None:
        fatigue_rows = "".join(
            "<tr>"
            f"<td>{row.girder_index}</td>"
            f"<td>{_number(row.reference_steel_stress_range_mpa)}</td>"
            f"<td>{_number(row.fatigue.reinforcement.utilization)}</td>"
            f"<td>{_number(row.fatigue.concrete.utilization) if row.fatigue.concrete is not None else '-'}</td>"
            f"<td>{_number(row.shear_links.fatigue.utilization) if row.shear_links is not None else '-'}</td>"
            "</tr>"
            for row in fatigue.girders
        )
        fatigue_blockers = (
            "<p class=\"warn\"><strong>Fatigue inputs required:</strong> "
            + escape("; ".join(fatigue.blockers))
            + "</p>"
            if fatigue.blockers
            else ""
        )
        fatigue_html = (
            "<h2>Native FLM3 fatigue</h2>"
            f"<p class=\"note\">{escape(fatigue.status)}</p>"
            f"<p>Evaluated FLM3 cases: {len(fatigue.search.cases)}</p>"
            + (
                "<table><thead><tr><th>Girder</th><th>Δσs (MPa)</th>"
                "<th>Steel util.</th><th>Concrete util.</th><th>Link util.</th>"
                "</tr></thead><tbody>" + fatigue_rows + "</tbody></table>"
                if fatigue_rows
                else ""
            )
            + fatigue_blockers
        )

    calculation_trace_section = calculation_trace_html(calculation_trace)

    integrated_design_html = ""
    if design_interpretation is not None:
        design_rows = "".join(
            "<tr>"
            f"<td>{row.girder_index}</td>"
            f"<td>{_number(row.design.uls_design.design_effects.moment_knm)}</td>"
            f"<td>{escape(row.governing_uls_moment_situation)}</td>"
            f"<td>{_number(row.design.uls_design.flexure.required_steel_area_mm2, 0)}</td>"
            f"<td>{row.selected_bars.bar_count}-Y{_number(row.selected_bars.bar_diameter_mm, 0)}</td>"
            f"<td>{_number(row.design.uls_design.flexure.utilization)}</td>"
            f"<td>{_number(abs(row.design.uls_design.design_effects.shear_kn))}</td>"
            f"<td>{escape(row.governing_uls_shear_situation)}</td>"
            f"<td>{_number(row.design.shear_utilization)}</td>"
            f"<td>{_number(row.design.crack.crack_width_mm)}</td>"
            f"<td>{_number(row.design.deflection.interpolated_deflection_mm)}</td>"
            f"<td>{'PASS' if row.passes_current_checks else 'CHECK'}</td>"
            "</tr>"
            for row in design_interpretation.girders
        )
        boundary_rows = []
        combo = design_interpretation.action_combinations
        if combo is not None and combo.bearing is not None:
            bearing = combo.bearing
            boundary_rows.append(
                "<tr><td class=\"left\">Bearing/restraint</td>"
                f"<td>{_number(bearing.persistent_uls_total_longitudinal_kn)} kN total; "
                f"{_number(bearing.persistent_uls_per_bearing_kn)} kN/bearing; "
                f"wind transverse {_number(bearing.persistent_uls_total_transverse_kn)} kN "
                f"({_number(bearing.persistent_uls_transverse_per_bearing_kn)} kN/bearing); "
                f"movement {_number(bearing.required_movement_mm)} mm</td>"
                f"<td class=\"left\">{escape(bearing.status)}</td></tr>"
            )
        if combo is not None and combo.barrier is not None:
            barrier = combo.barrier
            boundary_rows.append(
                "<tr><td class=\"left\">Safety-barrier accidental</td>"
                f"<td>{_number(barrier.transverse_accidental_demand_kn)} kN; "
                f"{_number(barrier.base_moment_accidental_demand_knm)} kNm</td>"
                f"<td class=\"left\">{escape(barrier.status)}</td></tr>"
            )
        blockers = (
            "<p class=\"warn\"><strong>Design blockers:</strong> "
            + escape("; ".join(design_interpretation.coverage_blockers))
            + "</p>"
            if design_interpretation.coverage_blockers
            else "<p class=\"note\">No unresolved coverage/input blockers remain in this design run.</p>"
        )
        integrated_design_html = (
            "<h2>Integrated action-to-design results</h2>"
            "<table><thead><tr>"
            "<th>Girder</th><th>MEd</th><th class=\"left\">M situation</th>"
            "<th>As,req</th><th>Selected bars</th><th>M util.</th>"
            "<th>VEd</th><th class=\"left\">V situation</th><th>V util.</th>"
            "<th>wk</th><th>Defl.</th><th>Status</th>"
            "</tr></thead><tbody>" + design_rows + "</tbody></table>"
            + (
                "<table><thead><tr><th class=\"left\">Local/support path</th>"
                "<th>Demand</th><th class=\"left\">Boundary</th></tr></thead><tbody>"
                + "".join(boundary_rows)
                + "</tbody></table>"
                if boundary_rows
                else ""
            )
            + blockers
        )

    capability_rows = "".join(
        "<tr>"
        f"<td>{escape(item.name)}</td>"
        f"<td>{escape(item.state.value.replace('_', ' '))}</td>"
        f"<td class=\"left\">{escape(item.detail)}</td>"
        "</tr>"
        for item in dashboard.capabilities
    )

    spans = ", ".join(_number(value) for value in geometry.span_lengths_m)
    project_name = escape(project.name)
    ec = prefs.eurocode
    analysis = prefs.analysis
    composite_html = ""
    if composite is not None:
        false_slab_text = (
            "weight-only"
            if composite.false_slab_weight_only
            else "included in composite stiffness"
        )
        composite_html = (
            f"<div>Final composite form</div>"
            f"<div>{escape(composite.final_section_form)}-section</div>"
            f"<div>Representative participating flange (m)</div>"
            f"<div>{_number(composite.flange_width_m)} × "
            f"{_number(composite.participating_flange_depth_m)}</div>"
            f"<div>Overall physical depth (m)</div>"
            f"<div>{_number(composite.overall_depth_m)}</div>"
            f"<div>Precast false slab in stiffness</div>"
            f"<div>{escape(false_slab_text)}</div>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{project_name} - RC Bridge Analysis Report</title>
<style>
:root {{
  --ink: #182635;
  --navy: #17324d;
  --navy-2: #244b6b;
  --line: #aebdca;
  --paper: #ffffff;
  --wash: #f4f7f9;
  --result: #f8fbf6;
  --accent: #9a7b35;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: "Segoe UI", Arial, Helvetica, sans-serif;
  max-width: 1180px;
  margin: 28px auto;
  padding: 34px 42px 48px;
  color: var(--ink);
  background: var(--paper);
  box-shadow: 0 10px 30px rgba(18, 41, 61, 0.10);
  line-height: 1.38;
}}
h1 {{
  color: var(--navy);
  margin: 0 0 4px;
  padding-bottom: 10px;
  border-bottom: 3px solid var(--navy);
  letter-spacing: 0.01em;
}}
h2 {{
  color: var(--navy);
  margin-top: 30px;
  padding: 7px 10px;
  border-left: 5px solid var(--navy-2);
  background: #f0f4f7;
}}
h3 {{ color: var(--navy-2); margin: 24px 0 4px; }}
.meta {{
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 6px 18px;
  border: 1px solid var(--line);
  padding: 12px 14px;
  background: #fbfcfd;
}}
.meta > div:nth-child(odd) {{ font-weight: 600; color: #3a5268; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0 24px; }}
th, td {{ border: 1px solid var(--line); padding: 7px 9px; text-align: right; }}
th:first-child, td:first-child {{ text-align: center; }}
th {{
  background: var(--navy);
  color: white;
  font-weight: 600;
}}
tbody tr:nth-child(even):not(.calculation-sheet tr) {{ background: #fafcfd; }}
.left {{ text-align: left; }}
.note {{
  border-left: 4px solid #6e879c;
  padding: 10px 14px;
  background: var(--wash);
}}
.warn {{
  border-left: 4px solid #b06f21;
  padding: 10px 14px;
  background: #fff8ec;
}}
.small {{ font-size: 0.9rem; color: #52606d; }}
.calculation-sheet {{
  table-layout: fixed;
  border: 1.4px solid #70879a;
  box-shadow: 0 1px 0 rgba(0,0,0,.03);
}}
.calculation-sheet td {{ vertical-align: top; }}
.calculation-sheet .ref {{
  width: 18%;
  background: #f3f5f7;
  color: #455b6d;
  font-size: 0.86rem;
}}
.calculation-sheet .calc {{ width: 62%; text-align: left; padding: 10px 14px; }}
.calculation-sheet .result {{
  width: 20%;
  background: var(--result);
  text-align: left;
  font-size: 0.93rem;
}}
.calc-label {{ color: var(--navy); font-size: 0.98rem; }}
.equation-caption {{
  margin-top: 7px;
  color: #748493;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
.formula, .substitution {{
  margin: 2px 0 4px;
  overflow-x: auto;
}}
.substitution {{ color: #334e68; }}
.formula-fallback {{
  font-family: "Cambria Math", "STIX Two Math", "Times New Roman", serif;
  font-size: 1.03rem;
}}
math.engineering-math {{
  font-family: "Cambria Math", "STIX Two Math", "STIXGeneral", "Times New Roman", serif;
  font-size: 1.08rem;
  margin: 2px 0;
}}
math.engineering-math[display="block"] {{ display: block; text-align: left; }}
@media print {{
  body {{
    max-width: none;
    margin: 0;
    padding: 10mm;
    box-shadow: none;
  }}
  h2 {{ break-after: avoid; }}
  h3 {{ break-after: avoid; }}
  .screen-only {{ display: none; }}
  .calculation-sheet tr {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<h1>{project_name}</h1>
<p class="small">Deterministic RC bridge analysis and application calculation report</p>

<h2>Project definition</h2>
<div class="meta">
<div>Design code</div><div>{escape(project.design_code.value)}</div>
<div>Support system</div><div>{escape(geometry.support_system.value)}</div>
<div>Span lengths (m)</div><div>{escape(spans)}</div>
<div>Deck width (m)</div><div>{_number(geometry.deck_width_m)}</div>
<div>Carriageway width (m)</div><div>{_number(geometry.carriageway_width_m)}</div>
<div>Carriageway offset (m)</div><div>{_number(geometry.carriageway_offset_m)}</div>
<div>Girder count</div><div>{int(geometry.girder_count)}</div>
<div>Girder spacing (m)</div><div>{_number(geometry.girder_spacing_m)}</div>
<div>Precast physical section</div><div>{escape(profile_name)}</div>
{composite_html}
<div>Concrete fck (MPa)</div><div>{_number(project.materials.fck_mpa, 1)}</div>
<div>Reinforcement fyk (MPa)</div><div>{_number(project.materials.fyk_mpa, 1)}</div>
</div>

<h2>Application design basis</h2>
<div class="meta">
<div>Display units</div><div>{escape(prefs.units.value)}</div>
<div>&gamma;G unfavourable</div><div>{_number(ec.gamma_g_unfavourable, 3)}</div>
<div>&gamma;G favourable</div><div>{_number(ec.gamma_g_favourable, 3)}</div>
<div>&gamma;Q traffic</div><div>{_number(ec.gamma_q_traffic, 3)}</div>
<div>&gamma;Q non-traffic</div><div>{_number(ec.gamma_q_nontraffic, 3)}</div>
<div>&psi;1 traffic</div><div>{_number(ec.psi1_traffic, 3)}</div>
<div>&psi;2 traffic</div><div>{_number(ec.psi2_traffic, 3)}</div>
<div>&psi;1 LM2</div><div>{_number(ec.psi1_lm2, 3)}</div>
<div>Thermal &psi;0 ULS / SLS</div><div>{_number(ec.psi0_thermal_uls, 3)} / {_number(ec.psi0_thermal_sls, 3)}</div>
<div>Thermal &psi;1 / &psi;2</div><div>{_number(ec.psi1_thermal, 3)} / {_number(ec.psi2_thermal, 3)}</div>
<div>Crack-width criterion (mm)</div><div>{_number(ec.crack_limit_mm, 3)}</div>
<div>Deflection criterion</div><div>L/{_number(ec.deflection_limit_span_ratio, 0)}</div>
<div>Native grid spacing (m)</div><div>{_number(analysis.grid_spacing_m)}</div>
<div>Traffic search step (m)</div><div>{_number(analysis.traffic_step_m)}</div>
</div>
<p class="note">
The native LM1 search below is a characteristic traffic analysis. The design-basis
ULS/SLS factors are persisted for design workflows and are not silently applied to
the characteristic traffic envelope itself.
</p>

<h2>Load cases and combinations</h2>
<p class="note">
Physical girder/deck self-weight is derived from the project geometry. Surfacing,
barriers and services are included only when defined in the project. The table
below reports equivalent full-length line loads for audit; non-uniform positioned
actions retain their actual extents in the deterministic permanent-load routines.
</p>
<table>
<thead><tr>
<th>Girder</th><th>Girder SW</th><th>False slab</th><th>In-situ slab</th>
<th>Surfacing</th><th>Barriers</th><th>Services</th><th>Other</th><th>Total Gk</th>
</tr></thead>
<tbody>{permanent_rows}</tbody>
</table>
<p class="small">All permanent-load audit values above are kN/m equivalent over the bridge length.</p>

<table>
<thead><tr><th class="left">Variable action</th><th>Status</th><th class="left">Current treatment</th></tr></thead>
<tbody>{variable_action_rows}</tbody>
</table>

<h3>EN 1990 combination interpretation</h3>
<p class="note">{escape(combination_scope_note)}</p>
{"<table><thead><tr><th>Girder</th><th>Gk M</th><th>LM1 Qk M</th><th>ULS M</th><th>Gk V</th><th>LM1 Qk V</th><th>ULS V</th><th>SLS char M</th><th>SLS freq M</th><th>SLS qp M</th></tr></thead><tbody>" + combination_rows + "</tbody></table>" if combination_rows else ""}

<h2>Native LM1 search</h2>
<div class="meta">
<div>Evaluated cases</div><div>{result.evaluated_case_count}</div>
<div>Search strategy</div><div>{escape(result.search_strategy)}</div>
<div>Longitudinal step (m)</div><div>{_number(result.longitudinal_step_m)}</div>
<div>UDL patterns</div><div>{result.udl_pattern_count}</div>
<div>Unique factorized grillage structures</div>
<div>{result.prepared_structure_count}</div>
<div>Reused factorization solves</div>
<div>{result.reused_factorization_solve_count}</div>
<div>Retained case models</div><div>{result.retained_case_count}</div>
<div>Exhaustive tandem combinations</div>
<div>{"yes" if result.tandem_combinations_exhaustive else "no"}</div>
</div>
<table>
<thead><tr>
<th>Girder</th><th>y (m)</th><th>|M| (kNm)</th><th>M case</th>
<th>|V| (kN)</th><th>V case</th><th>|T| (kNm)</th><th>T case</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
{deflection_section}
{calculation_trace_section}
{additional_action_html}
{local_deck_html}
{integrated_design_html}
{fatigue_html}

<h2>Design and verification readiness</h2>
<table>
<thead><tr><th>Capability</th><th>Status</th><th class="left">Engineering boundary</th></tr></thead>
<tbody>{capability_rows}</tbody>
</table>

<h2>Verification boundary</h2>
<p class="warn">
Independent structural validation for the deterministic Stage-5 solver profile now
includes genuine STAAD external evidence and an accepted source/model review. MIDAS
cross-verification is deferred to V2 and is not a deterministic-v1 release gate.
ANN/reliability/RBDO ground-truth generation remains locked until the current v1
verification manifest and outstanding project/code acceptance checks are complete.
</p>
</body>
</html>
"""


def native_lm1_html_report(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
) -> str:
    """Backward-compatible HTML report entry point."""

    return application_html_report(project, result)


def write_native_lm1_pdf_report(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
    path: str | Path,
    *,
    preferences: ApplicationPreferences | None = None,
    extended_actions: ExtendedActionSuite | None = None,
    local_deck_design: LocalDeckDesignResult | None = None,
    design_interpretation: ApplicationDesignInterpretationSuite | None = None,
    fatigue: FatigueApplicationResult | None = None,
    calculation_trace: CalculationTrace | None = None,
) -> Path:
    """Write a printable engineering calculation report using shared trace records."""

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF reporting requires the installed application reporting dependency."
        ) from exc

    destination = Path(path)
    if destination.suffix.lower() != ".pdf":
        raise ValueError("Application PDF report must use the .pdf extension.")
    destination.parent.mkdir(parents=True, exist_ok=True)

    prefs = preferences or ApplicationPreferences()
    dashboard = build_application_dashboard(
        project,
        has_native_lm1_analysis=True,
        has_extended_actions=extended_actions is not None,
        has_integrated_design=design_interpretation is not None,
        has_local_deck_design=local_deck_design is not None,
        has_fatigue=fatigue is not None,
        design_blocker_count=(
            0
            if design_interpretation is None
            else len(design_interpretation.coverage_blockers)
        ),
    )
    geometry = project.geometry
    composite = None
    if (
        geometry.girder_profile is not None
        and geometry.composite_flange_depth_m > 0.0
    ):
        composite = composite_section_description(
            geometry,
            slab_width_m=max(girder_tributary_slab_widths_m(geometry)),
            slab_width_basis="representative interior tributary slab width",
        )
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#17324d")
    navy_2 = colors.HexColor("#244b6b")
    line_colour = colors.HexColor("#9fb0bf")
    pale_blue = colors.HexColor("#eef3f7")
    pale_result = colors.HexColor("#f4f8f2")
    pale_reference = colors.HexColor("#f4f5f6")
    title_style = ParagraphStyle(
        "EngineeringTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=22,
        textColor=navy,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "EngineeringSubtitle",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#536b7d"),
        spaceAfter=5,
    )
    heading2 = ParagraphStyle(
        "EngineeringHeading2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=15,
        textColor=navy,
        backColor=pale_blue,
        borderColor=navy_2,
        borderWidth=0,
        borderPadding=(5, 7, 5, 8),
        leftIndent=0,
        spaceBefore=8,
        spaceAfter=6,
    )
    heading3 = ParagraphStyle(
        "EngineeringHeading3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=navy_2,
        spaceBefore=7,
        spaceAfter=3,
    )
    small = ParagraphStyle(
        "Small",
        parent=styles["BodyText"],
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
    )
    body = styles["BodyText"]
    body.fontSize = 9
    body.leading = 11
    body.textColor = colors.HexColor("#243746")
    reference_style = ParagraphStyle(
        "CalculationReference",
        parent=small,
        fontSize=6.8,
        leading=8.2,
        textColor=colors.HexColor("#526778"),
    )
    calc_label_style = ParagraphStyle(
        "CalculationLabel",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=10,
        textColor=navy,
        spaceAfter=2,
    )
    equation_caption_style = ParagraphStyle(
        "EquationCaption",
        parent=small,
        fontName="Helvetica-Bold",
        fontSize=5.8,
        leading=6.8,
        textColor=colors.HexColor("#748493"),
        spaceBefore=2,
        spaceAfter=1,
    )
    result_style = ParagraphStyle(
        "CalculationResult",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8.2,
        leading=10,
        textColor=navy,
    )
    story = [
        Paragraph(escape(project.name), title_style),
        Paragraph("Deterministic RC bridge analysis and design calculation report", subtitle_style),
        Spacer(1, 4 * mm),
        Paragraph("Project definition", heading2),
    ]

    project_rows = [
        ["Design code", project.design_code.value],
        ["Support system", geometry.support_system.value],
        ["Spans (m)", ", ".join(_number(value) for value in geometry.span_lengths_m)],
        ["Deck / carriageway (m)", f"{_number(geometry.deck_width_m)} / {_number(geometry.carriageway_width_m)}"],
        ["Girders", f"{int(geometry.girder_count)} @ {_number(geometry.girder_spacing_m)} m"],
        [
            "Concrete / steel (MPa)",
            (
                f"{_number(project.materials.fck_mpa, 1)} / "
                f"{_number(project.materials.fyk_mpa, 1)}"
            ),
        ],
    ]
    if composite is not None:
        project_rows.extend(
            [
                ["Precast section", composite.precast_section_type],
                ["Final composite form", f"{composite.final_section_form}-section"],
                [
                    "Composite flange (m)",
                    (
                        f"{_number(composite.flange_width_m)} x "
                        f"{_number(composite.participating_flange_depth_m)}"
                    ),
                ],
                ["Overall physical depth (m)", _number(composite.overall_depth_m)],
            ]
        )
    project_table = Table(project_rows, colWidths=[55 * mm, 110 * mm])
    project_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([project_table, Spacer(1, 4 * mm)])

    ec = prefs.eurocode
    story.append(Paragraph("Application design basis", heading2))
    basis_rows = [
        ["Display units", prefs.units.value],
        ["ULS factors", f"gamma_G,unf={ec.gamma_g_unfavourable:g}; gamma_G,fav={ec.gamma_g_favourable:g}; gamma_Q,traffic={ec.gamma_q_traffic:g}; gamma_Q,other={ec.gamma_q_nontraffic:g}"],
        ["SLS traffic psi", f"psi1={ec.psi1_traffic:g}; psi2={ec.psi2_traffic:g}; psi1,LM2={ec.psi1_lm2:g}"],
        ["Thermal psi", f"psi0 ULS/SLS={ec.psi0_thermal_uls:g}/{ec.psi0_thermal_sls:g}; psi1={ec.psi1_thermal:g}; psi2={ec.psi2_thermal:g}"],
        ["Crack / deflection criteria", f"{ec.crack_limit_mm:g} mm; L/{ec.deflection_limit_span_ratio:g}"],
        ["Native search", f"grid {prefs.analysis.grid_spacing_m:g} m; traffic step {prefs.analysis.traffic_step_m:g} m"],
    ]
    basis_table = Table(basis_rows, colWidths=[55 * mm, 110 * mm])
    basis_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ]
        )
    )
    story.extend([basis_table, Spacer(1, 4 * mm)])

    if calculation_trace is not None and calculation_trace.blocks:
        story.extend(
            [
                PageBreak(),
                Paragraph("Step-by-step calculation sheets", heading2),
                Paragraph(
                    "Each calculation sheet shows the design reference, equation, "
                    "numerical substitution and result. The later summary tables are "
                    "retained for review but do not replace the worked calculation path.",
                    body,
                ),
                Spacer(1, 3 * mm),
            ]
        )
        for block in calculation_trace.blocks:
            story.append(Paragraph(escape(block.title), heading3))
            story.append(Paragraph(escape(block.scope), small))
            trace_rows = [["Reference", "Worked calculation", "Result / check"]]
            for step in block.steps:
                calculation_cell: list = [
                    Paragraph(escape(step.label), calc_label_style),
                    Paragraph("EQUATION", equation_caption_style),
                ]
                if step.equation is not None:
                    calculation_cell.append(
                        MathFormulaFlowable(step.equation, font_size=9.5)
                    )
                else:
                    calculation_cell.append(
                        Paragraph(escape(step.expression), small)
                    )

                calculation_cell.append(
                    Paragraph("NUMERICAL SUBSTITUTION", equation_caption_style)
                )
                if step.substitution_equation is not None:
                    calculation_cell.append(
                        MathFormulaFlowable(
                            step.substitution_equation,
                            font_size=9.0,
                        )
                    )
                else:
                    calculation_cell.append(
                        Paragraph(escape(step.substitution), small)
                    )

                result_cell: list = [
                    Paragraph(escape(step.result), result_style)
                ]
                if step.status:
                    status_colour = "#1f6b45" if step.status == "PASS" else "#9a5a16"
                    result_cell.append(
                        Paragraph(
                            f'<font color="{status_colour}"><b>{escape(step.status)}</b></font>',
                            small,
                        )
                    )

                trace_rows.append(
                    [
                        Paragraph(escape(step.reference), reference_style),
                        calculation_cell,
                        result_cell,
                    ]
                )
            trace_table = Table(
                trace_rows,
                colWidths=[35 * mm, 110 * mm, 35 * mm],
                repeatRows=1,
                hAlign="LEFT",
            )
            trace_table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.35, line_colour),
                        ("BACKGROUND", (0, 0), (-1, 0), navy),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                        ("BACKGROUND", (0, 1), (0, -1), pale_reference),
                        ("BACKGROUND", (-1, 1), (-1, -1), pale_result),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 1), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                    ]
                )
            )
            story.extend([trace_table, Spacer(1, 3 * mm)])
        story.append(PageBreak())

    story.append(Paragraph("Load cases and combinations", heading2))
    permanent_rows_pdf = [
        [
            "Girder",
            "Girder SW",
            "False slab",
            "In-situ",
            "Surfacing",
            "Barriers",
            "Services",
            "Other",
            "Total Gk",
        ]
    ]
    permanent_rows_pdf.extend(
        [
            str(row.girder_index),
            _number(row.girder_self_weight_kn_m),
            _number(row.false_slab_kn_m),
            _number(row.in_situ_slab_kn_m),
            _number(row.surfacing_kn_m),
            _number(row.barriers_kn_m),
            _number(row.services_kn_m),
            _number(row.other_kn_m),
            _number(row.total_equivalent_kn_m),
        ]
        for row in permanent_load_audit(project)
    )
    permanent_table = Table(permanent_rows_pdf, repeatRows=1)
    permanent_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.extend([permanent_table, Spacer(1, 3 * mm)])

    try:
        combination_pdf = application_combination_summary(
            project,
            result,
            uls_factors=prefs.eurocode.uls_factors,
            sls_factors=prefs.eurocode.sls_factors,
        )
    except ValueError as exc:
        story.extend(
            [
                Paragraph(
                    "Combination interpretation: " + escape(str(exc)),
                    small,
                ),
                Spacer(1, 3 * mm),
            ]
        )
    else:
        combo_rows_pdf = [
            [
                "Girder",
                "Gk M",
                "LM1 Qk M",
                "ULS M",
                "Gk V",
                "LM1 Qk V",
                "ULS V",
                "SLS char M",
                "SLS freq M",
                "SLS qp M",
            ]
        ]
        combo_rows_pdf.extend(
            [
                str(row.girder_index),
                _number(row.permanent_characteristic.moment_knm),
                _number(row.traffic_characteristic.moment_knm),
                _number(row.uls.moment_knm),
                _number(row.permanent_characteristic.shear_kn),
                _number(row.traffic_characteristic.shear_kn),
                _number(row.uls.shear_kn),
                _number(row.sls_characteristic.moment_knm),
                _number(row.sls_frequent.moment_knm),
                _number(row.sls_quasi_permanent.moment_knm),
            ]
            for row in combination_pdf
        )
        combo_table = Table(combo_rows_pdf, repeatRows=1)
        combo_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6.6),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.extend([combo_table, Spacer(1, 4 * mm)])

    story.append(Paragraph("Native LM1 search", heading2))
    search_rows = [
        ["Evaluated cases", str(result.evaluated_case_count)],
        ["Unique factorized structures", str(result.prepared_structure_count)],
        ["Reused factorization solves", str(result.reused_factorization_solve_count)],
        ["Retained case models", str(result.retained_case_count)],
        ["Search strategy", result.search_strategy],
    ]
    search_table = Table(search_rows, colWidths=[55 * mm, 110 * mm])
    search_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend([search_table, Spacer(1, 4 * mm)])

    story.append(Paragraph("Native LM1 governing effects", heading2))
    effect_rows = [["Girder", "y (m)", "|M| kNm", "M case", "|V| kN", "V case", "|T| kNm", "T case"]]
    effect_rows.extend(
        [
            str(item.girder_index),
            _number(item.y_m),
            _number(item.moment_knm.value),
            str(item.moment_knm.case_id),
            _number(item.shear_kn.value),
            str(item.shear_kn.case_id),
            _number(item.torsion_knm.value),
            str(item.torsion_knm.case_id),
        ]
        for item in result.girders
    )
    effects_table = Table(effect_rows, repeatRows=1)
    effects_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    story.extend([effects_table, Spacer(1, 4 * mm)])

    if result.deflections:
        story.append(Paragraph("Native LM1 traffic deflection trace", heading2))
        deflection_rows = [["Girder", "|DZ| (mm)", "x (m)", "Case"]]
        deflection_rows.extend(
            [
                str(item.girder_index),
                _number(item.value_mm),
                _number(item.position_m),
                str(item.case_id),
            ]
            for item in result.deflections
        )
        deflection_table = Table(deflection_rows, repeatRows=1)
        deflection_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ]
            )
        )
        story.extend([deflection_table, Spacer(1, 4 * mm)])

    if local_deck_design is not None:
        deck = local_deck_design
        story.append(Paragraph("Native local deck/slab design", heading2))
        deck_rows = [
            ["Check", "Demand / provision", "Util."],
            [
                "ULS transverse moments",
                (
                    f"+{_number(deck.uls_positive_moment_knm_per_m)} / "
                    f"-{_number(deck.uls_negative_moment_knm_per_m)} kNm/m"
                ),
                "-",
            ],
            [
                "Bottom transverse steel",
                (
                    f"{deck.bottom_transverse.arrangement.label}; "
                    f"{_number(deck.bottom_transverse.arrangement.provided_area_mm2_per_m, 0)} "
                    "mm2/m"
                ),
                _number(deck.bottom_transverse.utilization),
            ],
            [
                "Top transverse steel",
                (
                    f"{deck.top_transverse.arrangement.label}; "
                    f"{_number(deck.top_transverse.arrangement.provided_area_mm2_per_m, 0)} "
                    "mm2/m"
                ),
                _number(deck.top_transverse.utilization),
            ],
            [
                "One-way strip shear",
                (
                    f"VEd={_number(deck.one_way_shear.design_shear_kn_per_m)} kN/m; "
                    f"VRdc={_number(deck.one_way_shear.concrete_resistance_kn_per_m)} kN/m"
                ),
                _number(deck.one_way_shear.utilization),
            ],
        ]
        deck_table = Table(deck_rows, colWidths=[45 * mm, 105 * mm, 25 * mm])
        deck_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.extend(
            [
                deck_table,
                Paragraph(escape(deck.status), small),
                Spacer(1, 3 * mm),
            ]
        )

    if fatigue is not None:
        story.append(Paragraph("Native FLM3 fatigue", heading2))
        fatigue_rows_pdf = [
            ["Girder", "Delta sigma s", "Steel util.", "Concrete util.", "Link util."]
        ]
        fatigue_rows_pdf.extend(
            [
                str(row.girder_index),
                _number(row.reference_steel_stress_range_mpa),
                _number(row.fatigue.reinforcement.utilization),
                (
                    _number(row.fatigue.concrete.utilization)
                    if row.fatigue.concrete is not None
                    else "-"
                ),
                (
                    _number(row.shear_links.fatigue.utilization)
                    if row.shear_links is not None
                    else "-"
                ),
            ]
            for row in fatigue.girders
        )
        fatigue_table = Table(fatigue_rows_pdf, repeatRows=1)
        fatigue_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.0),
                ]
            )
        )
        story.extend([fatigue_table, Spacer(1, 2 * mm)])
        if fatigue.blockers:
            story.extend(
                [
                    Paragraph(
                        "<b>Fatigue inputs required:</b> "
                        + escape("; ".join(fatigue.blockers)),
                        small,
                    ),
                    Spacer(1, 3 * mm),
                ]
            )

    if design_interpretation is not None:
        story.append(Paragraph("Integrated action-to-design results", heading2))
        integrated_rows = [
            [
                "Girder",
                "MEd",
                "M situation",
                "As,req",
                "Selected bars",
                "M util.",
                "VEd",
                "V situation",
                "V util.",
                "wk",
                "Defl.",
                "Status",
            ]
        ]
        integrated_rows.extend(
            [
                str(row.girder_index),
                _number(row.design.uls_design.design_effects.moment_knm),
                Paragraph(escape(row.governing_uls_moment_situation), small),
                _number(row.design.uls_design.flexure.required_steel_area_mm2, 0),
                (
                    f"{row.selected_bars.bar_count}-Y"
                    f"{_number(row.selected_bars.bar_diameter_mm, 0)}"
                ),
                _number(row.design.uls_design.flexure.utilization),
                _number(abs(row.design.uls_design.design_effects.shear_kn)),
                Paragraph(escape(row.governing_uls_shear_situation), small),
                _number(row.design.shear_utilization),
                _number(row.design.crack.crack_width_mm),
                _number(row.design.deflection.interpolated_deflection_mm),
                "PASS" if row.passes_current_checks else "CHECK",
            ]
            for row in design_interpretation.girders
        )
        integrated_table = Table(integrated_rows, repeatRows=1)
        integrated_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6.0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.extend([integrated_table, Spacer(1, 3 * mm)])
        if design_interpretation.coverage_blockers:
            story.extend(
                [
                    Paragraph(
                        "<b>Design blockers:</b> "
                        + escape("; ".join(design_interpretation.coverage_blockers)),
                        small,
                    ),
                    Spacer(1, 3 * mm),
                ]
            )

    story.extend([PageBreak(), Paragraph("Design and verification readiness", heading2)])
    capability_rows = [["Capability", "Status", "Engineering boundary"]]
    capability_rows.extend(
        [
            Paragraph(escape(item.name), small),
            item.state.value.replace("_", " "),
            Paragraph(escape(item.detail), small),
        ]
        for item in dashboard.capabilities
    )
    capability_table = Table(capability_rows, colWidths=[50 * mm, 35 * mm, 95 * mm], repeatRows=1)
    capability_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.extend(
        [
            capability_table,
            Spacer(1, 5 * mm),
            Paragraph(
                "Verification boundary: independent structural validation for the deterministic "
                "Stage-5 solver profile includes genuine STAAD external evidence and an accepted "
                "source/model review. MIDAS cross-verification is deferred to V2 and is not a "
                "deterministic-v1 release gate. ANN/reliability/RBDO ground-truth generation remains "
                "locked until the current v1 verification manifest and outstanding project/code "
                "acceptance checks are complete.",
                body,
            ),
        ]
    )

    temporary = destination.with_suffix(".pdf.tmp")
    page_size = landscape(A4)
    page_width, page_height = page_size

    def draw_page_frame(canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(0.7)
        canvas.line(10 * mm, page_height - 9 * mm, page_width - 10 * mm, page_height - 9 * mm)
        canvas.setFont("Helvetica-Bold", 7.2)
        canvas.setFillColor(navy)
        canvas.drawString(10 * mm, page_height - 7 * mm, project.name[:80])
        canvas.setFont("Helvetica", 7.0)
        canvas.setFillColor(colors.HexColor("#5f7383"))
        canvas.drawRightString(
            page_width - 10 * mm,
            page_height - 7 * mm,
            "RC Bridge Analysis & Design Calculations",
        )
        canvas.setStrokeColor(line_colour)
        canvas.setLineWidth(0.35)
        canvas.line(10 * mm, 8 * mm, page_width - 10 * mm, 8 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#5f7383"))
        canvas.drawString(10 * mm, 5 * mm, "Deterministic calculation report")
        canvas.drawCentredString(
            page_width / 2.0,
            5 * mm,
            f"Page {document.page}",
        )
        canvas.drawRightString(
            page_width - 10 * mm,
            5 * mm,
            "Generated by RC-Bridge-Analysis-ANN",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(temporary),
        pagesize=page_size,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=14 * mm,
        bottomMargin=12 * mm,
        title=f"{project.name} - RC Bridge Analysis Report",
    )
    document.build(
        story,
        onFirstPage=draw_page_frame,
        onLaterPages=draw_page_frame,
    )
    temporary.replace(destination)
    return destination
