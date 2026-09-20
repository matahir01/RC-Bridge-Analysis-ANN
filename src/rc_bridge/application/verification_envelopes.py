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
