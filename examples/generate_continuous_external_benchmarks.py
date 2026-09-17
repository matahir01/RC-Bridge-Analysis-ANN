from __future__ import annotations

import argparse
from pathlib import Path

from rc_bridge.core.models import BridgeGeometry, ProjectInput, SupportSystem
from rc_bridge.research.benchmark_suite import build_standard_continuous_line_benchmark_suite


def build_example_suite_files() -> dict[str, str]:
    """Build a fixed synthetic two-span suite for MIDAS/STAAD solver verification."""
    project = ProjectInput(
        name="Controlled external solver benchmark",
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0],
            support_system=SupportSystem.CONTINUOUS,
        ),
    )
    suite = build_standard_continuous_line_benchmark_suite(
        project,
        ei_kn_m2_by_span=(1.0e6, 1.0e6),
        analysis_area_m2_by_span=(0.45, 0.45),
    )
    return suite.files()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate controlled MIDAS Civil/STAAD.Pro benchmark files. "
            "These are synthetic solver-verification cases, not bridge-design load cases."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark_exports"),
        help="Directory to receive the generated benchmark files.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    files = build_example_suite_files()
    for filename, content in files.items():
        (args.output / filename).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} benchmark files to {args.output.resolve()}")


if __name__ == "__main__":
    main()
