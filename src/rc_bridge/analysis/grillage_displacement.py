from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import sqrt

from rc_bridge.analysis.grillage_solver import GrillageNodeResult
from rc_bridge.export.verification_model import VerificationModel


@dataclass(frozen=True)
class LongitudinalDisplacementPiece:
    """Cubic Hermite vertical-displacement field for one longitudinal member."""

    x_start_m: float
    x_end_m: float
    a0_m: float
    a1: float
    a2_per_m: float
    a3_per_m2: float

    def value_m(self, x_m: float) -> float:
        if x_m < self.x_start_m - 1.0e-9 or x_m > self.x_end_m + 1.0e-9:
            raise ValueError("Displacement evaluation point lies outside the member.")
        u = x_m - self.x_start_m
        return (
            self.a0_m
            + self.a1 * u
            + self.a2_per_m * u**2
            + self.a3_per_m2 * u**3
        )

    def slope(self, x_m: float) -> float:
        if x_m < self.x_start_m - 1.0e-9 or x_m > self.x_end_m + 1.0e-9:
            raise ValueError("Slope evaluation point lies outside the member.")
        u = x_m - self.x_start_m
        return self.a1 + 2.0 * self.a2_per_m * u + 3.0 * self.a3_per_m2 * u**2

    def translated_coefficients(
        self,
        x_m: float,
    ) -> tuple[float, float, float, float]:
        if x_m < self.x_start_m - 1.0e-9 or x_m > self.x_end_m + 1.0e-9:
            raise ValueError("Translation point lies outside the displacement member.")
        d = x_m - self.x_start_m
        return (
            self.value_m(x_m),
            self.slope(x_m),
            self.a2_per_m + 3.0 * self.a3_per_m2 * d,
            self.a3_per_m2,
        )


@dataclass(frozen=True)
class CombinedLongitudinalDeflectionPeak:
    maximum_absolute_deflection_m: float
    position_m: float
    signed_deflection_m: float


def longitudinal_displacement_field(
    model: VerificationModel,
    node_results: Sequence[GrillageNodeResult],
    *,
    target_y_m: float,
    tolerance_m: float = 1.0e-9,
) -> tuple[LongitudinalDisplacementPiece, ...]:
    """Recover the FE cubic displacement field along one physical girder line."""
    if tolerance_m <= 0.0:
        raise ValueError("tolerance_m must be positive.")

    nodes = {node.node_id: node for node in model.nodes}
    results = {item.node_id: item for item in node_results}
    if set(nodes) != set(results):
        raise ValueError("Node-result IDs do not match the supplied grillage model.")

    pieces: list[LongitudinalDisplacementPiece] = []
    for beam in model.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        dx = nj.x_m - ni.x_m
        if abs(dx) <= tolerance_m:
            continue
        if abs(ni.y_m - target_y_m) > tolerance_m:
            continue
        if abs(nj.y_m - target_y_m) > tolerance_m:
            continue
        if dx < 0.0:
            raise ValueError(
                "Longitudinal displacement recovery requires members ordered in "
                "increasing global x."
            )

        ri = results[beam.node_i]
        rj = results[beam.node_j]
        length = dx

        # For a longitudinal member running in +global x, the grillage element
        # transformation defines Euler-Bernoulli slope dw/dx = -Ry.
        wi = ri.vertical_displacement_m
        wj = rj.vertical_displacement_m
        slope_i = -ri.rotation_y_rad
        slope_j = -rj.rotation_y_rad

        a2 = (
            3.0 * (wj - wi) / length**2
            - (2.0 * slope_i + slope_j) / length
        )
        a3 = (
            2.0 * (wi - wj) / length**3
            + (slope_i + slope_j) / length**2
        )
        pieces.append(
            LongitudinalDisplacementPiece(
                x_start_m=ni.x_m,
                x_end_m=nj.x_m,
                a0_m=wi,
                a1=slope_i,
                a2_per_m=a2,
                a3_per_m2=a3,
            )
        )

    pieces.sort(key=lambda item: item.x_start_m)
    if not pieces:
        raise ValueError(
            f"No longitudinal displacement field found at y={target_y_m:.6g} m."
        )
    for previous, current in pairwise(pieces):
        if abs(previous.x_end_m - current.x_start_m) > tolerance_m:
            raise ValueError("Longitudinal displacement field contains a gap.")
        if current.x_start_m < previous.x_end_m - tolerance_m:
            raise ValueError("Longitudinal displacement field contains overlapping members.")
    return tuple(pieces)


