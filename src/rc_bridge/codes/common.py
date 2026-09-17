from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadEffects:
    moment_knm: float = 0.0
    shear_kn: float = 0.0
    torsion_knm: float = 0.0

    def __add__(self, other: "LoadEffects") -> "LoadEffects":
        return LoadEffects(
            moment_knm=self.moment_knm + other.moment_knm,
            shear_kn=self.shear_kn + other.shear_kn,
            torsion_knm=self.torsion_knm + other.torsion_knm,
        )

    def scaled(self, factor: float) -> "LoadEffects":
        return LoadEffects(
            moment_knm=self.moment_knm * factor,
            shear_kn=self.shear_kn * factor,
            torsion_knm=self.torsion_knm * factor,
        )


@dataclass(frozen=True)
class FactoredCombination:
    name: str
    effects: LoadEffects
    factors: dict[str, float]
