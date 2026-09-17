from __future__ import annotations

from bisect import bisect_right

from rc_bridge.analysis.moving_loads import AxleTrain, positioned_axles
from rc_bridge.codes.eurocode.materials import secant_elastic_modulus_mpa
from rc_bridge.core.models import DesignCode, ProjectInput, SupportSystem
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNode,
    VerificationPointLoad,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)
from rc_bridge.workflow.project_continuous import (
    GlobalBeamPointLoad,
    ProjectContinuousLoadCase,
)


def _elastic_modulus_mpa(project: ProjectInput) -> float:
    if project.materials.elastic_modulus_mpa is not None:
        return float(project.materials.elastic_modulus_mpa)
    if project.design_code == DesignCode.EUROCODE:
        return secant_elastic_modulus_mpa(float(project.materials.fck_mpa))
    raise ValueError(
        "Verification export requires explicit elastic_modulus_mpa for this design-code profile."
    )


def _analysis_areas(
    project: ProjectInput,
    span_count: int,
    supplied: tuple[float, ...] | None,
) -> tuple[float, ...]:
    if supplied is not None:
        if len(supplied) != span_count or any(value <= 0.0 for value in supplied):
            raise ValueError("analysis_area_m2_by_span must contain one positive value per span.")
        return supplied
    profile_area = project.geometry.girder_profile_area_m2
    if profile_area is None:
        raise ValueError(
            "Verification export needs a physical girder profile or explicit "
            "analysis_area_m2_by_span values. No artificial section area is inserted."
        )
    return tuple(float(profile_area) for _ in range(span_count))


def _map_global_load_to_member(
    span_lengths_m: tuple[float, ...],
    position_m: float,
) -> tuple[int, float]:
    boundaries = [0.0]
    for length in span_lengths_m:
        boundaries.append(boundaries[-1] + length)
    total = boundaries[-1]
    if position_m < 0.0 or position_m > total + 1e-9:
        raise ValueError("Global verification load position lies outside the bridge.")
    if abs(position_m - total) <= 1e-9:
        return len(span_lengths_m), span_lengths_m[-1]
    span_index = min(max(bisect_right(boundaries, position_m) - 1, 0), len(span_lengths_m) - 1)
    return span_index + 1, position_m - boundaries[span_index]


