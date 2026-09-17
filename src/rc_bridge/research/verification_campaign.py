from __future__ import annotations

from dataclasses import dataclass, replace

from rc_bridge.export.external_results import (
    VerificationResultValue,
    parse_verification_results_csv,
)
from rc_bridge.research.benchmarking import (
    BenchmarkComparison,
    BenchmarkTarget,
    compare_benchmark_value,
)
from rc_bridge.research.verification import (
    DeterministicSolverVerification,
    SolverProfile,
)


@dataclass(frozen=True)
class BenchmarkTolerance:
    """Tolerance policy for one normalized result component."""

    relative_tolerance: float | None = None
    absolute_tolerance: float | None = None
    enforce_sign: bool = True
    sign_zero_threshold: float = 0.0

    def __post_init__(self) -> None:
        if self.relative_tolerance is None and self.absolute_tolerance is None:
            raise ValueError("Benchmark tolerance requires a relative or absolute tolerance.")
        if self.relative_tolerance is not None and self.relative_tolerance < 0.0:
            raise ValueError("Benchmark relative tolerance cannot be negative.")
        if self.absolute_tolerance is not None and self.absolute_tolerance < 0.0:
            raise ValueError("Benchmark absolute tolerance cannot be negative.")
        if self.sign_zero_threshold < 0.0:
            raise ValueError("Benchmark sign_zero_threshold cannot be negative.")


@dataclass(frozen=True)
class ExternalBenchmarkPolicy:
    """Explicit component-by-component numerical acceptance policy."""

    tolerances_by_component: dict[str, BenchmarkTolerance]
    require_exact_result_set: bool = True

    def __post_init__(self) -> None:
        if not self.tolerances_by_component:
            raise ValueError("External benchmark policy requires component tolerances.")
        if any(not component.strip() for component in self.tolerances_by_component):
            raise ValueError("Benchmark component names cannot be empty.")


@dataclass(frozen=True)
class BenchmarkCaseSpec:
    case_id: str
    solver_profile: SolverProfile
    required_components: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("Benchmark case_id cannot be empty.")
        if not self.required_components:
            raise ValueError("Benchmark case must require at least one result component.")
        if len(set(self.required_components)) != len(self.required_components):
            raise ValueError("Benchmark required_components cannot contain duplicates.")
        if any(not component.strip() for component in self.required_components):
            raise ValueError("Benchmark required component names cannot be empty.")


@dataclass(frozen=True)
class BenchmarkCaseReview:
    """Human/engineering review gates required in addition to numerical agreement."""

    geometry_equivalent: bool = False
    boundary_conditions_equivalent: bool = False
    loading_equivalent: bool = False
    result_axes_verified: bool = False

    @property
    def accepted(self) -> bool:
        return all(
            (
                self.geometry_equivalent,
                self.boundary_conditions_equivalent,
                self.loading_equivalent,
                self.result_axes_verified,
            )
        )

    def missing_checks(self) -> tuple[str, ...]:
        checks = {
            "geometry_equivalent": self.geometry_equivalent,
            "boundary_conditions_equivalent": self.boundary_conditions_equivalent,
            "loading_equivalent": self.loading_equivalent,
            "result_axes_verified": self.result_axes_verified,
        }
        return tuple(name for name, complete in checks.items() if not complete)


@dataclass(frozen=True)
class BenchmarkValueAssessment:
    internal: VerificationResultValue
    external: VerificationResultValue
    comparison: BenchmarkComparison
    sign_matches: bool

    @property
    def passes(self) -> bool:
        return self.comparison.passes and self.sign_matches


@dataclass(frozen=True)
class ExternalBenchmarkCaseReport:
    spec: BenchmarkCaseSpec
    source_name: str
    source_reference: str
    assessments: tuple[BenchmarkValueAssessment, ...]
    missing_external_keys: tuple[str, ...]
    extra_external_keys: tuple[str, ...]
    missing_required_components: tuple[str, ...]
    review: BenchmarkCaseReview
    require_exact_result_set: bool

    @property
    def numerical_passes(self) -> bool:
        result_set_ok = (
            not self.require_exact_result_set
            or (not self.missing_external_keys and not self.extra_external_keys)
        )
        return (
            result_set_ok
            and not self.missing_required_components
            and bool(self.assessments)
            and all(item.passes for item in self.assessments)
        )

    @property
    def accepted_evidence(self) -> bool:
        return self.numerical_passes and self.review.accepted

    @property
    def failed_result_keys(self) -> tuple[str, ...]:
        return tuple(
            _display_key(item.internal.key)
            for item in self.assessments
            if not item.passes
        )


@dataclass(frozen=True)
class VerificationCampaignSpec:
    name: str
    solver_profile: SolverProfile
    required_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Verification campaign name cannot be empty.")
        if not self.required_case_ids:
            raise ValueError("Verification campaign requires at least one benchmark case.")
        if len(set(self.required_case_ids)) != len(self.required_case_ids):
            raise ValueError("Verification campaign required_case_ids cannot contain duplicates.")


@dataclass(frozen=True)
class VerificationCampaignReport:
    spec: VerificationCampaignSpec
    case_reports: tuple[ExternalBenchmarkCaseReport, ...]
    missing_case_ids: tuple[str, ...]
    unexpected_case_ids: tuple[str, ...]
    profile_mismatch_case_ids: tuple[str, ...]

    @property
    def passes(self) -> bool:
        required = set(self.spec.required_case_ids)
        required_reports = tuple(
            report for report in self.case_reports if report.spec.case_id in required
        )
        return (
            not self.missing_case_ids
            and not self.profile_mismatch_case_ids
            and len(required_reports) == len(required)
            and all(report.accepted_evidence for report in required_reports)
        )

    @property
    def failed_case_ids(self) -> tuple[str, ...]:
        required = set(self.spec.required_case_ids)
        failed = {
            report.spec.case_id
            for report in self.case_reports
            if report.spec.case_id in required and not report.accepted_evidence
        }
        failed.update(self.missing_case_ids)
        failed.update(self.profile_mismatch_case_ids)
        return tuple(sorted(failed))


