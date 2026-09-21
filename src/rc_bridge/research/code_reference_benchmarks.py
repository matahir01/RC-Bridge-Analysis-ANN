from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.design.eurocode_detailing import maximum_vertical_link_spacings_mm
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.research.benchmarking import (
    BenchmarkTarget,
    IndependentBenchmarkReport,
    build_independent_benchmark_report,
)
from rc_bridge.research.verification import SolverProfile


@dataclass(frozen=True)
class ReferenceBenchmarkEvidence:
    """Traceable metadata for one independent published worked example."""

    key: str
    source_name: str
    source_reference: str
    source_url: str
    scope: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Reference benchmark key cannot be empty.")
        if not self.source_name.strip():
            raise ValueError("Reference benchmark source name cannot be empty.")
        if not self.source_reference.strip():
            raise ValueError("Reference benchmark source reference cannot be empty.")
        if not self.source_url.strip():
            raise ValueError("Reference benchmark source URL cannot be empty.")
        if not self.scope.strip():
            raise ValueError("Reference benchmark scope cannot be empty.")


JRC_RECTANGULAR_FLEXURE = ReferenceBenchmarkEvidence(
    key="jrc_handbook2_rectangular_flexure",
    source_name="JRC Eurocodes Handbook 2 - Reliability backgrounds",
    source_reference=(
        "Annex B, Reinforced concrete beam or slab - bending moment example; "
        "b=1.0 m, d=0.17 m, fck=20 MPa, fyk=500 MPa, gamma_c=1.5, "
        "gamma_s=1.15, alpha_cc=1.0, MEd=62.78 kNm, A_s=0.000933 m2"
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2021-12/handbook2.pdf"
    ),
    scope=(
        "Independent first-generation Eurocode rectangular singly reinforced flexure "
        "reference case. It supports the basic rectangular flexure kernel only."
    ),
)

JRC_BEAM_LINK_SPACING = ReferenceBenchmarkEvidence(
    key="jrc_beam_a2_b2_c2_link_spacing",
    source_name="JRC Eurocode 2 Background and Applications - Detailing of reinforcement",
    source_reference=(
        "Section 4.2.2.1 Beam A2-B2-C2, case 1; h=400 mm, c_nom=30 mm, "
        "phi_w=8 mm, phi=16 mm, d=354 mm; s_l,max=s_t,max=0.75d=266 mm"
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/1110_WS_EC2.pdf"
    ),
    scope=(
        "Independent EC2 beam-link spacing reference case. It supports the vertical-link "
        "spacing rule only, not the complete detailing workflow."
    ),
)


def jrc_rectangular_flexure_benchmark() -> IndependentBenchmarkReport:
    """Compare the rectangular flexure kernel with the JRC Annex-B worked example."""

    design_moment_knm = 62.78
    width_m = 1.0
    effective_depth_m = 0.17
    fck_mpa = 20.0
    fyk_mpa = 500.0
    reference_steel_mm2 = 933.0

    required_steel_mm2 = required_tension_steel_rectangular(
        design_moment_knm,
        width_m,
        effective_depth_m,
        fck_mpa,
        fyk_mpa,
        gamma_c=1.50,
        gamma_s=1.15,
        alpha_cc=1.0,
    )
    resistance = rectangular_singly_reinforced_resistance(
        width_m,
        effective_depth_m,
        reference_steel_mm2,
        fck_mpa,
        fyk_mpa,
        gamma_c=1.50,
        gamma_s=1.15,
        alpha_cc=1.0,
    )

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_RECTANGULAR_FLEXURE.source_name,
        source_reference=JRC_RECTANGULAR_FLEXURE.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="required rectangular tension steel",
                    reference_value=reference_steel_mm2,
                    unit="mm2",
                    absolute_tolerance=2.0,
                ),
                required_steel_mm2,
            ),
            (
                BenchmarkTarget(
                    name="moment resistance using published steel area",
                    reference_value=design_moment_knm,
                    unit="kNm",
                    absolute_tolerance=0.05,
                ),
                resistance.resistance_knm,
            ),
        ),
        notes=(
            "The JRC source reports A=0.000933 m2 after the worked calculation. "
            "The separate preliminary estimate in the source uses z approximately 0.9d "
            "and is intentionally not used as the benchmark target."
        ),
    )


def jrc_beam_link_spacing_benchmark() -> IndependentBenchmarkReport:
    """Compare EC2 beam-link spacing limits with the JRC A2-B2-C2 example."""

    longitudinal_mm, transverse_mm = maximum_vertical_link_spacings_mm(
        effective_depth_m=0.354,
    )

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_BEAM_LINK_SPACING.source_name,
        source_reference=JRC_BEAM_LINK_SPACING.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="maximum longitudinal link spacing",
                    reference_value=266.0,
                    unit="mm",
                    absolute_tolerance=0.6,
                ),
                longitudinal_mm,
            ),
            (
                BenchmarkTarget(
                    name="maximum transverse link-leg spacing",
                    reference_value=266.0,
                    unit="mm",
                    absolute_tolerance=0.6,
                ),
                transverse_mm,
            ),
        ),
        notes=(
            "The published example reports d=354 mm and rounds 0.75d=265.5 mm "
            "to 266 mm. The benchmark tolerance covers that published rounding only."
        ),
    )


def eurocode_v1_published_reference_benchmarks() -> tuple[IndependentBenchmarkReport, ...]:
    """Return the currently implemented published-reference benchmark set."""

    return (
        jrc_rectangular_flexure_benchmark(),
        jrc_beam_link_spacing_benchmark(),
    )
