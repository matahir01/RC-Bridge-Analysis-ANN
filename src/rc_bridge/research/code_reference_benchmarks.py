from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.application.extended_actions import ExtendedActionSettings
from rc_bridge.codes.common import LoadEffects
from rc_bridge.codes.eurocode.combinations import EurocodeFactors, persistent_uls
from rc_bridge.codes.eurocode.en1991_2 import (
    lm1_characteristic_lane_load,
    notional_lane_layout,
    lm1_remaining_area_udl_kn_m2,
    lm1_tandem_axle_spacing_m,
)
from rc_bridge.design.eurocode_demand import required_tension_steel_rectangular
from rc_bridge.design.eurocode_detailing import maximum_vertical_link_spacings_mm
from rc_bridge.design.eurocode_fatigue import (
    concrete_compression_fatigue_check,
    concrete_design_fatigue_strength_mpa,
    reinforcement_fatigue_check,
)
from rc_bridge.design.eurocode_flexure import rectangular_singly_reinforced_resistance
from rc_bridge.design.eurocode_shear import concrete_shear_resistance
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


JRC_LM1_CHARACTERISTIC_VALUES = ReferenceBenchmarkEvidence(
    key="jrc_bridge_lm1_characteristic_values",
    source_name="JRC Bridge Design to Eurocodes - EN 1991 road traffic actions",
    source_reference=(
        "Chapter 3, section 3.9.1.2, Table 3.6 and Figure 3.10: "
        "LM1 lane 1 Q1k=300 kN/q1k=9.0 kN/m2; lane 2 200/2.5; "
        "lane 3 100/2.5; other lanes 0/2.5; remaining area 2.5 kN/m2; "
        "two tandem axles at 1.2 m longitudinal spacing."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "Bridge_Design-Eurocodes-Worked_examples.pdf"
    ),
    scope=(
        "Independent published characteristic LM1 load-definition reference. "
        "It verifies the basic lane/tandem magnitudes and axle spacing only, not "
        "the bridge-wide moving-load search or governing placement algorithm."
    ),
)

JRC_LM1_LANE_SUBDIVISION = ReferenceBenchmarkEvidence(
    key="jrc_bridge_lm1_lane_subdivision",
    source_name="JRC Bridge Design to Eurocodes - EN 1991 lane subdivision",
    source_reference=(
        "Chapter 3, section 3.9.1.1, Table 3.5: w<5.4 m -> one 3 m lane "
        "plus remaining width; 5.4<=w<6.0 m -> two lanes each 0.5w; "
        "w>=6.0 m -> int(w/3) lanes each 3 m plus w-3n remaining area."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "Bridge_Design-Eurocodes-Worked_examples-main_only.pdf"
    ),
    scope=(
        "Independent published verification of EN 1991-2 carriageway subdivision only. "
        "Lane numbering/positioning to maximize effects and the moving-load search remain "
        "separate verification targets."
    ),
)

JRC_REINFORCEMENT_FATIGUE = ReferenceBenchmarkEvidence(
    key="jrc_bridge_reinforcement_fatigue",
    source_name="JRC Bridge Design to Eurocodes - EN 1992-2 reinforcement fatigue",
    source_reference=(
        "Chapter 5 transverse slab fatigue example: lambda_s=0.89, "
        "Delta sigma_s,Ec=88 MPa, Delta sigma_s,equ=78 MPa; "
        "Delta sigma_Rsk/gamma_s,fat=162.5/1.15=141 MPa and the check passes."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "Bridge_Design-Eurocodes-Worked_examples.pdf"
    ),
    scope=(
        "Independent published verification of the EN 1992-2 equivalent-stress-range "
        "reinforcement fatigue equation only. FLM3 structural stress-range generation "
        "and fatigue lane placement remain separate verification targets."
    ),
)

JRC_CONCRETE_FATIGUE = ReferenceBenchmarkEvidence(
    key="jrc_bridge_concrete_compression_fatigue",
    source_name="JRC Bridge Design to Eurocodes - EN 1992-2 concrete fatigue",
    source_reference=(
        "Chapter 5 note following the reinforcement-fatigue example: for fck=35 MPa "
        "with recommended alpha_cc=0.85 and beta_cc(t0)=1.1..1.2, fcd,fat is about "
        "16..17.5 MPa; sigma_c,max=11.9 MPa and sigma_c,min=3.5 MPa do not satisfy "
        "EN 1992-2 Expression 6.77."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "Bridge_Design-Eurocodes-Worked_examples.pdf"
    ),
    scope=(
        "Independent published verification of the concrete-compression fatigue "
        "strength/check equation only. Traffic-derived concrete stress histories remain "
        "a separate verification target."
    ),
)


