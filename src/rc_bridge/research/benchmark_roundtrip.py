from __future__ import annotations

from rc_bridge.export.line_benchmark_results import (
    normalize_midas_line_benchmark_tables,
    parse_staad_line_benchmark_results,
)
from rc_bridge.research.line_benchmark import (
    ContinuousLineBenchmarkPackage,
    default_continuous_line_campaign_spec,
)
from rc_bridge.research.verification_campaign import (
    BenchmarkCaseReview,
    ExternalBenchmarkCaseReport,
    ExternalBenchmarkPolicy,
    VerificationCampaignReport,
    VerificationCampaignSpec,
    evaluate_external_benchmark_case,
    evaluate_verification_campaign,
)


def evaluate_staad_line_benchmark(
    package: ContinuousLineBenchmarkPackage,
    *,
    anl_text: str,
    policy: ExternalBenchmarkPolicy,
    review: BenchmarkCaseReview,
    load_case_id: int | None = None,
    source_reference: str = "",
) -> ExternalBenchmarkCaseReport:
    """Parse one real STAAD ``.ANL`` file and evaluate it against internal results."""
    external = parse_staad_line_benchmark_results(
        anl_text,
        package.verification_model,
        load_case_id=load_case_id,
    )
    return evaluate_external_benchmark_case(
        package.case_spec,
        internal_results_csv=package.external_expected_results_csv,
        external_results_csv=external,
        source_name="STAAD.Pro",
        source_reference=source_reference,
        policy=policy,
        review=review,
    )


def evaluate_midas_line_benchmark(
    package: ContinuousLineBenchmarkPackage,
    *,
    reaction_table: str,
    displacement_table: str,
    policy: ExternalBenchmarkPolicy,
    review: BenchmarkCaseReview,
    load_case: str | None = None,
    delimiter: str = ",",
    source_reference: str = "",
) -> ExternalBenchmarkCaseReport:
    """Normalize MIDAS global tables and evaluate them against internal line results."""
    case_name = load_case
    if case_name is None and len(package.verification_model.load_cases) == 1:
        case_name = package.verification_model.load_cases[0].name
    external = normalize_midas_line_benchmark_tables(
        reaction_table=reaction_table,
        displacement_table=displacement_table,
        load_case=case_name,
        delimiter=delimiter,
    )
    return evaluate_external_benchmark_case(
        package.case_spec,
        internal_results_csv=package.external_expected_results_csv,
        external_results_csv=external,
        source_name="MIDAS Civil",
        source_reference=source_reference,
        policy=policy,
        review=review,
    )


def evaluate_continuous_line_campaign(
    case_reports: tuple[ExternalBenchmarkCaseReport, ...],
    *,
    campaign_spec: VerificationCampaignSpec | None = None,
) -> VerificationCampaignReport:
    """Aggregate all controlled line benchmark reports into one campaign result."""
    return evaluate_verification_campaign(
        campaign_spec or default_continuous_line_campaign_spec(),
        case_reports,
    )
