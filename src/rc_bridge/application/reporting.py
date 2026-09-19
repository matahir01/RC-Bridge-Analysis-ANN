from __future__ import annotations

from html import escape

from rc_bridge.core.models import ProjectInput
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult


def _number(value: float, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def native_lm1_html_report(
    project: ProjectInput,
    result: ProjectNativeLM1GrillageSearchResult,
) -> str:
    """Render a standalone deterministic-analysis report without claiming validation."""
    geometry = project.geometry
    profile = geometry.girder_profile
    profile_name = "not defined" if profile is None else profile.section_type.value
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

    spans = ", ".join(_number(value) for value in geometry.span_lengths_m)
    project_name = escape(project.name)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{project_name} - RC Bridge Analysis Report</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; margin: 32px; color: #1f2933; }}
h1, h2 {{ color: #102a43; }}
.meta {{ display: grid; grid-template-columns: 220px 1fr; gap: 6px 18px; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0 24px; }}
th, td {{ border: 1px solid #bcccdc; padding: 7px 9px; text-align: right; }}
th:first-child, td:first-child {{ text-align: center; }}
th {{ background: #eaf2f8; }}
.note {{ border-left: 4px solid #829ab1; padding: 10px 14px; background: #f5f7fa; }}
.small {{ font-size: 0.9rem; color: #52606d; }}
</style>
</head>
<body>
<h1>{project_name}</h1>
<p class="small">Deterministic RC bridge analysis - application report</p>
<h2>Project definition</h2>
<div class="meta">
<div>Design code</div><div>{escape(project.design_code.value)}</div>
<div>Support system</div><div>{escape(geometry.support_system.value)}</div>
<div>Span lengths (m)</div><div>{escape(spans)}</div>
<div>Deck width (m)</div><div>{_number(geometry.deck_width_m)}</div>
<div>Carriageway width (m)</div><div>{_number(geometry.carriageway_width_m)}</div>
<div>Girder count</div><div>{int(geometry.girder_count)}</div>
<div>Girder spacing (m)</div><div>{_number(geometry.girder_spacing_m)}</div>
<div>Physical section</div><div>{escape(profile_name)}</div>
<div>Concrete fck (MPa)</div><div>{_number(project.materials.fck_mpa, 1)}</div>
<div>Reinforcement fyk (MPa)</div><div>{_number(project.materials.fyk_mpa, 1)}</div>
</div>
<h2>Native LM1 search</h2>
<div class="meta">
<div>Evaluated cases</div><div>{result.evaluated_case_count}</div>
<div>Search strategy</div><div>{escape(result.search_strategy)}</div>
<div>Longitudinal step (m)</div><div>{_number(result.longitudinal_step_m)}</div>
<div>UDL patterns</div><div>{result.udl_pattern_count}</div>
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
<h2>Verification boundary</h2>
<p class="note">
These are native deterministic analysis results. Passing automated tests or producing
MIDAS/STAAD model files is not independent structural validation. Final acceptance
requires the application-generated governing models to be run in independent structural
software and the genuine returned results to pass the project verification criteria.
</p>
</body>
</html>
"""