JRC_ROAD_BRIDGE_COMBINATION_FACTORS = ReferenceBenchmarkEvidence(
    key="jrc_road_bridge_combination_factors",
    source_name="JRC road-bridge EN 1990/EN 1991 combination references",
    source_reference=(
        "Bridge worked examples Table 3.8: gr1a frequent factors psi1=0.75 "
        "for the tandem system and psi1=0.40 for the UDL, with psi2=0; "
        "JRC Designers experience example: road-traffic gamma_Q=1.35, "
        "Q=1200 kN -> Qd=1620 kN."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "Bridge_Design-Eurocodes-Worked_examples.pdf"
    ),
    scope=(
        "Independent published reference for the road-traffic ULS partial factor "
        "and the split LM1 frequent TS/UDL factors only. It does not by itself "
        "certify the complete EN 1990 bridge group/leading/accompanying-action matrix."
    ),
)

JRC_EC2_SLAB_SHEAR = ReferenceBenchmarkEvidence(
    key="jrc_bridge_ec2_slab_shear_without_links",
    source_name="JRC Bridge Design to Eurocodes - concrete bridge design",
    source_reference=(
        "Section 5.2.2.7 / Vienna concrete-bridge worked example: "
        "fck=35 MPa, d=360 mm, Asl=1848 mm2, bw=1000 mm, sigma_cp=0; "
        "k=1.75, rho_l=0.51%, v_main=0.55 MPa, v_min=0.48 MPa and "
        "V_Rd,c=198 kN/m versus V_Ed=235 kN/m."
    ),
    source_url=(
        "https://eurocodes.jrc.ec.europa.eu/sites/default/files/2022-06/"
        "2010_Bridges_EN1992_GMancini_EBouchon.pdf"
    ),
    scope=(
        "Independent published EC2 concrete-shear-without-specific-shear-"
        "reinforcement reference. It supports V_Rd,c only; link design, V_Rd,s "
        "and V_Rd,max remain separate verification targets."
    ),
)


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


def jrc_lm1_characteristic_values_benchmark() -> IndependentBenchmarkReport:
    """Compare the native first-generation LM1 constants with JRC Table 3.6."""

    lane1 = lm1_characteristic_lane_load(1)
    lane2 = lm1_characteristic_lane_load(2)
    lane3 = lm1_characteristic_lane_load(3)
    lane4 = lm1_characteristic_lane_load(4)

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_LM1_CHARACTERISTIC_VALUES.source_name,
        source_reference=JRC_LM1_CHARACTERISTIC_VALUES.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="LM1 lane 1 tandem axle load",
                    reference_value=300.0,
                    unit="kN",
                    absolute_tolerance=1.0e-9,
                ),
                lane1.axle_load_kn,
            ),
            (
                BenchmarkTarget(
                    name="LM1 lane 1 UDL",
                    reference_value=9.0,
                    unit="kN/m2",
                    absolute_tolerance=1.0e-9,
                ),
                lane1.udl_kn_m2,
            ),
            (
                BenchmarkTarget(
                    name="LM1 lane 2 tandem axle load",
                    reference_value=200.0,
                    unit="kN",
                    absolute_tolerance=1.0e-9,
                ),
                lane2.axle_load_kn,
            ),
            (
                BenchmarkTarget(
                    name="LM1 lane 2 UDL",
                    reference_value=2.5,
                    unit="kN/m2",
                    absolute_tolerance=1.0e-9,
                ),
                lane2.udl_kn_m2,
            ),
            (
                BenchmarkTarget(
                    name="LM1 lane 3 tandem axle load",
                    reference_value=100.0,
                    unit="kN",
                    absolute_tolerance=1.0e-9,
                ),
                lane3.axle_load_kn,
            ),
            (
                BenchmarkTarget(
                    name="LM1 lane 3 UDL",
                    reference_value=2.5,
                    unit="kN/m2",
                    absolute_tolerance=1.0e-9,
                ),
                lane3.udl_kn_m2,
            ),
            (
                BenchmarkTarget(
                    name="LM1 other-lane tandem axle load",
                    reference_value=0.0,
                    unit="kN",
                    absolute_tolerance=1.0e-9,
                ),
                lane4.axle_load_kn,
            ),
            (
                BenchmarkTarget(
                    name="LM1 other-lane UDL",
                    reference_value=2.5,
                    unit="kN/m2",
                    absolute_tolerance=1.0e-9,
                ),
                lane4.udl_kn_m2,
            ),
            (
                BenchmarkTarget(
                    name="LM1 remaining-area UDL",
                    reference_value=2.5,
                    unit="kN/m2",
                    absolute_tolerance=1.0e-9,
                ),
                lm1_remaining_area_udl_kn_m2(),
            ),
            (
                BenchmarkTarget(
                    name="LM1 tandem axle spacing",
                    reference_value=1.2,
                    unit="m",
                    absolute_tolerance=1.0e-12,
                ),
                lm1_tandem_axle_spacing_m(),
            ),
        ),
        notes=(
            "Recommended/basic alpha factors are 1.0. The benchmark deliberately "
            "checks characteristic load definitions before any transverse or "
            "longitudinal placement/search logic."
        ),
    )


