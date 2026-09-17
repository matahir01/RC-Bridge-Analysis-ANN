from __future__ import annotations

from dataclasses import dataclass
from math import log


@dataclass(frozen=True)
class EC2ConcreteProperties:
    fck_mpa: float
    fcm_mpa: float
    fctm_mpa: float
    ecm_mpa: float


def mean_compressive_strength_mpa(fck_mpa: float) -> float:
    """Mean concrete compressive strength fcm for first-generation EC2."""
    if fck_mpa <= 0.0:
        raise ValueError("fck_mpa must be positive.")
    if fck_mpa > 90.0:
        raise ValueError("This first-generation EC2 helper is limited to fck <= 90 MPa.")
    return fck_mpa + 8.0


def mean_tensile_strength_mpa(fck_mpa: float) -> float:
    """Mean axial tensile strength fctm from EN 1992-1-1 Table 3.1 rules."""
    fcm_mpa = mean_compressive_strength_mpa(fck_mpa)
    if fck_mpa <= 50.0:
        return 0.30 * fck_mpa ** (2.0 / 3.0)
    return 2.12 * log(1.0 + fcm_mpa / 10.0)


def secant_elastic_modulus_mpa(fck_mpa: float) -> float:
    """Secant elastic modulus Ecm for normal-weight concrete in first-gen EC2."""
    fcm_mpa = mean_compressive_strength_mpa(fck_mpa)
    return 22000.0 * (fcm_mpa / 10.0) ** 0.30


def concrete_properties_ec2(fck_mpa: float) -> EC2ConcreteProperties:
    """Return the baseline first-generation EC2 concrete material properties."""
    return EC2ConcreteProperties(
        fck_mpa=fck_mpa,
        fcm_mpa=mean_compressive_strength_mpa(fck_mpa),
        fctm_mpa=mean_tensile_strength_mpa(fck_mpa),
        ecm_mpa=secant_elastic_modulus_mpa(fck_mpa),
    )
