import pytest

from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)
from rc_bridge.research.verification_campaign import (
    BenchmarkCaseReview,
    BenchmarkCaseSpec,
    BenchmarkTolerance,
    ExternalBenchmarkPolicy,
    VerificationCampaignSpec,
    apply_independent_benchmark_campaign,
    evaluate_external_benchmark_case,
    evaluate_verification_campaign,
)

_HEADER = "result_type,object_id,span_index,position_m,component,value,unit\n"
_INTERNAL = (
    _HEADER
    + "support_reaction,1,,,FZ,100,kN\n"
    + "node_displacement,2,,,DZ,-0.012,m\n"
    + "member_end_force,10,,I,V_VERTICAL,42,kN\n"
    + "member_end_force,10,,I,M_VERTICAL,-180,kNm\n"
    + "member_end_force,10,,I,T,12,kNm\n"
)


def _policy(*, moment_relative: float = 0.02) -> ExternalBenchmarkPolicy:
    return ExternalBenchmarkPolicy(
        tolerances_by_component={
            "FZ": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=0.1),
            "DZ": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=1.0e-5),
            "V_VERTICAL": BenchmarkTolerance(
                relative_tolerance=0.02,
                absolute_tolerance=0.1,
            ),
            "M_VERTICAL": BenchmarkTolerance(
                relative_tolerance=moment_relative,
                absolute_tolerance=0.1,
            ),
            "T": BenchmarkTolerance(relative_tolerance=0.02, absolute_tolerance=0.1),
        }
    )


def _spec(case_id: str = "grillage-eccentric") -> BenchmarkCaseSpec:
    return BenchmarkCaseSpec(
        case_id=case_id,
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        required_components=("FZ", "DZ", "V_VERTICAL", "M_VERTICAL", "T"),
    )


def _accepted_review() -> BenchmarkCaseReview:
    return BenchmarkCaseReview(
        geometry_equivalent=True,
        boundary_conditions_equivalent=True,
        loading_equivalent=True,
        result_axes_verified=True,
    )


def test_external_benchmark_case_requires_numerical_and_engineering_acceptance() -> None:
    external = _INTERNAL.replace("-180,kNm", "-181,kNm")
    report = evaluate_external_benchmark_case(
        _spec(),
        internal_results_csv=_INTERNAL,
        external_results_csv=external,
        source_name="MIDAS Civil",
        source_reference="eccentric-LM1-snapshot",
        policy=_policy(),
        review=_accepted_review(),
    )

    assert report.numerical_passes is True
    assert report.review.accepted is True
    assert report.accepted_evidence is True
    assert report.failed_result_keys == ()


def test_sign_inversion_fails_even_when_large_numeric_tolerance_would_allow_it() -> None:
    external = _INTERNAL.replace("-180,kNm", "180,kNm")
    report = evaluate_external_benchmark_case(
        _spec(),
        internal_results_csv=_INTERNAL,
        external_results_csv=external,
        source_name="STAAD.Pro",
        policy=_policy(moment_relative=3.0),
        review=_accepted_review(),
    )

    assessment = next(
        item for item in report.assessments if item.internal.component == "M_VERTICAL"
    )
    assert assessment.comparison.passes is True
    assert assessment.sign_matches is False
    assert assessment.passes is False
    assert report.numerical_passes is False
    assert report.accepted_evidence is False


def test_missing_external_row_blocks_exact_benchmark_case() -> None:
    external = _INTERNAL.replace("member_end_force,10,,I,T,12,kNm\n", "")
    report = evaluate_external_benchmark_case(
        _spec(),
        internal_results_csv=_INTERNAL,
        external_results_csv=external,
        source_name="MIDAS Civil",
        policy=_policy(),
        review=_accepted_review(),
    )

    assert len(report.missing_external_keys) == 1
    assert report.numerical_passes is False
    assert report.accepted_evidence is False


def test_incomplete_model_review_blocks_numerically_passing_case() -> None:
    report = evaluate_external_benchmark_case(
        _spec(),
        internal_results_csv=_INTERNAL,
        external_results_csv=_INTERNAL,
        source_name="STAAD.Pro",
        policy=_policy(),
        review=BenchmarkCaseReview(
            geometry_equivalent=True,
            boundary_conditions_equivalent=True,
            loading_equivalent=True,
            result_axes_verified=False,
        ),
    )

    assert report.numerical_passes is True
    assert report.review.missing_checks() == ("result_axes_verified",)
    assert report.accepted_evidence is False


def test_campaign_requires_every_named_case_before_it_passes() -> None:
    one_case = evaluate_external_benchmark_case(
        _spec("simple-udl"),
        internal_results_csv=_INTERNAL,
        external_results_csv=_INTERNAL,
        source_name="STAAD.Pro",
        policy=_policy(),
        review=_accepted_review(),
    )
    campaign = evaluate_verification_campaign(
        VerificationCampaignSpec(
            name="continuous Eurocode external benchmarks",
            solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
            required_case_ids=("simple-udl", "grillage-eccentric"),
        ),
        (one_case,),
    )

    assert campaign.passes is False
    assert campaign.missing_case_ids == ("grillage-eccentric",)
    assert campaign.failed_case_ids == ("grillage-eccentric",)


def test_accepted_campaign_promotes_only_independent_benchmark_milestone() -> None:
    case_a = evaluate_external_benchmark_case(
        _spec("simple-udl"),
        internal_results_csv=_INTERNAL,
        external_results_csv=_INTERNAL,
        source_name="STAAD.Pro",
        policy=_policy(),
        review=_accepted_review(),
    )
    case_b = evaluate_external_benchmark_case(
        _spec("grillage-eccentric"),
        internal_results_csv=_INTERNAL,
        external_results_csv=_INTERNAL,
        source_name="MIDAS Civil",
        policy=_policy(),
        review=_accepted_review(),
    )
    campaign = evaluate_verification_campaign(
        VerificationCampaignSpec(
            name="continuous Eurocode external benchmarks",
            solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
            required_case_ids=("simple-udl", "grillage-eccentric"),
        ),
        (case_a, case_b),
    )
    verification = DeterministicSolverVerification(
        solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
        traffic_loading=True,
        deflection=True,
    )

    updated = apply_independent_benchmark_campaign(verification, campaign)

    assert campaign.passes is True
    assert updated.independent_benchmark is True
    assert updated.traffic_loading is True
    assert updated.deflection is True
    assert updated.transverse_distribution is False
    assert updated.flexure is False
    assert updated.ann_ready is False


def test_failed_campaign_cannot_promote_independent_benchmark() -> None:
    case = evaluate_external_benchmark_case(
        _spec("simple-udl"),
        internal_results_csv=_INTERNAL,
        external_results_csv=_INTERNAL,
        source_name="STAAD.Pro",
        policy=_policy(),
        review=_accepted_review(),
    )
    campaign = evaluate_verification_campaign(
        VerificationCampaignSpec(
            name="incomplete campaign",
            solver_profile=SolverProfile.EUROCODE_CONTINUOUS,
            required_case_ids=("simple-udl", "missing-case"),
        ),
        (case,),
    )

    with pytest.raises(RuntimeError, match="Independent benchmark milestone remains locked"):
        apply_independent_benchmark_campaign(
            DeterministicSolverVerification(
                solver_profile=SolverProfile.EUROCODE_CONTINUOUS
            ),
            campaign,
        )