def build_project_continuous_verification_model(
    project: ProjectInput,
    load_case: ProjectContinuousLoadCase,
    *,
    analysis_area_m2_by_span: tuple[float, ...] | None = None,
    torsion_constant_m4_by_span: tuple[float, ...] | None = None,
) -> VerificationModel:
    """Convert one internal continuous-girder load case into an external verification model.

    The exported line model reproduces the longitudinal Euler-Bernoulli problem:
    span geometry, support continuity, explicit EI, UDLs and point loads. Transverse
    bridge/grillage action is deliberately outside this first exporter and remains
    a separate verification model.
    """
    if project.geometry.support_system != SupportSystem.CONTINUOUS:
        raise ValueError("Continuous verification export requires a CONTINUOUS project.")

    spans = tuple(float(value) for value in project.geometry.span_lengths_m)
    span_count = len(spans)
    if span_count < 2:
        raise ValueError("Continuous verification export requires at least two spans.")
    if len(load_case.ei_kn_m2_by_span) != span_count:
        raise ValueError("Verification EI vector must match the project span count.")
    if len(load_case.udl_kn_m_by_span) != span_count:
        raise ValueError("Verification UDL vector must match the project span count.")

    e_mpa = _elastic_modulus_mpa(project)
    e_kn_m2 = e_mpa * 1000.0
    areas = _analysis_areas(project, span_count, analysis_area_m2_by_span)
    vertical_inertias = tuple(value / e_kn_m2 for value in load_case.ei_kn_m2_by_span)
    if any(value <= 0.0 for value in vertical_inertias):
        raise ValueError("Derived section inertia must be positive.")

    if torsion_constant_m4_by_span is None:
        torsion = vertical_inertias
        torsion_note = "J defaults to the vertical bending I because torsion is restrained/not benchmarked."
    else:
        if len(torsion_constant_m4_by_span) != span_count or any(
            value <= 0.0 for value in torsion_constant_m4_by_span
        ):
            raise ValueError("torsion_constant_m4_by_span must contain one positive value per span.")
        torsion = torsion_constant_m4_by_span
        torsion_note = "Explicit torsion constants supplied by caller."

    x = 0.0
    nodes: list[VerificationNode] = [VerificationNode(1, 0.0, 0.0, 0.0)]
    for index, length in enumerate(spans, start=2):
        x += length
        nodes.append(VerificationNode(index, x, 0.0, 0.0))

    material = VerificationMaterial(
        material_id=1,
        name="VerificationConcrete",
        elastic_modulus_kn_m2=e_kn_m2,
        poisson_ratio=0.2,
        weight_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )
    sections = tuple(
        VerificationSection(
            section_id=index + 1,
            name=f"Span_{index + 1}_EI_Matched",
            area_m2=areas[index],
            torsion_constant_m4=torsion[index],
            iy_m4=vertical_inertias[index],
            iz_m4=vertical_inertias[index],
        )
        for index in range(span_count)
    )
    beams = tuple(
        VerificationBeam(
            member_id=index + 1,
            node_i=index + 1,
            node_j=index + 2,
            material_id=1,
            section_id=index + 1,
        )
        for index in range(span_count)
    )

    supports = [
        VerificationSupport(1, ux=True, uy=True, uz=True, rx=True),
    ]
    supports.extend(
        VerificationSupport(node_id=index + 1, uy=True, uz=True)
        for index in range(1, span_count + 1)
    )

    uniform_loads = tuple(
        VerificationUniformLoad(
            member_id=index + 1,
            direction="GZ",
            magnitude_kn_m=-float(load_case.udl_kn_m_by_span[index]),
        )
        for index in range(span_count)
        if load_case.udl_kn_m_by_span[index] != 0.0
    )
    point_loads: list[VerificationPointLoad] = []
    for load in load_case.point_loads:
        member_id, local_distance = _map_global_load_to_member(spans, load.position_m)
        point_loads.append(
            VerificationPointLoad(
                member_id=member_id,
                direction="GZ",
                magnitude_kn=-load.magnitude_kn,
                distance_from_i_m=local_distance,
            )
        )

    verification_case = VerificationLoadCase(
        load_case_id=1,
        name=load_case.name,
        uniform_loads=uniform_loads,
        point_loads=tuple(point_loads),
    )
    return VerificationModel(
        name=f"{project.name} - {load_case.name}",
        nodes=tuple(nodes),
        materials=(material,),
        sections=sections,
        beams=beams,
        supports=tuple(supports),
        load_cases=(verification_case,),
        metadata={
            "source": "RC-Bridge-Analysis-ANN",
            "purpose": "longitudinal_solver_verification",
            "design_code": project.design_code.value,
            "stiffness_basis": "section I derived exactly from caller-supplied EI / E",
            "self_weight_basis": "not activated; internal line loads exported explicitly",
            "transverse_distribution": "not represented in this line-model snapshot",
            "torsion_basis": torsion_note,
        },
    )


def build_moving_train_snapshot_verification_model(
    project: ProjectInput,
    *,
    train: AxleTrain,
    lead_position_m: float,
    ei_kn_m2_by_span: tuple[float, ...],
    udl_kn_m_by_span: tuple[float, ...] | None = None,
    analysis_area_m2_by_span: tuple[float, ...] | None = None,
    name: str = "governing moving-load snapshot",
) -> VerificationModel:
    """Export one exact moving-vehicle position as a static verification load case."""
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    axles = positioned_axles(train, lead_position_m, total_length)
    point_loads = tuple(
        GlobalBeamPointLoad(
            magnitude_kn=load.magnitude_kn,
            position_m=load.position_m,
            label=load.label,
        )
        for load in axles
    )
    udls = udl_kn_m_by_span or tuple(0.0 for _ in project.geometry.span_lengths_m)
    load_case = ProjectContinuousLoadCase(
        ei_kn_m2_by_span=ei_kn_m2_by_span,
        udl_kn_m_by_span=udls,
        point_loads=point_loads,
        name=name,
    )
    model = build_project_continuous_verification_model(
        project,
        load_case,
        analysis_area_m2_by_span=analysis_area_m2_by_span,
    )
    metadata = dict(model.metadata)
    metadata.update(
        {
            "moving_train_label": train.label,
            "lead_position_m": f"{lead_position_m:.12g}",
            "snapshot_type": "static_axle_position_from_internal_moving_load_solver",
        }
    )
    return VerificationModel(
        name=model.name,
        nodes=model.nodes,
        materials=model.materials,
        sections=model.sections,
        beams=model.beams,
        supports=model.supports,
        load_cases=model.load_cases,
        metadata=metadata,
    )
