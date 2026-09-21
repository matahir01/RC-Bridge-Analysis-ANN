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
                key="lm1_code_loading",
                title="EN 1991-2 LM1 load-generation rules",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Native lane, remaining-area, tandem and placement generation has extensive "
                    "automated mechanics/traceability tests and is exported identically to STAAD."
                ),
                boundary=(
                    "STAAD consumes the application's generated LM1 actions; matching results therefore "
                    "cannot independently establish that the EN 1991-2 loading interpretation is correct."
                ),
                next_evidence=(
                    "Clause-by-clause LM1 benchmark against independently checked hand calculations "
                    "or a trusted worked example, including lane widths, UDLs, tandems and placement."
                ),
            ),
            AcceptanceItem(
                key="en1990_combination_rules",
                title="EN 1990 / bridge traffic combination rules",
                domain=AcceptanceDomain.CODE_LOADING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Stage-5 exports 141 ULS/SLS combinations and STAAD reproduces their structural "
                    "response with the same governing combination identity."
                ),
                boundary=(
                    "The external solver verifies application of supplied factors, not whether the "
                    "selected EN 1990 groups, gamma values and psi factors are clause-correct."
                ),
                next_evidence=(
                    "Independent clause matrix/worked examples for gr1a, gr1b, gr2, gr3, wind, "
                    "characteristic, frequent and quasi-permanent combinations."
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
                key="ec2_flexure_design",
                title="EN 1992 flexural resistance and reinforcement design",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Layered rectangular/T/I resistance kernels, required-steel solvers and internal "
                    "cross-kernel tests are implemented."
                ),
                boundary=(
                    "STAAD is being used as an analysis verifier, not as the authority for RC section design."
                ),
                next_evidence=(
                    "Independent hand/worked-example checks for required As, compression block, lever arm, "
                    "MRd and reinforcement selection for rectangular, T and I physical profiles."
                ),
            ),
            AcceptanceItem(
                key="ec2_shear_design",
                title="EN 1992 shear resistance and link design",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Concrete VRd,c, required links, provided-link VRd,s/VRd,max and detailing limits are tested."
                ),
                boundary="Stage-5 member shear agreement does not validate the EC2 shear-resistance equations.",
                next_evidence=(
                    "Independent EC2 worked examples covering concrete-only and link-governed shear cases."
                ),
            ),
            AcceptanceItem(
                key="ec2_torsion_design",
                title="EN 1992 torsion resistance and shear-torsion interaction",
                domain=AcceptanceDomain.DESIGN_RESISTANCE,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Native torsion demand is externally compared in Stage-5 and EC2 torsion kernels have "
                    "deterministic unit tests."
                ),
                boundary=(
                    "External agreement of member torsional actions does not independently validate TRd,max, "
                    "torsion reinforcement or the shear-torsion interaction design equations."
                ),
                next_evidence="Independent EC2 torsion worked-example verification.",
            ),
            AcceptanceItem(
                key="ec2_crack_width",
                title="EN 1992 crack-width serviceability",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Layered cracked-section, effective tension area, steel stress, sr,max and wk kernels are tested."
                ),
                boundary="A structural solver force comparison cannot independently validate EC2 crack-width equations.",
                next_evidence="Independent crack-width worked examples for representative rectangular/T/I sections.",
            ),
            AcceptanceItem(
                key="ec2_deflection_serviceability",
                title="EN 1992 deflection serviceability",
                domain=AcceptanceDomain.SERVICEABILITY,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Elastic load-pattern/curvature mechanics have closed-form tests and Stage-5 DZ agrees with STAAD; "
                    "the application also implements cracked/uncracked EC2 interpolation."
                ),
                boundary=(
                    "STAAD validates the elastic structural response only, not EC2 cracking, effective modulus, "
                    "creep assumptions or tension-stiffening interpolation used for the design check."
                ),
                next_evidence=(
                    "Independent EC2 deflection worked examples including cracked state, creep/effective modulus "
                    "and interpolation."
                ),
            ),
            AcceptanceItem(
                key="ec2_fatigue",
                title="EN 1991-2 FLM3 / EN 1992 fatigue checks",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Native FLM3 moving-vehicle analysis and reinforcement/concrete fatigue kernels have automated tests."
                ),
                boundary="The accepted Stage-5 LM1 benchmark is not an FLM3 fatigue verification campaign.",
                next_evidence="Independent FLM3 stress-range and EN 1992 fatigue worked-example benchmark.",
            ),
            AcceptanceItem(
                key="ec2_detailing",
                title="EN 1992 detailing, anchorage, laps and cage fit",
                domain=AcceptanceDomain.FATIGUE_DETAILING,
                state=AcceptanceState.INTERNAL_ONLY,
                v1_gate=True,
                evidence=(
                    "Discrete bar/link selection, anchorage/lap, cover, cage-fit and curtailment logic have unit tests."
                ),
                boundary="These drawing/detailing rules are outside STAAD structural-analysis verification.",
                next_evidence=(
                    "Clause-by-clause detailing review and independently checked example drawings/calculations."
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