def _display_key(key: tuple[str, str, str, str, str, str]) -> str:
    result_type, object_id, span_index, position_m, component, unit = key
    return (
        f"{result_type}|object={object_id}|span={span_index}|position={position_m}|"
        f"{component}|{unit}"
    )


def _sign_matches(
    internal_value: float,
    external_value: float,
    tolerance: BenchmarkTolerance,
) -> bool:
    if not tolerance.enforce_sign:
        return True
    threshold = tolerance.sign_zero_threshold
    if abs(internal_value) <= threshold or abs(external_value) <= threshold:
        return True
    return internal_value * external_value > 0.0


def evaluate_external_benchmark_case(
    spec: BenchmarkCaseSpec,
    *,
    internal_results_csv: str,
    external_results_csv: str,
    source_name: str,
    policy: ExternalBenchmarkPolicy,
    review: BenchmarkCaseReview,
    source_reference: str = "",
) -> ExternalBenchmarkCaseReport:
    """Evaluate one independent-software benchmark case.

    Numerical comparison is component-specific and sign-aware. Engineering review
    remains a separate gate so a numerically close result cannot count as evidence
    when the compared models, loading or result axes are not confirmed equivalent.
    """
    if not source_name.strip():
        raise ValueError("External benchmark source_name cannot be empty.")

    internal = parse_verification_results_csv(internal_results_csv)
    external = parse_verification_results_csv(external_results_csv)
    internal_map = {item.key: item for item in internal}
    external_map = {item.key: item for item in external}

    internal_components = {item.component for item in internal}
    missing_required = tuple(
        component for component in spec.required_components if component not in internal_components
    )

    required_policy_components = {
        item.component for item in internal if item.key in external_map
    }
    missing_policy = sorted(
        required_policy_components - set(policy.tolerances_by_component)
    )
    if missing_policy:
        raise ValueError(
            "External benchmark policy is missing tolerances for components: "
            + ", ".join(missing_policy)
        )

    missing_external = tuple(
        _display_key(key) for key in sorted(internal_map.keys() - external_map.keys())
    )
    extra_external = tuple(
        _display_key(key) for key in sorted(external_map.keys() - internal_map.keys())
    )

    assessments: list[BenchmarkValueAssessment] = []
    for key in sorted(internal_map.keys() & external_map.keys()):
        internal_value = internal_map[key]
        external_value = external_map[key]
        tolerance = policy.tolerances_by_component[internal_value.component]
        target = BenchmarkTarget(
            name=_display_key(key),
            reference_value=external_value.value,
            unit=external_value.unit,
            relative_tolerance=tolerance.relative_tolerance,
            absolute_tolerance=tolerance.absolute_tolerance,
            location=(
                f"object {external_value.object_id}; span {external_value.span_index}; "
                f"position {external_value.position_m}"
            ),
        )
        comparison = compare_benchmark_value(
            target,
            calculated_value=internal_value.value,
        )
        assessments.append(
            BenchmarkValueAssessment(
                internal=internal_value,
                external=external_value,
                comparison=comparison,
                sign_matches=_sign_matches(
                    internal_value.value,
                    external_value.value,
                    tolerance,
                ),
            )
        )

    return ExternalBenchmarkCaseReport(
        spec=spec,
        source_name=source_name,
        source_reference=source_reference,
        assessments=tuple(assessments),
        missing_external_keys=missing_external,
        extra_external_keys=extra_external,
        missing_required_components=missing_required,
        review=review,
        require_exact_result_set=policy.require_exact_result_set,
    )


def evaluate_verification_campaign(
    spec: VerificationCampaignSpec,
    case_reports: tuple[ExternalBenchmarkCaseReport, ...],
) -> VerificationCampaignReport:
    """Aggregate benchmark evidence without changing deterministic verification state."""
    case_ids = [report.spec.case_id for report in case_reports]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("Verification campaign case reports contain duplicate case IDs.")

    required = set(spec.required_case_ids)
    supplied = set(case_ids)
    missing = tuple(sorted(required - supplied))
    unexpected = tuple(sorted(supplied - required))
    profile_mismatches = tuple(
        sorted(
            report.spec.case_id
            for report in case_reports
            if report.spec.case_id in required
            and report.spec.solver_profile != spec.solver_profile
        )
    )
    return VerificationCampaignReport(
        spec=spec,
        case_reports=case_reports,
        missing_case_ids=missing,
        unexpected_case_ids=unexpected,
        profile_mismatch_case_ids=profile_mismatches,
    )


def apply_independent_benchmark_campaign(
    verification: DeterministicSolverVerification,
    campaign: VerificationCampaignReport,
) -> DeterministicSolverVerification:
    """Promote only the independent-benchmark milestone after an accepted campaign.

    This function deliberately does not mark traffic, transverse distribution or
    any other verification milestone complete. Those remain separate evidence gates.
    """
    if verification.solver_profile != campaign.spec.solver_profile:
        raise RuntimeError(
            "Verification campaign solver profile does not match deterministic solver profile."
        )
    if not campaign.passes:
        failed = ", ".join(campaign.failed_case_ids) or "campaign requirements"
        raise RuntimeError(
            "Independent benchmark milestone remains locked. Failed or missing cases: " + failed
        )
    return replace(verification, independent_benchmark=True)
