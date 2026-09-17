from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TorsionResult:
    design_torsion_knm: float
    transverse_asw_per_s_mm2_per_mm: float
    transverse_asw_per_s_mm2_per_m: float
    longitudinal_asl_mm2: float
    trdmax_knm: float
    cot_theta: float
    nu1: float
    status: str


@dataclass(frozen=True)
class ShearTorsionInteractionResult:
    torsion_ratio: float
    shear_ratio: float
    utilization: float
    passes: bool


def torsion_reinforcement_and_resistance(
    *,
    ted_knm: float,
    ak_m2: float,
    uk_m: float,
    tef_m: float,
    fck_mpa: float,
    fyk_mpa: float,
    gamma_c: float = 1.50,
    gamma_s: float = 1.15,
    alpha_cc: float = 1.0,
    alpha_cw: float = 1.0,
    cot_theta: float = 2.0,
    nu1: float | None = None,
) -> TorsionResult:
    """EC2 thin-walled equivalent-section torsion design quantities.

    Implements the transverse torsion reinforcement relation
    Asw/s = TEd / (2 Ak fywd cot(theta)), the total longitudinal torsion
    reinforcement relation Asl = TEd uk cot(theta) / (2 Ak fyd), and the
    concrete-strut limit TRd,max from EN 1992-1-1/EN 1992-2 clause 6.3.

    ``Ak``, ``uk`` and ``tef`` are explicit equivalent thin-wall properties.
    They are not inferred from an arbitrary T/I/rectangular girder section in
    this function. Units: kNm, m, MPa -> reinforcement in mm² and resistance kNm.
    """
    if ted_knm < 0.0:
        raise ValueError("Design torsion cannot be negative.")
    if min(ak_m2, uk_m, tef_m, fck_mpa, fyk_mpa) <= 0.0:
        raise ValueError("Torsion geometry and strengths must be positive.")
    if gamma_c <= 0.0 or gamma_s <= 0.0 or alpha_cc <= 0.0 or alpha_cw <= 0.0:
        raise ValueError("Material and resistance factors must be positive.")
    if not 1.0 <= cot_theta <= 2.5:
        raise ValueError("cot(theta) must lie between 1.0 and 2.5 for this implementation.")

    ak_mm2 = ak_m2 * 1_000_000.0
    uk_mm = uk_m * 1000.0
    tef_mm = tef_m * 1000.0
    ted_nmm = ted_knm * 1_000_000.0
    fyd_mpa = fyk_mpa / gamma_s
    fcd_mpa = alpha_cc * fck_mpa / gamma_c

    if nu1 is None:
        nu1_value = 0.6 * (1.0 - fck_mpa / 250.0)
    else:
        nu1_value = nu1
    if not 0.0 < nu1_value <= 1.0:
        raise ValueError("nu1 must lie between 0 and 1.")

    sin_theta_cos_theta = cot_theta / (cot_theta**2 + 1.0)
    trdmax_nmm = (
        2.0
        * nu1_value
        * alpha_cw
        * fcd_mpa
        * ak_mm2
        * tef_mm
        * sin_theta_cos_theta
    )
    trdmax_knm = trdmax_nmm / 1_000_000.0

    if ted_knm == 0.0:
        asw_per_s = 0.0
        asl_mm2 = 0.0
    else:
        asw_per_s = ted_nmm / (2.0 * ak_mm2 * fyd_mpa * cot_theta)
        asl_mm2 = ted_nmm * uk_mm * cot_theta / (2.0 * ak_mm2 * fyd_mpa)

    return TorsionResult(
        design_torsion_knm=ted_knm,
        transverse_asw_per_s_mm2_per_mm=asw_per_s,
        transverse_asw_per_s_mm2_per_m=asw_per_s * 1000.0,
        longitudinal_asl_mm2=asl_mm2,
        trdmax_knm=trdmax_knm,
        cot_theta=cot_theta,
        nu1=nu1_value,
        status=(
            "EC2 thin-walled torsion model; Ak, uk and tef require verified section geometry, "
            "and minimum/detailing reinforcement checks remain separate"
        ),
    )


def shear_torsion_interaction(
    *,
    ted_knm: float,
    trdmax_knm: float,
    ved_kn: float,
    vrdmax_kn: float,
) -> ShearTorsionInteractionResult:
    """Check the EC2 concrete-strut interaction for combined torsion and shear."""
    if ted_knm < 0.0 or ved_kn < 0.0:
        raise ValueError("Design torsion and shear magnitudes cannot be negative.")
    if trdmax_knm <= 0.0 or vrdmax_kn <= 0.0:
        raise ValueError("Torsion and shear strut resistances must be positive.")

    torsion_ratio = ted_knm / trdmax_knm
    shear_ratio = ved_kn / vrdmax_kn
    utilization = torsion_ratio + shear_ratio
    return ShearTorsionInteractionResult(
        torsion_ratio=torsion_ratio,
        shear_ratio=shear_ratio,
        utilization=utilization,
        passes=utilization <= 1.0,
    )
