from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)


class AcceptanceState(str, Enum):
    """Evidence maturity for one deterministic-v1 acceptance item."""

    EXTERNALLY_ACCEPTED = "externally_accepted"
    INTERNAL_ONLY = "internal_only"
    PENDING_INDEPENDENT_CHECK = "pending_independent_check"
    DEFERRED_V2 = "deferred_v2"
    OUT_OF_SCOPE = "out_of_scope"


class AcceptanceDomain(str, Enum):
    """Engineering domain being accepted; analysis and design stay separate."""

    STRUCTURAL_ANALYSIS = "structural_analysis"
    CODE_LOADING = "code_loading"
    DESIGN_RESISTANCE = "design_resistance"
    SERVICEABILITY = "serviceability"
    FATIGUE_DETAILING = "fatigue_detailing"
    PROFILE_SCOPE = "profile_scope"


@dataclass(frozen=True)
class AcceptanceItem:
    """One auditable release/verification item.

    The v1_gate flag means the item must be independently accepted before the
    named solver profile can be represented as fully verified for research or
    production use. Internal tests and cross-kernel comparisons are useful
    evidence, but deliberately do not become EXTERNALLY_ACCEPTED.
    """

    key: str
    title: str
    domain: AcceptanceDomain
    state: AcceptanceState
    v1_gate: bool
    evidence: str
    boundary: str
    next_evidence: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Acceptance-item key cannot be empty.")
        if not self.title.strip():
            raise ValueError("Acceptance-item title cannot be empty.")
        if not self.evidence.strip():
            raise ValueError("Acceptance-item evidence cannot be empty.")
        if not self.boundary.strip():
            raise ValueError("Acceptance-item boundary cannot be empty.")
        if not self.next_evidence.strip():
            raise ValueError("Acceptance-item next_evidence cannot be empty.")


@dataclass(frozen=True)
class V1AcceptanceMatrix:
    """Evidence matrix for one deterministic solver profile.

    This matrix is intentionally stricter than the Stage-5 STAAD comparison.
    External structural-solver agreement verifies the mechanics of the exported
    grillage model and response. It does not, by itself, prove that EN 1991-2
    load generation, EN 1990 combinations, or EN 1992 design equations are
    clause-correct. Those are separate acceptance targets.
    """

    name: str
    solver_profile: SolverProfile
    source_reference: str
    items: tuple[AcceptanceItem, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Acceptance-matrix name cannot be empty.")
        if not self.source_reference.strip():
            raise ValueError("Acceptance-matrix source_reference cannot be empty.")
        keys = [item.key for item in self.items]
        if not keys:
            raise ValueError("Acceptance matrix requires at least one item.")
        if len(keys) != len(set(keys)):
            raise ValueError("Acceptance-matrix item keys must be unique.")

    @property
    def externally_accepted_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.items
            if item.state is AcceptanceState.EXTERNALLY_ACCEPTED
        )

    @property
    def pending_v1_gate_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.items
            if item.v1_gate
            and item.state is not AcceptanceState.EXTERNALLY_ACCEPTED
        )

    @property
    def deferred_v2_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.items
            if item.state is AcceptanceState.DEFERRED_V2
        )

    @property
    def structural_analysis_accepted(self) -> bool:
        structural = tuple(
            item
            for item in self.items
            if item.v1_gate
            and item.domain is AcceptanceDomain.STRUCTURAL_ANALYSIS
        )
        return bool(structural) and all(
            item.state is AcceptanceState.EXTERNALLY_ACCEPTED
            for item in structural
        )

    @property
    def full_v1_profile_accepted(self) -> bool:
        return not self.pending_v1_gate_keys

    def item(self, key: str) -> AcceptanceItem:
        for item in self.items:
            if item.key == key:
                return item
        raise KeyError(key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "solver_profile": self.solver_profile.value,
            "source_reference": self.source_reference,
            "structural_analysis_accepted": self.structural_analysis_accepted,
            "full_v1_profile_accepted": self.full_v1_profile_accepted,
            "externally_accepted_keys": list(self.externally_accepted_keys),
            "pending_v1_gate_keys": list(self.pending_v1_gate_keys),
            "deferred_v2_keys": list(self.deferred_v2_keys),
            "items": [
                {
                    **asdict(item),
                    "domain": item.domain.value,
                    "state": item.state.value,
                }
                for item in self.items
            ],
        }

    def research_verification_manifest(
        self,
        *,
        torsion_required: bool = True,
    ) -> DeterministicSolverVerification:
        """Map only independently accepted targets into the research lock.

        This is the key safeguard for Batch 6: a genuine STAAD analysis PASS
        must not silently unlock flexure, shear, cracking, serviceability,
        fatigue, detailing, traffic-code interpretation or load-combination
        milestones that STAAD did not independently verify.
        """

        accepted = set(self.externally_accepted_keys)

        return DeterministicSolverVerification(
            solver_profile=self.solver_profile,
            traffic_loading="lm1_code_loading" in accepted,
            load_combinations="en1990_combination_rules" in accepted,
            flexure="ec2_flexure_design" in accepted,
            shear="ec2_shear_design" in accepted,
            cracking="ec2_crack_width" in accepted,
            deflection="ec2_deflection_serviceability" in accepted,
            fatigue="ec2_fatigue" in accepted,
            detailing="ec2_detailing" in accepted,
            transverse_distribution="grillage_transverse_distribution" in accepted,
            independent_benchmark="stage5_structural_response" in accepted,
            torsion_required=torsion_required,
            torsion="ec2_torsion_design" in accepted,
        )


    def msc_research_verification_manifest(self) -> DeterministicSolverVerification:
        """Return the explicitly scoped four-target MSc verification manifest.

        This manifest is intentionally narrower than deterministic application
        v1.0. It covers only the simple-span permanent+LM1 research path feeding
        g_M, g_V, g_crack and g_deflection. Fatigue, drawing-level detailing,
        torsion, construction stages, local deck design and the wider EN 1990
        action matrix remain under their own standalone-application gates.
        """

        accepted = set(self.externally_accepted_keys)
        return DeterministicSolverVerification(
            solver_profile=self.solver_profile,
            traffic_loading="lm1_code_loading" in accepted,
            load_combinations="en1990_lm1_research_combination_core" in accepted,
            flexure="ec2_msc_layered_flexure_design" in accepted,
            shear="ec2_shear_design" in accepted,
            cracking="ec2_crack_width" in accepted,
            deflection="ec2_deflection_serviceability" in accepted,
            fatigue=False,
            detailing=False,
            transverse_distribution="grillage_transverse_distribution" in accepted,
            independent_benchmark="stage5_structural_response" in accepted,
            torsion_required=False,
            torsion=False,
        )