def _piece_at(
    pieces: tuple[LongitudinalDisplacementPiece, ...],
    x_m: float,
) -> LongitudinalDisplacementPiece:
    matches = [
        piece
        for piece in pieces
        if piece.x_start_m - 1.0e-9 <= x_m <= piece.x_end_m + 1.0e-9
    ]
    if not matches:
        raise ValueError(f"No displacement piece contains x={x_m:.6g} m.")
    # At a shared node either adjacent cubic gives the same nodal displacement.
    return matches[0]


def combined_longitudinal_deflection_peak(
    permanent: tuple[LongitudinalDisplacementPiece, ...],
    traffic: tuple[LongitudinalDisplacementPiece, ...] | None = None,
    *,
    traffic_factor: float = 1.0,
) -> CombinedLongitudinalDeflectionPeak:
    """Find the exact interior peak of permanent + factor*traffic FE fields."""
    if not permanent:
        raise ValueError("A permanent displacement field is required.")
    if traffic_factor < 0.0:
        raise ValueError("traffic_factor cannot be negative.")
    if traffic is None:
        traffic_factor = 0.0

    breakpoints = {piece.x_start_m for piece in permanent}
    breakpoints.update(piece.x_end_m for piece in permanent)
    if traffic is not None:
        breakpoints.update(piece.x_start_m for piece in traffic)
        breakpoints.update(piece.x_end_m for piece in traffic)
    ordered = tuple(sorted(breakpoints))
    if len(ordered) < 2:
        raise ValueError("Combined displacement field requires a positive bridge length.")

    best_abs = -1.0
    best_x = ordered[0]
    best_signed = 0.0

    def consider(x_m: float, value_m: float) -> None:
        nonlocal best_abs, best_x, best_signed
        magnitude = abs(value_m)
        if magnitude > best_abs:
            best_abs = magnitude
            best_x = x_m
            best_signed = value_m

    for left, right in pairwise(ordered):
        if right <= left + 1.0e-12:
            continue
        midpoint = 0.5 * (left + right)
        p = _piece_at(permanent, midpoint)
        p0, p1, p2, p3 = p.translated_coefficients(left)
        if traffic is None:
            t0 = t1 = t2 = t3 = 0.0
        else:
            t = _piece_at(traffic, midpoint)
            t0, t1, t2, t3 = t.translated_coefficients(left)

        a0 = p0 + traffic_factor * t0
        a1 = p1 + traffic_factor * t1
        a2 = p2 + traffic_factor * t2
        a3 = p3 + traffic_factor * t3
        length = right - left

        left_value = a0
        right_value = a0 + a1 * length + a2 * length**2 + a3 * length**3
        consider(left, left_value)
        consider(right, right_value)

        # Stationary points solve dv/dx = a1 + 2*a2*u + 3*a3*u^2 = 0.
        qa = 3.0 * a3
        qb = 2.0 * a2
        qc = a1
        roots: list[float] = []
        if abs(qa) <= 1.0e-18:
            if abs(qb) > 1.0e-18:
                roots.append(-qc / qb)
        else:
            discriminant = qb**2 - 4.0 * qa * qc
            if discriminant >= 0.0:
                root = sqrt(max(discriminant, 0.0))
                roots.extend(
                    (
                        (-qb - root) / (2.0 * qa),
                        (-qb + root) / (2.0 * qa),
                    )
                )
        for local_x in roots:
            if 1.0e-10 < local_x < length - 1.0e-10:
                root_value = (
                    a0
                    + a1 * local_x
                    + a2 * local_x**2
                    + a3 * local_x**3
                )
                consider(left + local_x, root_value)

    return CombinedLongitudinalDeflectionPeak(
        maximum_absolute_deflection_m=best_abs,
        position_m=best_x,
        signed_deflection_m=best_signed,
    )
