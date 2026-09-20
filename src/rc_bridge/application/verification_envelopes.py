from __future__ import annotations

import json
from dataclasses import dataclass, replace

from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
)
from rc_bridge.application.verification_results import VerificationResultDatabase
from rc_bridge.application.verification_tolerance import VerificationImportTolerance
from rc_bridge.export.verification_model import VerificationModel
from rc_bridge.workflow.lm1_grillage_search import ProjectNativeLM1GrillageSearchResult


@dataclass(frozen=True)
class EnvelopeComparisonItem:
    girder_index: int
    quantity: str
    source_case_id: int
    stage5_case_id: int
    native_value: float
    external_value: float
    unit: str
    relative_difference: float | None
    absolute_difference: float
    allowable_absolute_difference: float
    passes: bool
    note: str = ""


@dataclass(frozen=True)
class PermanentEquilibriumComparison:
    stage5_case_id: int
    native_total_reaction_kn: float
    external_total_reaction_kn: float
    relative_difference: float | None
    absolute_difference: float
    allowable_absolute_difference: float
    passes: bool


@dataclass(frozen=True)
class StaadEnvelopeComparisonReport:
    source_name: str
    relative_tolerance: float
    permanent_equilibrium: PermanentEquilibriumComparison | None
    items: tuple[EnvelopeComparisonItem, ...]

    @property
    def passes(self) -> bool:
        equilibrium_passes = (
            True
            if self.permanent_equilibrium is None
            else self.permanent_equilibrium.passes
        )
        return equilibrium_passes and bool(self.items) and all(item.passes for item in self.items)

    @property
    def maximum_relative_difference(self) -> float | None:
        values = [
            abs(item.relative_difference)
            for item in self.items
            if item.relative_difference is not None
        ]
        if self.permanent_equilibrium is not None:
            value = self.permanent_equilibrium.relative_difference
            if value is not None:
                values.append(abs(value))
        return max(values) if values else None


def _relative_difference(reference: float, comparison: float) -> float | None:
    scale = abs(reference)
    if scale <= 1.0e-12:
        return None
    return (comparison - reference) / scale


def _stage5_case_identity(
    model: VerificationModel,
) -> tuple[dict[str, object], ...]:
    raw = model.metadata.get("case_identity", "")
    if not raw:
        raise ValueError(
            "Stage-5 model does not contain case_identity metadata required for "
            "source-case envelope comparison."
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Stage-5 case_identity metadata is invalid JSON.") from exc
    if not isinstance(payload, list):
        raise TypeError("Stage-5 case_identity metadata must be a list.")
    return tuple(item for item in payload if isinstance(item, dict))


def _stage5_case_id_for_source(
    identities: tuple[dict[str, object], ...],
    *,
    group: str,
    source_case_id: int,
) -> int:
    matches = [
        int(item["stage5_case_id"])
        for item in identities
        if item.get("group") == group
        and int(item.get("source_case_id", -1)) == int(source_case_id)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one Stage-5 {group!r} case for source case "
            f"{source_case_id}, found {len(matches)}."
        )
    return matches[0]


def _longitudinal_member_ids(
    model: VerificationModel,
    *,
    y_m: float,
    tolerance_m: float = 1.0e-9,
) -> set[int]:
    nodes = {node.node_id: node for node in model.nodes}
    ids: set[int] = set()
    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(ni.y_m - y_m) <= tolerance_m
            and abs(nj.y_m - y_m) <= tolerance_m
            and abs(nj.x_m - ni.x_m) > tolerance_m
        ):
            ids.add(beam.member_id)
    if not ids:
        raise ValueError(
            f"Stage-5 model has no longitudinal members on girder line y={y_m:.6g} m."
        )
    return ids


