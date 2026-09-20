from __future__ import annotations

import json
from dataclasses import dataclass, replace

from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
)
from rc_bridge.export.external_results import parse_verification_results_csv
from rc_bridge.export.staad_anl import parse_staad_anl_results
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
    passes: bool
    note: str = ""


@dataclass(frozen=True)
class PermanentEquilibriumComparison:
    stage5_case_id: int
    native_total_reaction_kn: float
    external_total_reaction_kn: float
    relative_difference: float | None
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


def _component_envelope(
    normalized_csv: str,
    *,
    member_ids: set[int],
    component: str,
) -> float:
    values = [
        abs(item.value)
        for item in parse_verification_results_csv(normalized_csv)
        if item.result_type == "member_end_force"
        and item.component == component
        and int(item.object_id) in member_ids
    ]
    if not values:
        raise ValueError(
            f"STAAD normalized results contain no {component} values for the "
            "selected girder line."
        )
    return max(values)


def _nearest_deflection(
    normalized_csv: str,
    model: VerificationModel,
    *,
    y_m: float,
    target_x_m: float,
    tolerance_m: float = 1.0e-9,
) -> tuple[float, float]:
    nodes = {node.node_id: node for node in model.nodes}
    candidates: list[tuple[float, float, float]] = []
    for item in parse_verification_results_csv(normalized_csv):
        if item.result_type != "node_displacement" or item.component != "DZ":
            continue
        node = nodes.get(int(item.object_id))
        if node is None or abs(node.y_m - y_m) > tolerance_m:
            continue
        candidates.append((abs(node.x_m - target_x_m), abs(item.value) * 1000.0, node.x_m))
    if not candidates:
        raise ValueError(
            "STAAD normalized results contain no vertical displacement values for "
            "the selected girder line."
        )
    _, value_mm, x_m = min(candidates, key=lambda item: item[0])
    return value_mm, x_m


def _sum_support_reactions(normalized_csv: str) -> float:
    return sum(
        item.value
        for item in parse_verification_results_csv(normalized_csv)
        if item.result_type == "support_reaction" and item.component == "FZ"
    )


def compare_staad_lm1_envelopes(
    model: VerificationModel,
    lm1: ProjectNativeLM1GrillageSearchResult,
    *,
    staad_anl_text: str,
    relative_tolerance: float = 0.05,
    source_name: str = "STAAD.Pro",
) -> StaadEnvelopeComparisonReport:
    """Compare native governing LM1 envelopes against the same cases rerun in STAAD.

    The application's governing source case is mapped to its Stage-5 exported case
    using the model's case_identity metadata. STAAD member-end results are then
    enveloped only along the corresponding longitudinal girder chain. Deflection is
    compared at the closest exported grillage node to the native governing station.
    """

    if relative_tolerance < 0.0:
        raise ValueError("Envelope comparison tolerance cannot be negative.")
    identities = _stage5_case_identity(model)
    cache: dict[int, str] = {}

    def normalized(stage5_case_id: int) -> str:
        if stage5_case_id not in cache:
            cache[stage5_case_id] = parse_staad_anl_results(
                staad_anl_text,
                model,
                load_case_id=stage5_case_id,
            )
        return cache[stage5_case_id]

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
            external_value = _component_envelope(
                normalized(stage5_case_id),
                member_ids=member_ids,
                component=external_component,
            )
            native_value = abs(float(native_component.value))
            difference = _relative_difference(native_value, external_value)
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
                    passes=(
                        difference is None
                        or abs(difference) <= relative_tolerance + 1.0e-12
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
            external_value, external_x = _nearest_deflection(
                normalized(stage5_case_id),
                model,
                y_m=float(girder.y_m),
                target_x_m=float(deflection.position_m),
            )
            native_value = abs(float(deflection.value_mm))
            difference = _relative_difference(native_value, external_value)
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
                    passes=(
                        difference is None
                        or abs(difference) <= relative_tolerance + 1.0e-12
                    ),
                    note=(
                        f"Native governing station x={deflection.position_m:.4f} m; "
                        f"STAAD comparison node x={external_x:.4f} m."
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
        external_csv = normalized(stage5_case_id)
        external_total = _sum_support_reactions(external_csv)
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
        permanent_equilibrium = PermanentEquilibriumComparison(
            stage5_case_id=stage5_case_id,
            native_total_reaction_kn=native_total,
            external_total_reaction_kn=external_total,
            relative_difference=eq_difference,
            passes=(
                eq_difference is None
                or abs(eq_difference) <= relative_tolerance + 1.0e-12
            ),
        )

    return StaadEnvelopeComparisonReport(
        source_name=source_name,
        relative_tolerance=relative_tolerance,
        permanent_equilibrium=permanent_equilibrium,
        items=tuple(items),
    )
