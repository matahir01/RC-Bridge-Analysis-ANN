from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from rc_bridge.export.external_results import (
    VerificationResultValue,
    parse_verification_results_csv,
)
from rc_bridge.export.verification_model import VerificationModel


@dataclass(frozen=True)
class VerificationResultDatabase:
    """Indexed normalized result database for one external verification import.

    The raw ANL/table parser runs once. Downstream checks query this database by
    result ID, member/node and semantic component instead of rescanning the source
    file or reparsing normalized CSV repeatedly.
    """

    normalized_csv_by_result: dict[int, str]
    records_by_result: dict[int, tuple[VerificationResultValue, ...]]
    member_end_index: dict[int, dict[int, dict[str, dict[str, float]]]]
    node_displacement_index: dict[int, dict[int, float]]
    support_reaction_index: dict[int, dict[int, float]]

    @classmethod
    def from_normalized_csvs(
        cls,
        normalized_csv_by_result: dict[int, str],
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> VerificationResultDatabase:
        records_by_result: dict[int, tuple[VerificationResultValue, ...]] = {}
        member_end_index: dict[int, dict[int, dict[str, dict[str, float]]]] = {}
        node_displacement_index: dict[int, dict[int, float]] = {}
        support_reaction_index: dict[int, dict[int, float]] = {}

        total = len(normalized_csv_by_result)
        for index, (result_id, csv_text) in enumerate(
            normalized_csv_by_result.items(),
            start=1,
        ):
            if cancel_check is not None and cancel_check():
                raise RuntimeError(
                    "Verification import cancelled while indexing external results."
                )
            records = parse_verification_results_csv(csv_text)
            records_by_result[result_id] = records
            members: dict[int, dict[str, dict[str, float]]] = {}
            displacements: dict[int, float] = {}
            reactions: dict[int, float] = {}

            for record in records:
                object_id = int(record.object_id)
                if record.result_type == "member_end_force":
                    members.setdefault(object_id, {}).setdefault(
                        record.position_m,
                        {},
                    )[record.component] = float(record.value)
                elif (
                    record.result_type == "node_displacement"
                    and record.component == "DZ"
                ):
                    displacements[object_id] = float(record.value)
                elif (
                    record.result_type == "support_reaction"
                    and record.component == "FZ"
                ):
                    reactions[object_id] = float(record.value)

            member_end_index[result_id] = members
            node_displacement_index[result_id] = displacements
            support_reaction_index[result_id] = reactions
            if progress_callback is not None:
                progress_callback(index, total)

        return cls(
            normalized_csv_by_result=dict(normalized_csv_by_result),
            records_by_result=records_by_result,
            member_end_index=member_end_index,
            node_displacement_index=node_displacement_index,
            support_reaction_index=support_reaction_index,
        )

    def has_result(self, result_id: int) -> bool:
        return result_id in self.records_by_result

    def normalized_csv(self, result_id: int) -> str:
        try:
            return self.normalized_csv_by_result[result_id]
        except KeyError as exc:
            raise KeyError(f"External result ID {result_id} is not available.") from exc

    def member_component_envelope(
        self,
        result_id: int,
        *,
        member_ids: set[int],
        component: str,
    ) -> float:
        member_results = self.member_end_index.get(result_id, {})
        values = [
            abs(component_values[component])
            for member_id in member_ids
            for component_values in member_results.get(member_id, {}).values()
            if component in component_values
        ]
        if not values:
            raise ValueError(
                f"External result {result_id} contains no {component} values for "
                "the selected member set."
            )
        return max(values)

    def nearest_vertical_displacement_mm(
        self,
        result_id: int,
        model: VerificationModel,
        *,
        y_m: float,
        target_x_m: float,
        tolerance_m: float = 1.0e-9,
    ) -> tuple[float, float]:
        nodes = {node.node_id: node for node in model.nodes}
        values = self.node_displacement_index.get(result_id, {})
        candidates: list[tuple[float, float, float]] = []
        for node_id, displacement_m in values.items():
            node = nodes.get(node_id)
            if node is None or abs(float(node.y_m) - y_m) > tolerance_m:
                continue
            candidates.append(
                (
                    abs(float(node.x_m) - target_x_m),
                    abs(displacement_m) * 1000.0,
                    float(node.x_m),
                )
            )
        if not candidates:
            raise ValueError(
                f"External result {result_id} contains no vertical displacement "
                "values for the selected girder line."
            )
        _, value_mm, x_m = min(candidates, key=lambda item: item[0])
        return value_mm, x_m

    def vertical_displacement_envelope_mm(
        self,
        result_id: int,
        model: VerificationModel,
        *,
        y_m: float,
        tolerance_m: float = 1.0e-9,
    ) -> float:
        nodes = {node.node_id: node for node in model.nodes}
        values = self.node_displacement_index.get(result_id, {})
        candidates = [
            abs(displacement_m) * 1000.0
            for node_id, displacement_m in values.items()
            if (
                (node := nodes.get(node_id)) is not None
                and abs(float(node.y_m) - y_m) <= tolerance_m
            )
        ]
        if not candidates:
            raise ValueError(
                f"External result {result_id} contains no vertical displacement "
                "values for the selected girder line."
            )
        return max(candidates)

    def support_reaction_sum_kn(self, result_id: int) -> float:
        reactions = self.support_reaction_index.get(result_id, {})
        if not reactions:
            raise ValueError(
                f"External result {result_id} contains no vertical support reactions."
            )
        return sum(reactions.values())
