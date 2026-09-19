from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from rc_bridge.application.project_io import load_project, save_project
from rc_bridge.application.session import BridgeApplicationSession
from rc_bridge.core.models import ProjectInput


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rc-bridge",
        description="RC Bridge Analysis deterministic application tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="Create a validated project JSON file.")
    new.add_argument("project_file", type=Path)

    summary = sub.add_parser("summary", help="Print the validated project definition.")
    summary.add_argument("project_file", type=Path)

    analyse = sub.add_parser(
        "analyze-lm1",
        help=(
            "Run native full-width Eurocode LM1 and write HTML/PDF reports plus "
            "governing verification files."
        ),
    )
    analyse.add_argument("project_file", type=Path)
    analyse.add_argument("--output", type=Path, required=True)
    analyse.add_argument("--grid-spacing", type=float, default=None)
    analyse.add_argument("--traffic-step", type=float, default=None)
    analyse.add_argument("--max-tandem-combinations", type=int, default=None)
    return parser


def _summary(project: ProjectInput) -> str:
    geometry = project.geometry
    spans = ", ".join(f"{float(value):.3f}" for value in geometry.span_lengths_m)
    profile = (
        "undefined"
        if geometry.girder_profile is None
        else geometry.girder_profile.section_type.value
    )
    return "\n".join(
        (
            f"Project: {project.name}",
            f"Code: {project.design_code.value}",
            f"Support system: {geometry.support_system.value}",
            f"Spans (m): {spans}",
            (
                f"Deck / carriageway (m): {float(geometry.deck_width_m):.3f} / "
                f"{float(geometry.carriageway_width_m):.3f}"
            ),
            (
                f"Girders: {int(geometry.girder_count)} @ "
                f"{float(geometry.girder_spacing_m):.3f} m"
            ),
            f"Physical girder profile: {profile}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "new":
        path = save_project(ProjectInput(), args.project_file)
        print(f"Created {path}")
        print(
            "Define a complete physical girder profile before native grillage analysis."
        )
        return 0

    if args.command == "summary":
        print(_summary(load_project(args.project_file)))
        return 0

    if args.command == "analyze-lm1":
        session = BridgeApplicationSession.open(args.project_file)
        result = session.run_native_lm1(
            grid_spacing_m=args.grid_spacing,
            longitudinal_step_m=args.traffic_step,
            max_exhaustive_tandem_combinations=args.max_tandem_combinations,
        )
        args.output.mkdir(parents=True, exist_ok=True)
        html_report = session.write_last_lm1_report(
            args.output / "calculation_report.html"
        )
        pdf_report = session.write_last_lm1_pdf_report(
            args.output / "calculation_report.pdf"
        )
        verification = session.export_last_lm1_verification(
            args.output / "verification",
            base_name="application_lm1_governing",
        )
        print(
            f"Completed {result.evaluated_case_count} LM1 cases; "
            f"HTML: {html_report}; PDF: {pdf_report}; "
            f"MIDAS: {verification.midas_mct}; STAAD: {verification.staad_std}; "
            f"governing verification cases: {len(verification.case_ids)}"
        )
        return 0

    raise RuntimeError(f"Unhandled command {args.command!r}.")


if __name__ == "__main__":
    raise SystemExit(main())