def jrc_lm1_lane_subdivision_benchmark() -> IndependentBenchmarkReport:
    """Reproduce JRC Table 3.5 notional-lane subdivision cases."""

    cases = (
        (5.0, 1, 3.0, 2.0),
        (5.8, 2, 2.9, 0.0),
        (7.0, 2, 3.0, 1.0),
        (10.0, 3, 3.0, 1.0),
    )
    observations: list[tuple[BenchmarkTarget, float]] = []
    for width_m, lane_count, lane_width_m, remainder_m in cases:
        layout = notional_lane_layout(width_m)
        observations.extend(
            (
                (
                    BenchmarkTarget(
                        name=f"w={width_m:g} m lane count",
                        reference_value=float(lane_count),
                        unit="-",
                        absolute_tolerance=1.0e-12,
                    ),
                    float(layout.lane_count),
                ),
                (
                    BenchmarkTarget(
                        name=f"w={width_m:g} m lane width",
                        reference_value=lane_width_m,
                        unit="m",
                        absolute_tolerance=1.0e-12,
                    ),
                    layout.lane_width_m,
                ),
                (
                    BenchmarkTarget(
                        name=f"w={width_m:g} m remaining width",
                        reference_value=remainder_m,
                        unit="m",
                        absolute_tolerance=1.0e-12,
                    ),
                    layout.remaining_width_m,
                ),
            )
        )

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_LM1_LANE_SUBDIVISION.source_name,
        source_reference=JRC_LM1_LANE_SUBDIVISION.source_reference,
        observations=tuple(observations),
        notes=(
            "The 7.0 m case is the thesis carriageway width: two 3.0 m notional "
            "lanes plus 1.0 m remaining area. This benchmark verifies subdivision, "
            "not the transverse lane placement chosen to maximize each response."
        ),
    )


def jrc_reinforcement_fatigue_benchmark() -> IndependentBenchmarkReport:
    """Reproduce the JRC equivalent-stress-range reinforcement fatigue example."""

    result = reinforcement_fatigue_check(
        reference_stress_range_mpa=88.0,
        lambda_s=0.89,
        phi_fat=1.0,
        characteristic_fatigue_strength_mpa=162.5,
        gamma_s_fat=1.15,
    )
    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_REINFORCEMENT_FATIGUE.source_name,
        source_reference=JRC_REINFORCEMENT_FATIGUE.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="reinforcement equivalent stress range",
                    reference_value=78.0,
                    unit="MPa",
                    absolute_tolerance=0.5,
                ),
                result.equivalent_stress_range_mpa,
            ),
            (
                BenchmarkTarget(
                    name="reinforcement design fatigue resistance",
                    reference_value=141.0,
                    unit="MPa",
                    absolute_tolerance=0.5,
                ),
                result.design_fatigue_resistance_mpa,
            ),
        ),
        notes=(
            "Published values are rounded. The native calculation gives 78.32 MPa "
            "and 141.30 MPa and therefore reproduces the passing JRC check."
        ),
    )


def jrc_concrete_fatigue_benchmark() -> IndependentBenchmarkReport:
    """Reproduce the JRC concrete-compression fatigue strength range."""

    low = concrete_design_fatigue_strength_mpa(
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=0.85,
        k1=0.85,
        beta_cc_t0=1.10,
    )
    high = concrete_design_fatigue_strength_mpa(
        fck_mpa=35.0,
        gamma_c=1.50,
        alpha_cc=0.85,
        k1=0.85,
        beta_cc_t0=1.20,
    )
    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_CONCRETE_FATIGUE.source_name,
        source_reference=JRC_CONCRETE_FATIGUE.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="concrete fatigue strength beta_cc=1.10",
                    reference_value=16.0,
                    unit="MPa",
                    absolute_tolerance=0.10,
                ),
                low,
            ),
            (
                BenchmarkTarget(
                    name="concrete fatigue strength beta_cc=1.20",
                    reference_value=17.5,
                    unit="MPa",
                    absolute_tolerance=0.15,
                ),
                high,
            ),
        ),
        notes=(
            "The source gives a rounded 16..17.5 MPa range. The native endpoints "
            "are 15.95 and 17.40 MPa. Using the cited 11.9/3.5 MPa concrete stresses, "
            "Expression 6.77 remains unsatisfied at both endpoints, as reported by JRC."
        ),
    )