def compare_staad_lm1_envelopes(
    model: VerificationModel,
    lm1: ProjectNativeLM1GrillageSearchResult,
    *,
    external_results: VerificationResultDatabase,
    tolerance: VerificationImportTolerance | None = None,
    source_name: str = "STAAD.Pro",
) -> StaadEnvelopeComparisonReport:
    """Compare native governing LM1 envelopes with an already-parsed external database.

    The ANL/table source is parsed exactly once upstream. Governing source cases are
    mapped to exported Stage-5 result IDs and queried from the indexed result database.
    The same relative-plus-absolute tolerance policy used by detailed verification
    comparisons governs envelope acceptance, including near-zero quantities.
    """

    policy = tolerance or VerificationImportTolerance()
    identities = _stage5_case_identity(model)

    items: list[EnvelopeComparisonItem] = []
    deflections = {item.girder_index: item for item in lm1.deflections}

    for girder in lm1.girders:
        member_ids = _longitudinal_member_ids(model, y_m=float(girder.y_m))
        for quantity, native_component, external_component, unit in (
            ("Moment", girder.moment_knm, "M_VERTICAL", "kNm"),
            ("Shear", girder.shear_kn, "V_VERTICAL", "kN"),
            ("Torsion", girder.torsion_knm, "T", "kNm"),
        ):
            stage5_case_id = _stage5_case_id_for_source(
                identities,
                group="lm1",
                source_case_id=native_component.case_id,
            )
            external_value = external_results.member_component_envelope(
                stage5_case_id,
                member_ids=member_ids,
                component=external_component,
            )
            native_value = abs(float(native_component.value))
            difference = _relative_difference(native_value, external_value)
            absolute_difference = abs(external_value - native_value)
            allowable = policy.allowable_absolute_error(
                reference_value=native_value,
                unit=unit,
            )
            items.append(
                EnvelopeComparisonItem(
                    girder_index=girder.girder_index,
                    quantity=quantity,
                    source_case_id=native_component.case_id,
                    stage5_case_id=stage5_case_id,
                    native_value=native_value,
                    external_value=external_value,
                    unit=unit,
                    relative_difference=difference,
                    absolute_difference=absolute_difference,
                    allowable_absolute_difference=allowable,
                    passes=policy.passes(
                        reference_value=native_value,
                        comparison_value=external_value,
                        unit=unit,
                    ),
                )
            )

        deflection = deflections.get(girder.girder_index)
        if deflection is not None:
            stage5_case_id = _stage5_case_id_for_source(
                identities,
                group="lm1",
                source_case_id=deflection.case_id,
            )
            external_value, external_x = (
                external_results.nearest_vertical_displacement_mm(
                    stage5_case_id,
                    model,
                    y_m=float(girder.y_m),
                    target_x_m=float(deflection.position_m),
                )
            )
            native_value = abs(float(deflection.value_mm))
            difference = _relative_difference(native_value, external_value)
            absolute_difference = abs(external_value - native_value)
            allowable = policy.allowable_absolute_error(
                reference_value=native_value,
                unit="mm",
            )
            items.append(
                EnvelopeComparisonItem(
                    girder_index=girder.girder_index,
                    quantity="Deflection",
                    source_case_id=deflection.case_id,
                    stage5_case_id=stage5_case_id,
                    native_value=native_value,
                    external_value=external_value,
                    unit="mm",
                    relative_difference=difference,
                    absolute_difference=absolute_difference,
                    allowable_absolute_difference=allowable,
                    passes=policy.passes(
                        reference_value=native_value,
                        comparison_value=external_value,
                        unit="mm",
                    ),
                    note=(
                        f"Native governing station x={deflection.position_m:.4f} m; "
                        f"external comparison node x={external_x:.4f} m."
                    ),
                )
            )

    permanent_identity = next(
        (item for item in identities if item.get("group") == "permanent"),
        None,
    )
    permanent_equilibrium: PermanentEquilibriumComparison | None = None
    if permanent_identity is not None:
        stage5_case_id = int(permanent_identity["stage5_case_id"])
        external_total = external_results.support_reaction_sum_kn(stage5_case_id)
        load_case = next(
            case for case in model.load_cases if case.load_case_id == stage5_case_id
        )
        permanent_model = replace(
            model,
            load_cases=(load_case,),
            load_combinations=(),
        )
        prepared = prepare_vertical_grillage(permanent_model)
        native_analysis = solve_prepared_vertical_grillage(
            prepared,
            permanent_model,
        )
        support_ids = {support.node_id for support in permanent_model.supports}
        native_total = sum(
            node.vertical_reaction_kn
            for node in native_analysis.nodes
            if node.node_id in support_ids
        )
        eq_difference = _relative_difference(native_total, external_total)
        absolute_difference = abs(external_total - native_total)
        allowable = policy.allowable_absolute_error(
            reference_value=native_total,
            unit="kN",
        )
        permanent_equilibrium = PermanentEquilibriumComparison(
            stage5_case_id=stage5_case_id,
            native_total_reaction_kn=native_total,
            external_total_reaction_kn=external_total,
            relative_difference=eq_difference,
            absolute_difference=absolute_difference,
            allowable_absolute_difference=allowable,
            passes=policy.passes(
                reference_value=native_total,
                comparison_value=external_total,
                unit="kN",
            ),
        )

    return StaadEnvelopeComparisonReport(
        source_name=source_name,
        relative_tolerance=policy.relative_tolerance,
        permanent_equilibrium=permanent_equilibrium,
        items=tuple(items),
    )


