from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import ProjectInput, SupportSystem
from rc_bridge.research.line_benchmark import (
    ContinuousLineBenchmarkPackage,
    build_continuous_line_benchmark_package,
    continuous_line_benchmark_case_specs,
)
from rc_bridge.workflow.project_continuous import (
    GlobalBeamPointLoad,
    ProjectContinuousLoadCase,
)


@dataclass(frozen=True)
class ControlledLineBenchmarkParameters:
    """Synthetic load magnitudes used only for external solver verification cases."""

    equal_udl_kn_m: float = 20.0
    asymmetric_udl_kn_m: float = 20.0
    point_load_kn: float = 100.0
    mixed_udl_span_1_kn_m: float = 15.0
    mixed_udl_span_2_kn_m: float = 10.0
    mixed_point_load_kn: float = 80.0

    def __post_init__(self) -> None:
        values = (
            self.equal_udl_kn_m,
            self.asymmetric_udl_kn_m,
            self.point_load_kn,
            self.mixed_udl_span_1_kn_m,
            self.mixed_udl_span_2_kn_m,
            self.mixed_point_load_kn,
        )
        if any(value <= 0.0 for value in values):
            raise ValueError("Controlled benchmark load magnitudes must all be positive.")


@dataclass(frozen=True)
class ControlledLineBenchmarkSuite:
    packages: tuple[ContinuousLineBenchmarkPackage, ...]
    parameters: ControlledLineBenchmarkParameters

    def __post_init__(self) -> None:
        if not self.packages:
            raise ValueError("Controlled line benchmark suite cannot be empty.")

    def files(self) -> dict[str, str]:
        """Flatten every case package into one non-colliding file bundle."""
        files: dict[str, str] = {}
        for package in self.packages:
            case_files = package.files()
            overlap = set(files) & set(case_files)
            if overlap:
                raise RuntimeError(
                    "Controlled benchmark cases generated duplicate filenames: "
                    + ", ".join(sorted(overlap))
                )
            files.update(case_files)
        return files


def build_standard_continuous_line_benchmark_suite(
    project: ProjectInput,
    *,
    ei_kn_m2_by_span: tuple[float, float],
    analysis_area_m2_by_span: tuple[float, float],
    parameters: ControlledLineBenchmarkParameters | None = None,
    torsion_constant_m4_by_span: tuple[float, float] | None = None,
) -> ControlledLineBenchmarkSuite:
    """Build four controlled two-span benchmark packages in one call.

    The cases are intentionally synthetic and code-neutral. They isolate solver
    mechanics rather than representing Eurocode traffic or design combinations.
    """
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Controlled continuous benchmark suite requires CONTINUOUS supports.")
    spans = tuple(float(value) for value in project.geometry.span_lengths_m)
    if len(spans) != 2:
        raise ValueError("Controlled line benchmark suite currently requires exactly two spans.")
    if len(ei_kn_m2_by_span) != 2 or any(value <= 0.0 for value in ei_kn_m2_by_span):
        raise ValueError("Benchmark suite requires two positive EI values.")
    if len(analysis_area_m2_by_span) != 2 or any(
        value <= 0.0 for value in analysis_area_m2_by_span
    ):
        raise ValueError("Benchmark suite requires two positive analysis areas.")

    params = parameters or ControlledLineBenchmarkParameters()
    specs = {spec.case_id: spec for spec in continuous_line_benchmark_case_specs()}
    first_midspan = 0.5 * spans[0]
    second_midspan_global = spans[0] + 0.5 * spans[1]

    load_cases = {
        "continuous-2span-equal-udl": ProjectContinuousLoadCase(
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            udl_kn_m_by_span=(params.equal_udl_kn_m, params.equal_udl_kn_m),
            name="continuous-2span-equal-udl",
        ),
        "continuous-2span-asymmetric-udl": ProjectContinuousLoadCase(
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            udl_kn_m_by_span=(params.asymmetric_udl_kn_m, 0.0),
            name="continuous-2span-asymmetric-udl",
        ),
        "continuous-2span-point-load": ProjectContinuousLoadCase(
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            udl_kn_m_by_span=(0.0, 0.0),
            point_loads=(
                GlobalBeamPointLoad(
                    magnitude_kn=params.point_load_kn,
                    position_m=first_midspan,
                    label="controlled first-span midspan point load",
                ),
            ),
            name="continuous-2span-point-load",
        ),
        "continuous-2span-mixed-load": ProjectContinuousLoadCase(
            ei_kn_m2_by_span=ei_kn_m2_by_span,
            udl_kn_m_by_span=(
                params.mixed_udl_span_1_kn_m,
                params.mixed_udl_span_2_kn_m,
            ),
            point_loads=(
                GlobalBeamPointLoad(
                    magnitude_kn=params.mixed_point_load_kn,
                    position_m=second_midspan_global,
                    label="controlled second-span midspan point load",
                ),
            ),
            name="continuous-2span-mixed-load",
        ),
    }

    packages = tuple(
        build_continuous_line_benchmark_package(
            project,
            load_cases[case_id],
            case_spec=specs[case_id],
            analysis_area_m2_by_span=analysis_area_m2_by_span,
            torsion_constant_m4_by_span=torsion_constant_m4_by_span,
        )
        for case_id in (
            "continuous-2span-equal-udl",
            "continuous-2span-asymmetric-udl",
            "continuous-2span-point-load",
            "continuous-2span-mixed-load",
        )
    )
    return ControlledLineBenchmarkSuite(packages=packages, parameters=params)
