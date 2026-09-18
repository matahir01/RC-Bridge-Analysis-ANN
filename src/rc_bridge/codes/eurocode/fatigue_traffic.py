from __future__ import annotations

from dataclasses import dataclass

from rc_bridge.analysis.loads import PointLoad
from rc_bridge.analysis.moving_loads import AxleTrain, positioned_axles
from rc_bridge.analysis.point_loads import section_response


@dataclass(frozen=True)
class FatigueLoadModel3:
    axle_loads_kn: tuple[float, float, float, float]
    axle_offsets_m: tuple[float, float, float, float]
    transverse_wheel_spacing_m: float
    status: str

    @property
    def axle_train(self) -> AxleTrain:
        return AxleTrain(
            axle_loads_kn=self.axle_loads_kn,
            axle_offsets_m=self.axle_offsets_m,
            label="EN 1991-2 FLM3",
        )


@dataclass(frozen=True)
class FLM3SimpleSpanSectionRange:
    section_position_m: float
    minimum_moment_knm: float
    maximum_moment_knm: float
    moment_range_knm: float
    governing_lead_position_m: float
    movement_steps: int
    status: str


def fatigue_load_model_3(*, axle_load_factor: float = 1.0) -> FatigueLoadModel3:
    """Return the EN 1991-2 Fatigue Load Model 3 four-axle vehicle.

    The standard nominal vehicle has four 120 kN axle lines at successive
    spacings 1.2 m, 6.0 m and 1.2 m, with two wheels per axle line at 2.0 m
    transverse spacing. The optional factor is explicit for National Annex or
    project adjustments; dynamic amplification is already represented by the
    code load model unless a governing document states otherwise.
    """
    if axle_load_factor <= 0.0:
        raise ValueError("FLM3 axle_load_factor must be positive.")
    axle = 120.0 * axle_load_factor
    return FatigueLoadModel3(
        axle_loads_kn=(axle, axle, axle, axle),
        axle_offsets_m=(0.0, 1.2, 7.2, 8.4),
        transverse_wheel_spacing_m=2.0,
        status=(
            "EN 1991-2 FLM3 nominal vehicle; confirm National Annex axle adjustment, "
            "fatigue lane position and local dynamic factor"
        ),
    )


def flm3_simple_span_section_moment_range(
    *,
    span_m: float,
    section_position_m: float,
    axle_load_factor: float = 1.0,
    longitudinal_distribution_factor: float = 1.0,
    movement_steps: int = 1201,
) -> FLM3SimpleSpanSectionRange:
    """Move FLM3 across a simple span and return a co-located moment range.

    ``longitudinal_distribution_factor`` maps the full vehicle axle-line loads
    to one longitudinal girder. It must come from a validated fatigue-specific
    transverse analysis; this function does not infer or certify that factor.
    """
    if span_m <= 0.0 or not 0.0 <= section_position_m <= span_m:
        raise ValueError("FLM3 span and section position are invalid.")
    if not 0.0 <= longitudinal_distribution_factor <= 1.0:
        raise ValueError("Fatigue transverse distribution factor must lie between 0 and 1.")
    if movement_steps < 2:
        raise ValueError("At least two FLM3 movement steps are required.")

    vehicle = fatigue_load_model_3(axle_load_factor=axle_load_factor)
    end = span_m + vehicle.axle_train.train_length_m
    minimum = 0.0
    maximum = 0.0
    governing_lead = 0.0
    for index in range(movement_steps):
        lead = end * index / (movement_steps - 1)
        loads = tuple(
            PointLoad(
                magnitude_kn=load.magnitude_kn * longitudinal_distribution_factor,
                position_m=load.position_m,
                label=load.label,
            )
            for load in positioned_axles(vehicle.axle_train, lead, span_m)
        )
        response = section_response(span_m, list(loads), section_position_m)
        if response.moment_knm > maximum:
            maximum = response.moment_knm
            governing_lead = lead
        minimum = min(minimum, response.moment_knm)
    return FLM3SimpleSpanSectionRange(
        section_position_m=section_position_m,
        minimum_moment_knm=minimum,
        maximum_moment_knm=maximum,
        moment_range_knm=maximum - minimum,
        governing_lead_position_m=governing_lead,
        movement_steps=movement_steps,
        status=(
            "Co-located EN 1991-2 FLM3 moving-vehicle moment range; transverse factor "
            "requires fatigue-specific validation and is not an LM1 factor"
        ),
    )
