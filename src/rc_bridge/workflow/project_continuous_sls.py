from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.core.models import (
    IGirderProfile,
    ProjectInput,
    RectangularGirderProfile,
    TGirderProfile,
)
from rc_bridge.design.eurocode_layered_cracking import HorizontalSectionLayer
from rc_bridge.workflow.continuous_support_sls import (
    ContinuousSupportCrackCheck,
    ContinuousSupportCrackInput,
    ServiceCombinationKind,
    check_continuous_support_cracking,
)
from rc_bridge.workflow.project_continuous_envelope import (
    ContinuousDesignEnvelopeResult,
    ContinuousDesignEnvelopeStation,
)


@dataclass(frozen=True)
class ContinuousHoggingCrackResult:
    combination_kind: ServiceCombinationKind
    governing_station: ContinuousDesignEnvelopeStation
    support_check: ContinuousSupportCrackCheck
    status: str

    @property
    def service_moment_knm(self) -> float:
        return self.support_check.service_moment_magnitude_knm

    @property
    def signed_service_moment_knm(self) -> float:
        return self.support_check.signed_service_moment_knm

    @property
    def crack(self):
        return self.support_check.crack


def _negative_sls_effect(
    station: ContinuousDesignEnvelopeStation,
    combination_kind: ServiceCombinationKind,
) -> float:
    combinations = station.moment_combinations
    if combination_kind == "characteristic":
        return combinations.negative_characteristic_sls_effect
    if combination_kind == "frequent":
        return combinations.negative_frequent_sls_effect
    if combination_kind == "quasi_permanent":
        return combinations.negative_quasi_permanent_sls_effect
    raise ValueError(
        "combination_kind must be 'characteristic', 'frequent', or 'quasi_permanent'."
    )


def support_layers_from_project(
    project: ProjectInput,
    *,
    effective_deck_width_m: float,
) -> tuple[HorizontalSectionLayer, ...]:
    """Build bottom-to-top hogging section strips from physical project geometry.

    Girder profile dimensions are retained explicitly. The deck false slab and
    in-situ slab use the supplied verified deck width, while each layer's ``active``
    flag follows the project's composite-participation setting. Thus the 75 mm
    false slab can preserve physical depth without automatically receiving
    stiffness or crack-control credit.
    """
    if effective_deck_width_m <= 0.0:
        raise ValueError("Effective deck width must be positive.")
    if effective_deck_width_m > float(project.geometry.deck_width_m) + 1e-9:
        raise ValueError("Effective deck width cannot exceed the physical deck width.")

    profile = project.geometry.girder_profile
    if profile is None:
        raise ValueError(
            "Physical girder profile dimensions are required to build support SLS layers."
        )

    layers: list[HorizontalSectionLayer] = []
    y = 0.0

    def append_layer(width_m: float, thickness_m: float, label: str, *, active: bool = True) -> None:
        nonlocal y
        if thickness_m <= 0.0:
            return
        next_y = y + thickness_m
        layers.append(
            HorizontalSectionLayer(
                width_m=width_m,
                start_depth_m=y,
                end_depth_m=next_y,
                label=label,
                active=active,
            )
        )
        y = next_y

    if isinstance(profile, IGirderProfile):
        append_layer(
            float(profile.bottom_flange_width_m),
            float(profile.bottom_flange_thickness_m),
            "precast bottom flange",
        )
        append_layer(
            float(profile.web_width_m),
            float(profile.web_depth_m),
            "precast web",
        )
        append_layer(
            float(profile.top_flange_width_m),
            float(profile.top_flange_thickness_m),
            "precast top flange",
        )
    elif isinstance(profile, TGirderProfile):
        append_layer(
            float(profile.web_width_m),
            float(profile.total_depth_m - profile.flange_thickness_m),
            "precast T-girder stem",
        )
        append_layer(
            float(profile.flange_width_m),
            float(profile.flange_thickness_m),
            "precast T-girder top flange",
        )
    elif isinstance(profile, RectangularGirderProfile):
        append_layer(
            float(profile.width_m),
            float(profile.depth_m),
            "precast rectangular girder",
        )
    else:
        raise TypeError("Unsupported physical girder profile type.")

    deck = project.geometry.deck_construction
    append_layer(
        effective_deck_width_m,
        float(deck.precast_false_slab_depth_m),
        "precast false slab",
        active=deck.false_slab_composite_participation,
    )
    append_layer(
        effective_deck_width_m,
        float(deck.in_situ_slab_depth_m),
        "in-situ deck",
        active=deck.in_situ_slab_composite_participation,
    )

    expected_depth = float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    if abs(y - expected_depth) > 1e-9:
        raise ValueError(
            "Layered support-section depth does not match girder plus physical deck depth."
        )
    return tuple(layers)


def support_crack_input_from_project(
    project: ProjectInput,
    *,
    effective_deck_width_m: float,
    top_tension_steel_area_mm2: float,
    steel_depth_from_bottom_m: float,
    bar_diameter_mm: float,
    bar_spacing_mm: float,
    cover_mm: float,
    es_mpa: float,
    ecm_mpa: float,
    fct_eff_mpa: float,
    crack_limit_mm: float,
    kt: float = 0.4,
) -> ContinuousSupportCrackInput:
    layers = support_layers_from_project(
        project,
        effective_deck_width_m=effective_deck_width_m,
    )
    total_depth = float(project.geometry.girder_depth_m) + project.geometry.physical_deck_depth_m
    return ContinuousSupportCrackInput(
        layers_from_compression_face=layers,
        total_depth_m=total_depth,
        top_tension_steel_area_mm2=top_tension_steel_area_mm2,
        steel_depth_from_compression_face_m=steel_depth_from_bottom_m,
        bar_diameter_mm=bar_diameter_mm,
        bar_spacing_mm=bar_spacing_mm,
        cover_mm=cover_mm,
        es_mpa=es_mpa,
        ecm_mpa=ecm_mpa,
        fct_eff_mpa=fct_eff_mpa,
        crack_limit_mm=crack_limit_mm,
        kt=kt,
    )


def run_continuous_hogging_crack_check(
    envelope: ContinuousDesignEnvelopeResult,
    *,
    input_data: ContinuousSupportCrackInput,
    combination_kind: ServiceCombinationKind = "frequent",
) -> ContinuousHoggingCrackResult:
    """Check crack width at the independently scanned SLS-governing support section."""
    if not envelope.stations:
        raise ValueError("Continuous design envelope contains no stations.")

    negative_effects = tuple(
        _negative_sls_effect(station, combination_kind) for station in envelope.stations
    )
    station_index = min(range(len(envelope.stations)), key=lambda index: negative_effects[index])
    governing_station = envelope.stations[station_index]
    support_check = check_continuous_support_cracking(
        governing_station.moment_combinations,
        input_data,
        service_combination=combination_kind,
    )
    return ContinuousHoggingCrackResult(
        combination_kind=combination_kind,
        governing_station=governing_station,
        support_check=support_check,
        status=(
            "Project continuous support SLS: governing negative service station scanned over the "
            "full envelope, then checked by the canonical layered support-cracking workflow"
        ),
    )