@dataclass(frozen=True)
class CombinationEnvelopeComparisonItem:
    category: str
    girder_index: int
    quantity: str
    native_governing_result_id: int
    native_governing_result_name: str
    external_governing_result_id: int
    external_governing_result_name: str
    native_value: float
    external_value_at_native_result: float
    external_envelope_value: float
    unit: str
    same_case_relative_difference: float | None
    envelope_relative_difference: float | None
    same_case_absolute_difference: float
    envelope_absolute_difference: float
    allowable_absolute_difference: float
    governing_result_matches: bool
    passes: bool


@dataclass(frozen=True)
class CombinationEnvelopeComparisonReport:
    source_name: str
    relative_tolerance: float
    requested_combination_ids: tuple[int, ...]
    missing_combination_ids: tuple[int, ...]
    items: tuple[CombinationEnvelopeComparisonItem, ...]

    @property
    def passes(self) -> bool:
        return (
            bool(self.items)
            and not self.missing_combination_ids
            and all(item.passes for item in self.items)
        )

    @property
    def maximum_relative_difference(self) -> float | None:
        values = [
            abs(value)
            for item in self.items
            for value in (
                item.same_case_relative_difference,
                item.envelope_relative_difference,
            )
            if value is not None
        ]
        return max(values) if values else None


def _longitudinal_girder_lines(
    model: VerificationModel,
    *,
    tolerance_m: float = 1.0e-9,
) -> tuple[float, ...]:
    nodes = {node.node_id: node for node in model.nodes}
    values: set[float] = set()
    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if (
            abs(float(ni.y_m) - float(nj.y_m)) <= tolerance_m
            and abs(float(nj.x_m) - float(ni.x_m)) > tolerance_m
        ):
            values.add(round(float(ni.y_m), 12))
    if not values:
        raise ValueError("Stage-5 model contains no longitudinal girder lines.")
    return tuple(sorted(values))