def eurocode_simple_span_v1_acceptance_matrix() -> V1AcceptanceMatrix:
    """Return the current evidence boundary for the first Eurocode v1 profile.

    The genuine 19 Sep 2026 STAAD run is accepted as independent structural
    analysis evidence for the final-service Stage-5 grillage. The items below
    deliberately keep code-loading and RC design acceptance separate.
    """

    evidence = (
        "verification_evidence/staad_stage5_2026-09-19.json; "
        "STAAD.Pro CONNECT 22.09.00.115; engineering acceptance ACCEPTED"
    )

    return V1AcceptanceMatrix(
        name="Eurocode simple-span deterministic v1 acceptance",
        solver_profile=SolverProfile.EUROCODE_1G,
        source_reference=evidence,
        items=(
            AcceptanceItem(
                key="stage5_model_equivalence",
                title="Stage-5 exported model equivalence",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "Genuine STAAD ANL plus reviewed STAAD-resaved STD confirm 540 nodes, "
                    "749 members, 14 supports, section/material assignment, loading, "
                    "141 combinations and GLOBAL result axes."
                ),
                boundary=(
                    "This accepts equivalence of the analysed Stage-5 final-service model; "
                    "it does not certify Eurocode clause interpretation or RC design equations."
                ),
                next_evidence="No further v1 evidence required for this Stage-5 model-equivalence item.",
            ),
            AcceptanceItem(
                key="stage5_structural_response",
                title="Final-service grillage structural response",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "All 204 STAAD result sets and 1,029,792 detailed comparisons pass the "
                    "accepted v1 tolerance policy; reactions, member V/M/T and node DZ are covered."
                ),
                boundary=(
                    "Independent structural mechanics acceptance only. The same load definitions "
                    "are intentionally used in both solvers, so this does not independently prove "
                    "that those loads are the correct Eurocode loads."
                ),
                next_evidence="No further v1 evidence required for the final-service structural solver.",
            ),
            AcceptanceItem(
                key="grillage_transverse_distribution",
                title="Full-width transverse load distribution mechanics",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "The full Stage-5 grillage, including longitudinal and transverse members, "
                    "recovers the same governing LM1 source cases and accepted V/M/T envelopes in STAAD."
                ),
                boundary=(
                    "This verifies structural distribution for the exported grillage model, not the "
                    "EN 1991-2 lane/tandem generation rules used to create the traffic actions."
                ),
                next_evidence="No further v1 evidence required for transverse-distribution mechanics.",
            ),
            AcceptanceItem(
                key="elastic_displacement_response",
                title="Elastic final-service displacement response",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "STAAD GLOBAL joint DZ results agree with the native final-service grillage "
                    "within the accepted 0.001 mm absolute floor / 0.1% relative policy."
                ),
                boundary=(
                    "This verifies linear-elastic grillage displacement. It does not validate the "
                    "EC2 cracked-section, creep or tension-stiffening serviceability treatment."
                ),
                next_evidence="No further v1 evidence required for the linear-elastic solver response.",
            ),
            AcceptanceItem(
                key="lm1_characteristic_values_reference_case",
                title="Published EN 1991-2 LM1 characteristic-value reference",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC Bridge Design to Eurocodes Table 3.6/Figure 3.10 is reproduced "
                    "for lane 1/2/3/other tandem axle loads, lane/remaining-area UDLs "
                    "and the 1.2 m tandem axle spacing."
                ),
                boundary=(
                    "This independently verifies the basic characteristic LM1 constants only. "
                    "It does not certify notional-lane geometry, transverse positioning, "
                    "longitudinal moving-load search or governing placement."
                ),
                next_evidence=(
                    "Add independently checked lane-layout and placement/envelope examples "
                    "before promoting the broad LM1 loading milestone."
                ),
            ),
            AcceptanceItem(
                key="lm1_lane_subdivision_reference_case",
                title="Published EN 1991-2 notional-lane subdivision reference",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC Bridge Design to Eurocodes Table 3.5 is reproduced for the "
                    "three carriageway-width regimes. The thesis 7.0 m carriageway "
                    "therefore gives two 3.0 m notional lanes plus 1.0 m remaining area."
                ),
                boundary=(
                    "This independently verifies carriageway subdivision only. "
                    "Lane positioning/numbering to maximize response and the "
                    "longitudinal moving-load search remain separate verification targets."
                ),
                next_evidence=(
                    "Add an independently checked LM1 placement/envelope example before "
                    "promoting the broad LM1 loading milestone."
                ),
            ),
            AcceptanceItem(
                key="lm1_transverse_distribution_reference_case",
                title="Published LM1 transverse placement/distribution reference",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC D1.8 two-girder LM1 example is reproduced for the "
                    "11.0 m carriageway and three tandem systems: native code geometry "
                    "gives R1=471.43 kN and R2=128.57 kN versus published "
                    "471.4/128.6 kN."
                ),
                boundary=(
                    "This independently verifies conventional transverse lane/wheel "
                    "positioning and two-girder influence-line distribution only. "
                    "Longitudinal tandem positioning and whole-bridge governing-envelope "
                    "selection remain separate verification targets."
                ),
                next_evidence=(
                    "Add an independent longitudinal LM1 placement/envelope example "
                    "before promoting the broad LM1 loading milestone."
                ),
            ),
            AcceptanceItem(
                key="lm1_longitudinal_search_reference_case",
                title="Independent LM1 longitudinal governing-search reference",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "Independent 18 m simple-span LM1 hand calculation is reproduced: "
                    "two 300 kN axles at 1.2 m spacing govern at x=L/2-0.3=8.7 m, "
                    "with the native search returning Mmax=2523 kNm and the leading "
                    "axle coordinate 9.9 m."
                ),
                boundary=(
                    "This independently verifies the longitudinal moving-tandem search "
                    "for the simple-span MSc profile. Continuous-span LM1 placement remains "
                    "a separate solver-profile verification item."
                ),
                next_evidence=(
                    "No further longitudinal LM1 placement evidence is required for the "
                    "simple-span Eurocode MSc profile."
                ),
            ),
            AcceptanceItem(
                key="lm1_code_loading",
                title="EN 1991-2 LM1 load-generation rules",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "The simple-span MSc LM1 path now has independent evidence for characteristic "
                    "lane/remaining-area values, 1.2 m tandem spacing, notional-lane subdivision, "
                    "transverse tandem placement/distribution and longitudinal response-maximising "
                    "tandem placement. Production-search regression tests additionally cover independent "
                    "lane tandem coordinates, lane/remaining-area UDL inclusion, both carriageway-edge "
                    "layouts, M/V/T envelope extraction and co-located service-deflection recovery. "
                    "The production convergence controller halves the longitudinal movement step until "
                    "the worst M/V/T/deflection envelope change is within tolerance and refuses to "
                    "self-certify a reduced tandem search. The exact generated Stage-5 traffic cases "
                    "are also reproduced by STAAD at the structural-response level."
                ),
                boundary=(
                    "This acceptance is for the simple-span Eurocode research profile using exhaustive "
                    "independent tandem combinations and convergence-controlled longitudinal placement. "
                    "It does not promote the separate continuous-span LM1 solver profile, nor does "
                    "STAAD by itself establish code interpretation."
                ),
                next_evidence=(
                    "Simple-span MSc LM1 loading gate closed. Verify continuous-span placement "
                    "separately before unlocking that solver profile."
                ),
            ),
            AcceptanceItem(
                key="road_bridge_combination_factors_reference_case",
                title="Published road-bridge traffic combination-factor reference",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC road-bridge references are reproduced for gamma_Q,traffic=1.35 "
                    "(1200 kN -> 1620 kN) and split LM1 frequent factors "
                    "psi1,TS=0.75 and psi1,UDL=0.40."
                ),
                boundary=(
                    "This verifies the cited traffic factors only. It does not certify the "
                    "complete EN 1990 bridge leading/accompanying-action matrix or every "
                    "gr1a/gr1b/gr2/gr3/wind/thermal design situation."
                ),
                next_evidence=(
                    "Complete independent group-by-group ULS/SLS combination examples before "
                    "promoting the broad EN 1990 combination milestone."
                ),
            ),
            AcceptanceItem(
                key="en1990_lm1_research_combination_core",
                title="Published permanent+LM1 EN 1990 research-combination core",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC bridge formulas are reproduced for the MSc permanent+LM1 core: "
                    "ULS 1.35G+1.35(TS+UDL), characteristic G+TS+UDL, frequent "
                    "G+0.75TS+0.40UDL, and quasi-permanent LM1 contribution zero."
                ),
                boundary=(
                    "This independently supports the action subset used by the MSc "
                    "simple-span permanent+LM1 research profile only. It does not certify "
                    "the standalone application's complete thermal/wind/pedestrian/braking/"
                    "LM2/accompanying-action matrix."
                ),
                next_evidence=(
                    "Keep the MSc permanent+LM1 combination core as accepted evidence; "
                    "complete the general application matrix separately where those actions "
                    "are in project scope."
                ),
            ),
            AcceptanceItem(
                key="en1990_combination_rules",
                title="EN 1990 / bridge traffic combination rules",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Stage-5 exports ULS/SLS combinations and the accepted STAAD run verifies "
                    "the structural superposition mechanics for its recorded factor set. "
                    "Published JRC gamma_Q,traffic, split frequent LM1 factors and the complete "
                    "permanent+LM1 ULS/characteristic/frequent/quasi core used by the MSc profile "
                    "now pass as separate scoped code-reference cases."
                ),
                boundary=(
                    "The external solver verifies application of supplied factors, not whether the "
                    "selected EN 1990 groups, gamma values and psi factors are clause-correct."
                ),
                next_evidence=(
                    "Retain the passing MSc permanent+LM1 combination core and complete independent "
                    "general-application checks for gr1b, gr2, gr3, wind/thermal and other "
                    "leading/accompanying situations before promoting the broad application milestone."
                ),
            ),
            AcceptanceItem(
                key="construction_stage_response",
                title="Construction-stage incremental response",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.PENDING_INDEPENDENT_CHECK,
                v1_gate=True,
                evidence=(
                    "The application has separate exact stage packages and internal analytical tests; "
                    "the accepted genuine STAAD evidence is the unified final-service Stage-5 model."
                ),
                boundary=(
                    "Stage-5 acceptance does not independently validate earlier precast/deck-construction "
                    "increments or stage-specific stiffness activation."
                ),
                next_evidence="Run and compare the exported construction-stage models in STAAD.",
            ),
            AcceptanceItem(
                key="local_deck_analysis",
                title="Local transverse deck/slab analysis and design",
                domain=AcceptanceDomain.STRUCTURAL_ANALYSIS,
                state=AcceptanceState.PENDING_INDEPENDENT_CHECK,
                v1_gate=True,
                evidence=(
                    "Native strip/slab kernels and tests cover permanent, LM2 and barrier-related local actions."
                ),
                boundary="The local deck design path is not part of the accepted Stage-5 STAAD benchmark.",
                next_evidence=(
                    "Independent strip/plate or hand-calculation benchmark for transverse moments, "
                    "one-way shear and reinforcement selection."
                ),
            ),
            AcceptanceItem(
                key="ec2_rectangular_flexure_reference_case",
                title="Published EC2 rectangular flexure reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC Eurocodes Handbook 2 Annex-B rectangular bending example is reproduced: "
                    "the published A_s=933 mm2 for MEd=62.78 kNm is matched by the native "
                    "rectangular required-steel/resistance kernels within the benchmark tolerances."
                ),
                boundary=(
                    "This is independent supporting evidence for the basic rectangular "
                    "singly-reinforced flexure kernel only; it does not certify layered T/I "
                    "sections, reinforcement selection, ductility or the complete bridge design path."
                ),
                next_evidence=(
                    "Add independent T/I/layered flexure examples and the remaining "
                    "project/clause checks before promoting the broad flexure milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_msc_layered_flexure_design",
                title="Scoped MSc positive-bending layered flexure design",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "The production layered required-steel path applies the explicit EC2 design "
                    "lever-arm cap z<=0.95d and reproduces The Concrete Centre heavily loaded "
                    "L-beam span-AB reference: MEd=1148 kNm, d=668 mm, As,req≈4158 mm2 and "
                    "six H32 bars provide the published 4824 mm2 nominal reinforcement. The same "
                    "0.95d sizing basis is now used by the discrete reinforcement selector and its "
                    "refined effective-depth iterations, preventing under-provision after final design "
                    "recalculation. The 15 m research baseline uses a 400x950 mm rectangular precast "
                    "girder with the hardened participating deck forming the composite T-section."
                ),
                boundary=(
                    "This accepts the positive-bending simple-span MSc branch where the compression "
                    "block remains in the effective composite flange. It does not certify negative "
                    "bending, compression reinforcement or every possible web-compression regime."
                ),
                next_evidence=(
                    "Keep sampled MSc geometry/reinforcement inside this verified positive-bending "
                    "scope, or add an independent flange-to-web compression-block benchmark before "
                    "expanding the research input domain."
                ),
            ),
            AcceptanceItem(
                key="ec2_flexure_design",
                title="EN 1992 flexural resistance and reinforcement design",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Layered rectangular/T/I resistance kernels, required-steel solvers and internal "
                    "cross-kernel tests are implemented. Independent references now cover the basic "
                    "JRC rectangular kernel and the MSc positive-bending compression-block-in-flange "
                    "production path with the explicit 0.95d design lever-arm cap."
                ),
                boundary=(
                    "STAAD is being used as an analysis verifier, not as the authority for RC section design."
                ),
                next_evidence=(
                    "The four-target MSc positive-bending scope is accepted separately. Add independent "
                    "web-compression, negative-bending and other general T/I cases before the broad "
                    "standalone flexure milestone can be promoted."
                ),
            ),
            AcceptanceItem(
                key="ec2_concrete_shear_reference_case",
                title="Published EC2 concrete shear V_Rd,c reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC concrete-bridge slab example is reproduced for fck=35 MPa, "
                    "d=360 mm, Asl=1848 mm2 and bw=1000 mm: k≈1.75, rho_l≈0.51%, "
                    "v_min≈0.48 MPa and V_Rd,c≈198 kN/m."
                ),
                boundary=(
                    "This independently verifies the concrete-only V_Rd,c path. "
                    "It does not certify required/provided link design, V_Rd,s or V_Rd,max."
                ),
                next_evidence=(
                    "Add independent link-governed shear examples covering required A_sw/s, "
                    "provided-link resistance and V_Rd,max before promoting the broad shear milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_required_link_shear_reference_case",
                title="Published EC2 required-link shear reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "The Concrete Centre support-B example is reproduced for VEd=164.5 kN, "
                    "bw=300 mm, d=392 mm, fck=30 MPa, fyk=500 MPa and cot(theta)=2.5: "
                    "required Asw/s≈0.429 mm2/mm, minimum≈0.263 mm2/mm, maximum spacing "
                    "294 mm, and two-leg H8@200 provides≈0.503 mm2/mm versus published 0.50."
                ),
                boundary=(
                    "This independently verifies required links, minimum shear steel, link spacing "
                    "and the stated provided-link ratio. It deliberately does not certify V_Rd,max, "
                    "whose concrete-strut reduction convention remains a separate code-basis check."
                ),
                next_evidence=(
                    "Resolve and independently benchmark the EN 1992-2 V_Rd,max reduction-factor "
                    "basis before promoting the broad shear milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_provided_link_vrds_reference_case",
                title="Published EC2 provided-link V_Rd,s reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "European Concrete Platform Example 6.4 is reproduced for bw=150 mm, "
                    "d=550 mm, z=500 mm, Asw=226 mm2 at 150 mm, fyd≈391 MPa and "
                    "cot(theta)=1.29: native V_Rd,s≈380.27 kN versus published 380 kN."
                ),
                boundary=(
                    "This independently verifies the provided vertical-link V_Rd,s equation only. "
                    "The example's V_Rd,max/nu convention is intentionally not used to certify "
                    "the current bridge strut-capacity implementation."
                ),
                next_evidence=(
                    "Resolve and independently benchmark V_Rd,max with the intended EN 1992-2 "
                    "bridge convention."
                ),
            ),
            AcceptanceItem(
                key="ec2_vrdmax_reference_case",
                title="Published EC2 V_Rd,max concrete-strut reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "The Concrete Centre fck=30 MPa, cot(theta)=2.5 case is reproduced "
                    "with the JRC EN 1992-2 recommended nu1=0.6(1-fck/250)=0.528: "
                    "native v_Rd,max≈3.641 MPa versus published 3.64 MPa."
                ),
                boundary=(
                    "This verifies the recommended non-prestressed concrete-strut "
                    "V_Rd,max equation/factor basis used by deterministic v1."
                ),
                next_evidence="No further equation-level v1 evidence required for V_Rd,max.",
            ),
            AcceptanceItem(
                key="ec2_shear_design",
                title="EN 1992 shear resistance and link design",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "Independent published examples now cover V_Rd,c, required A_sw/s, "
                    "minimum links, maximum spacing, provided H8@200 reinforcement, "
                    "provided-link V_Rd,s and the recommended V_Rd,max concrete-strut basis."
                ),
                boundary=(
                    "The deterministic shear resistance/design equations are independently "
                    "benchmarked for the simple-span Eurocode research profile. Drawing-level "
                    "link zoning/curtailment remains part of the separate detailing milestone."
                ),
                next_evidence=(
                    "No further equation-level shear evidence is required for the MSc "
                    "simple-span profile; retain detailing/zoning under the detailing gate."
                ),
            ),
            AcceptanceItem(
                key="ec2_torsion_reinforcement_reference_case",
                title="Published EC2 torsion-reinforcement reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "European Concrete Platform Example 6.6 is reproduced for TEd=700 kNm, "
                    "Ak=1.08 m2, uk=4.30 m, fyk=500 MPa and cot(theta)=2.14: "
                    "native transverse Asw/s≈0.34830 mm2/mm versus published 0.348, "
                    "and longitudinal Asl≈6858.9 mm2 versus published 6855 mm2."
                ),
                boundary=(
                    "This verifies the torsion reinforcement equations for explicit verified "
                    "thin-wall properties Ak and uk; it does not infer those properties from "
                    "an arbitrary bridge girder."
                ),
                next_evidence=(
                    "Verify the project torsion-cell geometry input/derivation before "
                    "promoting the broad torsion milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_torsion_resistance_interaction_reference_case",
                title="Published EC2 torsion resistance/interaction reference case",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "European Concrete Platform Example 6.7 is reproduced for "
                    "Ak=83636 mm2, tef=94 mm, fcd=17 MPa, nu=0.616 and cot(theta)=2.0: "
                    "native T_Rd,max≈65.86 kNm versus published 66 kNm. The published "
                    "VEd=350 kN / TEd≈20 kNm point also lies on the native linear "
                    "V-T interaction boundary within rounding."
                ),
                boundary=(
                    "This verifies T_Rd,max and the high-stress linear shear-torsion "
                    "interaction for explicitly supplied equivalent-section geometry."
                ),
                next_evidence=(
                    "Verify the actual bridge torsion-cell Ak/uk/tef basis before "
                    "promoting the broad torsion milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_torsion_design",
                title="EN 1992 torsion resistance and shear-torsion interaction",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Native torsion demand is externally compared in Stage-5. Published European "
                    "Concrete Platform worked examples now independently reproduce the torsion "
                    "transverse/longitudinal reinforcement equations, T_Rd,max and V-T interaction."
                ),
                boundary=(
                    "The remaining broad-profile gap is not the torsion equations themselves: "
                    "Ak, uk and tef are intentionally explicit verified torsion-cell inputs. "
                    "The actual bridge/profile geometry used for research must therefore carry "
                    "a traceable torsion-cell basis before the broad milestone is promoted."
                ),
                next_evidence=(
                    "Close the actual simple-span bridge torsion-cell geometry basis "
                    "(Ak, uk, tef), or mark torsion not required for the research limit state."
                ),
            ),
            AcceptanceItem(
                key="ec2_crack_width_reference_case",
                title="Published EC2 crack-width transformed-section reference",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "European Concrete Platform Example 7.3 is reproduced with the "
                    "production layered-section kernel, including compression steel: "
                    "x=237.86 mm, I_II=5.957e9 mm4, sigma_s=234.29 MPa and "
                    "wk=0.18487 mm versus published 237.8 mm, 5.96e9 mm4, "
                    "234 MPa and 0.184 mm."
                ),
                boundary=(
                    "This verifies the EC2 direct crack-width/transformed-section mechanics. "
                    "The project's selected crack-width limit remains a project/NA input."
                ),
                next_evidence="No further equation benchmark required for the simple-span MSc crack path.",
            ),
            AcceptanceItem(
                key="ec2_crack_width",
                title="EN 1992 crack-width serviceability",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "Layered cracked-section, effective tension area, steel stress, sr,max and wk "
                    "kernels have internal rectangular/T-section equivalence tests. European "
                    "Concrete Platform Example 7.3 independently reproduces the transformed "
                    "neutral axis, cracked inertia, steel stress and final EC2 crack width."
                ),
                boundary=(
                    "The equation/mechanics gate is accepted for the simple-span research profile. "
                    "The allowable crack width remains an explicit project/National-Annex criterion."
                ),
                next_evidence="Simple-span MSc EC2 crack-width calculation gate closed.",
            ),
            AcceptanceItem(
                key="ec2_deflection_reference_case",
                title="Published EC2 spatial deflection reference",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "European Concrete Platform Example 7.6 is reproduced using the "
                    "production moment-diagram path: state-I deflection≈21.64 mm and "
                    "spatially varying cracked/uncracked deflection≈35.8 mm versus "
                    "published 21.64 mm and 35.71 mm."
                ),
                boundary=(
                    "This verifies the EC2 deformation calculation/interpolation mechanics. "
                    "It does not impose a universal road-bridge allowable deflection."
                ),
                next_evidence=(
                    "Use the client/project deformation criterion when a numerical "
                    "road-bridge acceptance limit is required."
                ),
            ),
            AcceptanceItem(
                key="ec2_deflection_serviceability",
                title="EN 1992 deflection serviceability",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=True,
                evidence=(
                    "Elastic structural displacement agrees with the genuine STAAD Stage-5 model. "
                    "The EC2 cracked/uncracked serviceability path now uses spatially varying "
                    "curvature interpolation along the actual co-located service moment diagram, "
                    "and reproduces European Concrete Platform Example 7.6."
                ),
                boundary=(
                    "The deformation calculation gate is accepted for the simple-span research "
                    "profile. EN 1990 Annex A2 does not impose one universal road-bridge "
                    "span/deflection ratio, so PASS/CHECK still requires an explicit project/client "
                    "criterion where such a limit is applicable."
                ),
                next_evidence="Simple-span MSc EC2 deflection-calculation gate closed.",
            ),
            AcceptanceItem(
                key="ec2_reinforcement_fatigue_reference_case",
                title="Published EN 1992-2 reinforcement-fatigue reference case",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC transverse-slab fatigue example is reproduced: "
                    "lambda_s=0.89 and Delta sigma_s,Ec=88 MPa give "
                    "Delta sigma_s,equ=78.32 MPa versus published 78 MPa; "
                    "162.5/1.15 gives 141.30 MPa versus published 141 MPa."
                ),
                boundary=(
                    "This independently verifies the equivalent-stress-range/resistance "
                    "equation only. FLM3 traffic placement, structural stress-range generation "
                    "and fatigue-specific transverse distribution are not certified by this case."
                ),
                next_evidence=(
                    "Add an independent FLM3 moving-vehicle stress-range benchmark for a "
                    "simple-span bridge/girder before promoting the broad fatigue milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_concrete_fatigue_reference_case",
                title="Published EN 1992-2 concrete-compression fatigue reference case",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC concrete-fatigue note is reproduced for fck=35 MPa, alpha_cc=0.85, "
                    "beta_cc(t0)=1.1..1.2: native fcd,fat=15.95..17.40 MPa matches the "
                    "published rounded 16..17.5 MPa range, and the cited 11.9/3.5 MPa "
                    "compression stresses fail Expression 6.77 at both endpoints as reported."
                ),
                boundary=(
                    "This independently verifies the concrete fatigue-strength/check equation "
                    "for the cited stresses only. Traffic-derived concrete stress histories remain "
                    "part of the unverified FLM3 structural-response path."
                ),
                next_evidence=(
                    "Verify the FLM3 structural stress history independently before promoting "
                    "the broad fatigue milestone."
                ),
            ),
            AcceptanceItem(
                key="flm3_longitudinal_search_reference_case",
                title="Independent FLM3 simple-span longitudinal search reference",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "The production FLM3 mover reproduces the independent 15 m simple-span "
                    "midspan influence-line result for the standard four 120 kN axle lines: "
                    "maximum positive moment and range are 936 kNm at unit longitudinal distribution."
                ),
                boundary=(
                    "This verifies the longitudinal vehicle movement/search only. Fatigue-specific "
                    "transverse distribution, section stress recovery and full stress histories remain "
                    "separate verification targets."
                ),
                next_evidence=(
                    "Use an independently checked fatigue-specific full-width distribution/stress-history "
                    "case before promoting the broad fatigue milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_fatigue",
                title="EN 1991-2 FLM3 / EN 1992 fatigue checks",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Native FLM3 moving-vehicle analysis and reinforcement/concrete fatigue kernels "
                    "have automated tests. Published JRC reinforcement/concrete fatigue equation "
                    "examples pass, and the 15 m longitudinal FLM3 mover independently reproduces "
                    "a 936 kNm midspan simple-span influence-line reference."
                ),
                boundary=(
                    "The longitudinal FLM3 search is now independently checked, but the accepted Stage-5 "
                    "LM1 benchmark is not an FLM3 fatigue campaign. Fatigue-specific transverse "
                    "distribution and the resulting girder stress histories are still unverified."
                ),
                next_evidence=(
                    "Retain the equation and longitudinal-movement references, then add an independent "
                    "fatigue-specific transverse distribution and girder stress-history benchmark."
                ),
            ),
            AcceptanceItem(
                key="ec2_link_spacing_reference_case",
                title="Published EC2 vertical-link spacing reference case",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.EXTERNALLY_ACCEPTED,
                v1_gate=False,
                evidence=(
                    "JRC Eurocode 2 Background and Applications Beam A2-B2-C2 case 1 "
                    "reports d=354 mm and s_l,max=s_t,max=0.75d=266 mm; the native "
                    "spacing kernel returns 265.5 mm and passes the published-rounding tolerance."
                ),
                boundary=(
                    "This independently supports the maximum vertical-link spacing formula only. "
                    "It does not certify minimum steel, link selection, anchorage, laps, cover, "
                    "curtailment, cage fit or drawing-level detailing."
                ),
                next_evidence=(
                    "Add independent benchmarks for the remaining detailing rules before "
                    "promoting the broad EC2 detailing milestone."
                ),
            ),
            AcceptanceItem(
                key="ec2_detailing",
                title="EN 1992 detailing, anchorage, laps and cage fit",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Discrete bar/link selection, anchorage/lap, cover, cage-fit and curtailment logic "
                    "have unit tests. One independent JRC vertical-link spacing reference case now "
                    "passes and is recorded separately."
                ),
                boundary="These drawing/detailing rules are outside STAAD structural-analysis verification.",
                next_evidence=(
                    "Retain the passing JRC link-spacing case as supporting evidence and complete "
                    "clause-by-clause independent checks for minimum steel, link selection, anchorage, "
                    "laps, cover, curtailment and cage/drawing rules."
                ),
            ),
            AcceptanceItem(
                key="midas_cross_verification",
                title="Second-solver MIDAS cross-verification",
                domain=AcceptanceDomain.PROFILE_SCOPE,
                state=AcceptanceState.DEFERRED_V2,
                v1_gate=False,
                evidence="MIDAS export/import support remains implemented but no genuine MIDAS run is required for v1.",
                boundary="Deferred by project decision; STAAD is the independent structural solver for v1.",
                next_evidence="Run the same acceptance workflow in MIDAS as a V2 cross-check.",
            ),
            AcceptanceItem(
                key="continuous_eurocode_profile",
                title="Continuous-span Eurocode solver profile",
                domain=AcceptanceDomain.PROFILE_SCOPE,
                state=AcceptanceState.OUT_OF_SCOPE,
                v1_gate=False,
                evidence="Continuous-span deterministic mechanics exist as a separate solver profile.",
                boundary="The accepted simple-span Stage-5 evidence cannot certify the continuous solver profile.",
                next_evidence="Separate independent verification campaign before unlocking that profile.",
            ),
            AcceptanceItem(
                key="bs5400_profile",
                title="BS 5400 / BD 37 solver profile",
                domain=AcceptanceDomain.PROFILE_SCOPE,
                state=AcceptanceState.OUT_OF_SCOPE,
                v1_gate=False,
                evidence="BS 5400 mechanics are isolated under their own solver profile and tests.",
                boundary="Eurocode Stage-5 evidence cannot certify BS 5400 calculations.",
                next_evidence="Separate independent BS 5400 verification programme.",
            ),
        ),
    )