def jrc_road_bridge_combination_factors_benchmark() -> IndependentBenchmarkReport:
    """Check the v1 road-bridge traffic factors against published JRC examples."""

    factors = EurocodeFactors()
    settings = ExtendedActionSettings()
    traffic_force = LoadEffects(shear_kn=1200.0)
    design_force = persistent_uls(LoadEffects(), traffic_force, factors).effects.shear_kn

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_ROAD_BRIDGE_COMBINATION_FACTORS.source_name,
        source_reference=JRC_ROAD_BRIDGE_COMBINATION_FACTORS.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="road-traffic ULS partial factor gamma_Q",
                    reference_value=1.35,
                    unit="-",
                    absolute_tolerance=1.0e-12,
                ),
                factors.gamma_q_traffic,
            ),
            (
                BenchmarkTarget(
                    name="published 1200 kN traffic design force",
                    reference_value=1620.0,
                    unit="kN",
                    absolute_tolerance=0.01,
                ),
                design_force,
            ),
            (
                BenchmarkTarget(
                    name="LM1 frequent tandem factor",
                    reference_value=0.75,
                    unit="-",
                    absolute_tolerance=1.0e-12,
                ),
                settings.gr2_lm1_tandem_factor,
            ),
            (
                BenchmarkTarget(
                    name="LM1 frequent UDL factor",
                    reference_value=0.40,
                    unit="-",
                    absolute_tolerance=1.0e-12,
                ),
                settings.gr2_lm1_udl_factor,
            ),
        ),
        notes=(
            "The TS and UDL frequent factors are checked separately because scaling "
            "a combined characteristic LM1 envelope by one psi factor can change or "
            "misstate the governing placement."
        ),
    )


def jrc_ec2_slab_shear_benchmark() -> IndependentBenchmarkReport:
    """Reproduce the JRC 1 m slab-strip V_Rd,c worked example."""

    result = concrete_shear_resistance(
        web_width_m=1.0,
        effective_depth_m=0.360,
        longitudinal_steel_area_mm2=1848.0,
        fck_mpa=35.0,
        gamma_c=1.50,
        c_rdc_factor=0.18,
        sigma_cp_mpa=0.0,
        k1=0.15,
    )
    bw_mm = 1000.0
    d_mm = 360.0
    vmin_mpa = result.vmin_kn * 1000.0 / (bw_mm * d_mm)
    vrdc_mpa = result.vrdc_kn * 1000.0 / (bw_mm * d_mm)

    return build_independent_benchmark_report(
        solver_profile=SolverProfile.EUROCODE_1G,
        source_name=JRC_EC2_SLAB_SHEAR.source_name,
        source_reference=JRC_EC2_SLAB_SHEAR.source_reference,
        observations=(
            (
                BenchmarkTarget(
                    name="EC2 shear size-effect factor k",
                    reference_value=1.75,
                    unit="-",
                    absolute_tolerance=0.01,
                ),
                result.k,
            ),
            (
                BenchmarkTarget(
                    name="EC2 longitudinal reinforcement ratio rho_l",
                    reference_value=0.0051,
                    unit="-",
                    absolute_tolerance=5.0e-5,
                ),
                result.rho_l,
            ),
            (
                BenchmarkTarget(
                    name="EC2 minimum shear stress v_min",
                    reference_value=0.48,
                    unit="MPa",
                    absolute_tolerance=0.01,
                ),
                vmin_mpa,
            ),
            (
                BenchmarkTarget(
                    name="EC2 governing concrete shear stress",
                    reference_value=0.55,
                    unit="MPa",
                    absolute_tolerance=0.01,
                ),
                vrdc_mpa,
            ),
            (
                BenchmarkTarget(
                    name="EC2 concrete shear resistance V_Rd,c",
                    reference_value=198.0,
                    unit="kN",
                    absolute_tolerance=1.0,
                ),
                result.vrdc_kn,
            ),
        ),
        notes=(
            "The JRC source rounds k, rho_l, stresses and V_Rd,c. Tolerances cover "
            "published rounding only. The example demonstrates that V_Rd,c is below "
            "the cited V_Ed=235 kN/m and therefore does not validate link design."
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
        jrc_lm1_characteristic_values_benchmark(),
        jrc_lm1_lane_subdivision_benchmark(),
        jrc_road_bridge_combination_factors_benchmark(),
        jrc_ec2_slab_shear_benchmark(),
        jrc_rectangular_flexure_benchmark(),
        jrc_beam_link_spacing_benchmark(),
        jrc_reinforcement_fatigue_benchmark(),
        jrc_concrete_fatigue_benchmark(),
    )