def compare_stage5_combination_envelopes(
    model: VerificationModel,
    *,
    native_results: VerificationResultDatabase,
    external_results: VerificationResultDatabase,
    result_ids: tuple[int, ...] | None = None,
    tolerance: VerificationImportTolerance | None = None,
    source_name: str = "External solver",
) -> CombinationEnvelopeComparisonReport:
    """Compare governing ULS/SLS combination envelopes by girder.

    Detailed result-set comparison checks every returned row. This higher-level layer
    independently identifies the governing combination for each girder response and
    checks both the external value on the native governing combination and the external
    governing envelope itself. A different governing combination is recorded but is not
    automatically a failure when the envelope magnitude still agrees within tolerance.
    """

    policy = tolerance or VerificationImportTolerance()
    selected = (
        {item.combination_id for item in model.load_combinations}
        if result_ids is None
        else set(result_ids)
    )
    combinations = tuple(
        item for item in model.load_combinations if item.combination_id in selected
    )
    requested = tuple(item.combination_id for item in combinations)
    missing_set = {
        item.combination_id
        for item in combinations
        if not native_results.has_result(item.combination_id)
        or not external_results.has_result(item.combination_id)
    }
    missing = tuple(
        item.combination_id
        for item in combinations
        if item.combination_id in missing_set
    )
    available = tuple(
        item for item in combinations if item.combination_id not in missing_set
    )
    if not available:
        return CombinationEnvelopeComparisonReport(
            source_name=source_name,
            relative_tolerance=policy.relative_tolerance,
            requested_combination_ids=requested,
            missing_combination_ids=missing,
            items=(),
        )

    by_category: dict[str, list] = {}
    for combination in available:
        by_category.setdefault(combination.category, []).append(combination)

    girder_lines = _longitudinal_girder_lines(model)
    items: list[CombinationEnvelopeComparisonItem] = []
    for category, category_combinations in by_category.items():
        is_sls = category.strip().upper().startswith("SLS")
        name_by_id = {
            item.combination_id: item.name for item in category_combinations
        }
        for girder_index, y_m in enumerate(girder_lines, start=1):
            member_ids = _longitudinal_member_ids(model, y_m=y_m)
            for quantity, component, unit in (
                ("Moment", "M_VERTICAL", "kNm"),
                ("Shear", "V_VERTICAL", "kN"),
                ("Torsion", "T", "kNm"),
            ):
                native_values = {
                    item.combination_id: native_results.member_component_envelope(
                        item.combination_id,
                        member_ids=member_ids,
                        component=component,
                    )
                    for item in category_combinations
                }
                external_values = {
                    item.combination_id: external_results.member_component_envelope(
                        item.combination_id,
                        member_ids=member_ids,
                        component=component,
                    )
                    for item in category_combinations
                }
                native_id = max(native_values, key=native_values.__getitem__)
                external_id = max(external_values, key=external_values.__getitem__)
                native_value = native_values[native_id]
                external_same = external_values[native_id]
                external_envelope = external_values[external_id]
                same_case_absolute = abs(external_same - native_value)
                envelope_absolute = abs(external_envelope - native_value)
                allowable = policy.allowable_absolute_error(
                    reference_value=native_value,
                    unit=unit,
                )
                items.append(
                    CombinationEnvelopeComparisonItem(
                        category=category,
                        girder_index=girder_index,
                        quantity=quantity,
                        native_governing_result_id=native_id,
                        native_governing_result_name=name_by_id[native_id],
                        external_governing_result_id=external_id,
                        external_governing_result_name=name_by_id[external_id],
                        native_value=native_value,
                        external_value_at_native_result=external_same,
                        external_envelope_value=external_envelope,
                        unit=unit,
                        same_case_relative_difference=_relative_difference(
                            native_value,
                            external_same,
                        ),
                        envelope_relative_difference=_relative_difference(
                            native_value,
                            external_envelope,
                        ),
                        same_case_absolute_difference=same_case_absolute,
                        envelope_absolute_difference=envelope_absolute,
                        allowable_absolute_difference=allowable,
                        governing_result_matches=(native_id == external_id),
                        passes=(
                            policy.passes(
                                reference_value=native_value,
                                comparison_value=external_same,
                                unit=unit,
                            )
                            and policy.passes(
                                reference_value=native_value,
                                comparison_value=external_envelope,
                                unit=unit,
                            )
                        ),
                    )
                )

            if is_sls:
                native_values = {
                    item.combination_id: native_results.vertical_displacement_envelope_mm(
                        item.combination_id,
                        model,
                        y_m=y_m,
                    )
                    for item in category_combinations
                }
                external_values = {
                    item.combination_id: external_results.vertical_displacement_envelope_mm(
                        item.combination_id,
                        model,
                        y_m=y_m,
                    )
                    for item in category_combinations
                }
                native_id = max(native_values, key=native_values.__getitem__)
                external_id = max(external_values, key=external_values.__getitem__)
                native_value = native_values[native_id]
                external_same = external_values[native_id]
                external_envelope = external_values[external_id]
                allowable = policy.allowable_absolute_error(
                    reference_value=native_value,
                    unit="mm",
                )
                items.append(
                    CombinationEnvelopeComparisonItem(
                        category=category,
                        girder_index=girder_index,
                        quantity="Deflection",
                        native_governing_result_id=native_id,
                        native_governing_result_name=name_by_id[native_id],
                        external_governing_result_id=external_id,
                        external_governing_result_name=name_by_id[external_id],
                        native_value=native_value,
                        external_value_at_native_result=external_same,
                        external_envelope_value=external_envelope,
                        unit="mm",
                        same_case_relative_difference=_relative_difference(
                            native_value,
                            external_same,
                        ),
                        envelope_relative_difference=_relative_difference(
                            native_value,
                            external_envelope,
                        ),
                        same_case_absolute_difference=abs(external_same - native_value),
                        envelope_absolute_difference=abs(
                            external_envelope - native_value
                        ),
                        allowable_absolute_difference=allowable,
                        governing_result_matches=(native_id == external_id),
                        passes=(
                            policy.passes(
                                reference_value=native_value,
                                comparison_value=external_same,
                                unit="mm",
                            )
                            and policy.passes(
                                reference_value=native_value,
                                comparison_value=external_envelope,
                                unit="mm",
                            )
                        ),
                    )
                )

    return CombinationEnvelopeComparisonReport(
        source_name=source_name,
        relative_tolerance=policy.relative_tolerance,
        requested_combination_ids=requested,
        missing_combination_ids=missing,
        items=tuple(items),
    )
