from rc_bridge.research.acceptance_matrix import (
    AcceptanceDomain,
    AcceptanceState,
    eurocode_simple_span_v1_acceptance_matrix,
)
from rc_bridge.research.verification import SolverProfile, VerificationScope


def test_v1_acceptance_matrix_separates_structural_analysis_from_design_code() -> None:
    matrix = eurocode_simple_span_v1_acceptance_matrix()

    assert matrix.solver_profile is SolverProfile.EUROCODE_1G
    assert matrix.item("stage5_model_equivalence").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("stage5_structural_response").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert (
        matrix.item("grillage_transverse_distribution").state
        is AcceptanceState.EXTERNALLY_ACCEPTED
    )
    assert (
        matrix.item("elastic_displacement_response").state
        is AcceptanceState.EXTERNALLY_ACCEPTED
    )

    assert matrix.item("lm1_code_loading").domain is AcceptanceDomain.CODE_LOADING
    assert matrix.item("lm1_code_loading").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("en1990_combination_rules").state is AcceptanceState.INTERNAL_ONLY

    for key in (
        "lm1_characteristic_values_reference_case",
        "lm1_lane_subdivision_reference_case",
        "lm1_transverse_distribution_reference_case",
        "lm1_longitudinal_search_reference_case",
        "en1990_lm1_research_combination_core",
        "road_bridge_combination_factors_reference_case",
        "ec2_concrete_shear_reference_case",
        "ec2_required_link_shear_reference_case",
        "ec2_provided_link_vrds_reference_case",
        "ec2_vrdmax_reference_case",
        "ec2_torsion_reinforcement_reference_case",
        "ec2_torsion_resistance_interaction_reference_case",
        "ec2_reinforcement_fatigue_reference_case",
        "ec2_concrete_fatigue_reference_case",
        "ec2_crack_width_reference_case",
        "ec2_deflection_reference_case",
        "ec2_msc_layered_flexure_design",
        "flm3_longitudinal_search_reference_case",
    ):
        assert matrix.item(key).state is AcceptanceState.EXTERNALLY_ACCEPTED
        assert key not in matrix.pending_v1_gate_keys

    assert (
        matrix.item("ec2_rectangular_flexure_reference_case").state
        is AcceptanceState.EXTERNALLY_ACCEPTED
    )
    assert (
        matrix.item("ec2_link_spacing_reference_case").state
        is AcceptanceState.EXTERNALLY_ACCEPTED
    )
    assert "ec2_rectangular_flexure_reference_case" not in matrix.pending_v1_gate_keys
    assert "ec2_link_spacing_reference_case" not in matrix.pending_v1_gate_keys

    assert matrix.item("ec2_shear_design").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert "ec2_shear_design" not in matrix.pending_v1_gate_keys

    for key in (
        "ec2_flexure_design",
        "ec2_torsion_design",
        "ec2_fatigue",
        "ec2_detailing",
    ):
        assert matrix.item(key).state is AcceptanceState.INTERNAL_ONLY
        assert key in matrix.pending_v1_gate_keys

    assert matrix.item("midas_cross_verification").state is AcceptanceState.DEFERRED_V2
    assert "midas_cross_verification" not in matrix.pending_v1_gate_keys


def test_staad_acceptance_does_not_unlock_unverified_design_milestones() -> None:
    matrix = eurocode_simple_span_v1_acceptance_matrix()
    verification = matrix.research_verification_manifest(torsion_required=True)

    assert verification.solver_profile is SolverProfile.EUROCODE_1G
    assert verification.independent_benchmark is True
    assert verification.transverse_distribution is True

    assert verification.traffic_loading is True
    assert verification.load_combinations is False
    # Passing sub-component reference cases are supporting evidence only.
    assert matrix.item("lm1_characteristic_values_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("lm1_lane_subdivision_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("lm1_transverse_distribution_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("lm1_longitudinal_search_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("en1990_lm1_research_combination_core").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("road_bridge_combination_factors_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_concrete_shear_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_required_link_shear_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_provided_link_vrds_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_vrdmax_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_torsion_reinforcement_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_torsion_resistance_interaction_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_reinforcement_fatigue_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_concrete_fatigue_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_crack_width_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_deflection_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_crack_width").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_deflection_serviceability").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_rectangular_flexure_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert matrix.item("ec2_link_spacing_reference_case").state is AcceptanceState.EXTERNALLY_ACCEPTED
    assert verification.traffic_loading is True
    assert verification.load_combinations is False
    assert verification.flexure is False
    assert verification.shear is True
    assert verification.cracking is True
    assert verification.deflection is True
    assert verification.fatigue is False
    assert verification.detailing is False
    assert verification.torsion_required is True
    assert verification.torsion is False
    assert verification.ann_ready is False



def test_msc_manifest_is_ready_only_for_explicit_four_target_scope() -> None:
    matrix = eurocode_simple_span_v1_acceptance_matrix()
    msc = matrix.msc_research_verification_manifest()

    assert msc.solver_profile is SolverProfile.EUROCODE_1G
    assert msc.traffic_loading is True
    assert msc.load_combinations is True
    assert msc.flexure is True
    assert msc.shear is True
    assert msc.cracking is True
    assert msc.deflection is True
    assert msc.transverse_distribution is True
    assert msc.independent_benchmark is True

    # These remain outside the current four ANN targets and do not become
    # generally accepted just because the MSc profile is narrower.
    assert msc.fatigue is False
    assert msc.detailing is False
    assert msc.torsion_required is False
    assert msc.torsion is False
    assert msc.ann_ready is False
    assert msc.ready_for(VerificationScope.MSC_SIMPLE_SPAN_ANN) is True
    assert msc.missing_requirements_for(VerificationScope.MSC_SIMPLE_SPAN_ANN) == ()

    general = matrix.research_verification_manifest(torsion_required=True)
    assert general.ann_ready is False
    assert general.flexure is False
    assert general.load_combinations is False
    assert general.fatigue is False
    assert general.detailing is False
    assert general.torsion is False


def test_v1_matrix_keeps_stage_specific_and_local_deck_checks_pending() -> None:
    matrix = eurocode_simple_span_v1_acceptance_matrix()

    assert matrix.item("construction_stage_response").state is AcceptanceState.PENDING_INDEPENDENT_CHECK
    assert matrix.item("local_deck_analysis").state is AcceptanceState.PENDING_INDEPENDENT_CHECK
    assert matrix.structural_analysis_accepted is False
    assert matrix.full_v1_profile_accepted is False


def test_v1_matrix_serialization_is_machine_readable() -> None:
    matrix = eurocode_simple_span_v1_acceptance_matrix()
    payload = matrix.as_dict()

    assert payload["solver_profile"] == SolverProfile.EUROCODE_1G.value
    assert payload["full_v1_profile_accepted"] is False
    assert "ec2_flexure_design" in payload["pending_v1_gate_keys"]
    assert payload["deferred_v2_keys"] == ["midas_cross_verification"]
    item = next(
        row for row in payload["items"] if row["key"] == "stage5_structural_response"
    )
    assert item["state"] == AcceptanceState.EXTERNALLY_ACCEPTED.value
    assert item["domain"] == AcceptanceDomain.STRUCTURAL_ANALYSIS.value
