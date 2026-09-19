from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from rc_bridge.analysis.physical_sections import (
    composite_girder_properties,
    deck_construction_girder_properties,
    girder_tributary_slab_widths_m,
    precast_girder_properties,
)
from rc_bridge.application.action_combinations import (
    BridgeActionCombinationFactors,
    IntegratedActionCombinationSuite,
)
from rc_bridge.application.extended_actions import ExtendedActionSettings, ExtendedActionSuite
from rc_bridge.application.fatigue import FatigueApplicationResult
from rc_bridge.application.local_deck import LocalDeckDesignResult
from rc_bridge.codes.eurocode.materials import secant_elastic_modulus_mpa
from rc_bridge.core.models import (
    DesignCode,
    PermanentActionStage,
    ProjectInput,
    SupportSystem,
)
from rc_bridge.export.model_verification_package import build_model_verification_export_package
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationLoadCombination,
    VerificationLoadCombinationTerm,
    VerificationMaterial,
    VerificationModel,
    VerificationNodalLoad,
    VerificationNode,
    VerificationPointLoad,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)
from rc_bridge.workflow.grillage_verification_export import (
    GrillageAreaLoad,
    GrillageVerificationLoadCase,
    build_project_grillage_verification_model,
)
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    build_consolidated_governing_lm1_verification_model,
)
from rc_bridge.workflow.lm1_grillage_verification import (
    build_project_lm1_grillage_verification_model,
)
from rc_bridge.workflow.project_bridge import girder_permanent_load_segments


@dataclass(frozen=True)
class WrittenCampaignModel:
    family: str
    label: str
    directory: Path
    files: tuple[Path, ...]


@dataclass(frozen=True)
class WrittenVerificationCampaign:
    directory: Path
    manifest_json: Path
    action_summary_json: Path
    models: tuple[WrittenCampaignModel, ...]

    @property
    def model_count(self) -> int:
        return len(self.models)

    @property
    def families(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.family for item in self.models))


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    if not stem:
        raise ValueError("Verification campaign name cannot be empty.")
    return stem


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _write_model(
    model: VerificationModel,
    directory: Path,
    *,
    family: str,
    label: str,
    base_name: str,
) -> WrittenCampaignModel:
    package = build_model_verification_export_package(model)
    directory.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for filename, content in package.files(_safe_stem(base_name)).items():
        path = directory / filename
        _write_text_atomic(path, content)
        files.append(path)
    return WrittenCampaignModel(
        family=family,
        label=label,
        directory=directory,
        files=tuple(sorted(files)),
    )


def _grid_stations(total_length_m: float, maximum_spacing_m: float) -> tuple[float, ...]:
    if total_length_m <= 0.0 or maximum_spacing_m <= 0.0:
        raise ValueError("Verification grid length and spacing must be positive.")
    values = {0.0, total_length_m}
    position = 0.0
    while position < total_length_m - 1.0e-12:
        values.add(round(position, 12))
        position += maximum_spacing_m
    return tuple(sorted(values))


def _girder_y_coordinates(project: ProjectInput) -> tuple[float, ...]:
    count = int(project.geometry.girder_count)
    width = float(project.geometry.deck_width_m)
    spacing = float(project.geometry.girder_spacing_m)
    first = -width / 2.0 + float(project.geometry.nominal_edge_overhang_m)
    return tuple(first + index * spacing for index in range(count))


def _elastic_modulus_kn_m2(project: ProjectInput) -> float:
    if project.materials.elastic_modulus_mpa is not None:
        return float(project.materials.elastic_modulus_mpa) * 1000.0
    if project.design_code is DesignCode.EUROCODE:
        return secant_elastic_modulus_mpa(float(project.materials.fck_mpa)) * 1000.0
    raise ValueError(
        "Verification campaign requires explicit elastic_modulus_mpa for this design code."
    )


def _all_permanent_reference_model(
    project: ProjectInput,
    *,
    grid_spacing_m: float,
) -> VerificationModel:
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    segments_by_girder = {
        girder_index: girder_permanent_load_segments(
            project,
            girder_index=girder_index,
        )
        for girder_index in range(1, int(project.geometry.girder_count) + 1)
    }
    stations = set(_grid_stations(total_length, grid_spacing_m))
    for segments in segments_by_girder.values():
        for segment in segments:
            stations.add(float(segment.x_start_m))
            stations.add(float(segment.x_end_m))

    base = build_project_grillage_verification_model(
        project,
        transverse_stations_m=tuple(sorted(stations)),
        load_case=GrillageVerificationLoadCase(
            name="all permanent actions final composite reference",
        ),
    )
    nodes = {node.node_id: node for node in base.nodes}
    girder_y = _girder_y_coordinates(project)
    loads: list[VerificationUniformLoad] = []
    for beam in base.beams:
        ni = nodes[beam.node_i]
        nj = nodes[beam.node_j]
        if abs(ni.y_m - nj.y_m) > 1.0e-9 or abs(ni.x_m - nj.x_m) <= 1.0e-12:
            continue
        girder_index = next(
            (
                index + 1
                for index, y_m in enumerate(girder_y)
                if abs(ni.y_m - y_m) <= 1.0e-9
            ),
            None,
        )
        if girder_index is None:
            continue
        midpoint = 0.5 * (ni.x_m + nj.x_m)
        magnitude = sum(
            segment.magnitude_kn_m
            for segment in segments_by_girder[girder_index]
            if segment.x_start_m - 1.0e-9 <= midpoint <= segment.x_end_m + 1.0e-9
        )
        if magnitude > 0.0:
            loads.append(
                VerificationUniformLoad(
                    member_id=beam.member_id,
                    direction="GZ",
                    magnitude_kn_m=-magnitude,
                )
            )

    metadata = {
        **base.metadata,
        "verification_export": "all_permanent_actions_final_composite_reference",
        "staging_warning": (
            "This model verifies the exact permanent load definition and equilibrium on "
            "the final composite grillage. Construction-stage response equivalence must "
            "be checked with the separate stage models in this campaign."
        ),
    }
    return replace(
        base,
        name=f"{project.name} - all permanent actions reference",
        load_cases=(
            VerificationLoadCase(
                load_case_id=1,
                name="all permanent actions final composite reference",
                uniform_loads=tuple(loads),
            ),
        ),
        metadata=metadata,
    )


def _construction_stage_physical_model(
    project: ProjectInput,
    actions: ExtendedActionSuite,
    stage: PermanentActionStage,
) -> VerificationModel | None:
    if actions.construction is None:
        return None
    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        return None
    if len(project.geometry.span_lengths_m) != 1:
        return None

    span_m = float(project.geometry.span_lengths_m[0])
    girder_count = int(project.geometry.girder_count)
    girder_y = _girder_y_coordinates(project)
    tributary_widths = girder_tributary_slab_widths_m(project.geometry)
    rows = {
        (row.girder_index, row.stage): row
        for row in actions.construction.girders
    }

    segments_by_girder = {
        girder_index: girder_permanent_load_segments(
            project,
            girder_index=girder_index,
            included_stages=(stage,),
        )
        for girder_index in range(1, girder_count + 1)
    }
    stations = {0.0, span_m}
    for segments in segments_by_girder.values():
        for segment in segments:
            stations.add(float(segment.x_start_m))
            stations.add(float(segment.x_end_m))
    x_values = tuple(sorted(stations))

    if stage is PermanentActionStage.SUPERIMPOSED:
        base = build_project_grillage_verification_model(
            project,
            transverse_stations_m=x_values,
            load_case=GrillageVerificationLoadCase(
                name="completed composite bridge - superimposed permanent actions",
            ),
        )
        nodes_by_id = {node.node_id: node for node in base.nodes}
        loads: list[VerificationUniformLoad] = []
        for beam in base.beams:
            ni = nodes_by_id[beam.node_i]
            nj = nodes_by_id[beam.node_j]
            if abs(ni.y_m - nj.y_m) > 1.0e-9 or nj.x_m <= ni.x_m + 1.0e-12:
                continue
            girder_index = next(
                (
                    index + 1
                    for index, y_m in enumerate(girder_y)
                    if abs(ni.y_m - y_m) <= 1.0e-9
                ),
                None,
            )
            if girder_index is None:
                continue
            midpoint = 0.5 * (ni.x_m + nj.x_m)
            magnitude = sum(
                segment.magnitude_kn_m
                for segment in segments_by_girder[girder_index]
                if (
                    segment.x_start_m - 1.0e-9
                    <= midpoint
                    <= segment.x_end_m + 1.0e-9
                )
            )
            if magnitude > 0.0:
                loads.append(
                    VerificationUniformLoad(
                        member_id=beam.member_id,
                        direction="GZ",
                        magnitude_kn_m=-magnitude,
                    )
                )
        return replace(
            base,
            name=f"{project.name} - completed composite construction stage",
            load_cases=(
                VerificationLoadCase(
                    load_case_id=1,
                    name="superimposed permanent actions on completed composite bridge",
                    uniform_loads=tuple(loads),
                ),
            ),
            metadata={
                **base.metadata,
                "source": "RC-Bridge-Analysis-ANN",
                "purpose": "construction_stage_application_verification",
                "construction_stage": stage.value,
                "structural_model": (
                    "completed physical final-stage bridge grillage with longitudinal "
                    "composite girders and transverse deck-strip members"
                ),
                "physical_presence": (
                    "precast girders + precast false slab + hardened in-situ deck present; "
                    "superimposed permanent actions applied to completed composite structure"
                ),
                "construction_history_boundary": (
                    "earlier girder/false-slab/wet-deck loads are not reapplied here; "
                    "their response belongs to the earlier construction increments"
                ),
                "stiffness_basis": "final hardened composite bridge section and deck grillage",
                "load_basis": "SUPERIMPOSED-stage permanent segments only",
            },
        )

    e_kn_m2 = _elastic_modulus_kn_m2(project)
    material = VerificationMaterial(
        material_id=1,
        name="VerificationConcrete",
        elastic_modulus_kn_m2=e_kn_m2,
        poisson_ratio=0.2,
        weight_density_kn_m3=float(project.materials.concrete_density_kn_m3),
    )

    sections: list[VerificationSection] = []
    for girder_index in range(1, girder_count + 1):
        if stage is PermanentActionStage.PRECAST_GIRDER:
            properties = precast_girder_properties(project.geometry)
        elif stage is PermanentActionStage.DECK_CONSTRUCTION:
            properties = deck_construction_girder_properties(
                project.geometry,
                slab_width_m=tributary_widths[girder_index - 1],
                false_slab_participates=(
                    project.geometry.deck_construction.false_slab_composite_participation
                ),
            )
        else:
            properties = composite_girder_properties(
                project.geometry,
                slab_width_m=tributary_widths[girder_index - 1],
                slab_width_basis="physical girder tributary width",
            )
        sections.append(
            VerificationSection(
                section_id=girder_index,
                name=f"{stage.value}_girder_{girder_index}",
                area_m2=properties.area_m2,
                torsion_constant_m4=properties.torsion_constant_m4,
                iy_m4=properties.iy_m4,
                iz_m4=properties.iz_m4,
            )
        )

    def node_id(girder_index: int, x_index: int) -> int:
        return (girder_index - 1) * len(x_values) + x_index + 1

    nodes = tuple(
        VerificationNode(
            node_id=node_id(girder_index, x_index),
            x_m=x_m,
            y_m=girder_y[girder_index - 1],
            z_m=0.0,
        )
        for girder_index in range(1, girder_count + 1)
        for x_index, x_m in enumerate(x_values)
    )
    beams: list[VerificationBeam] = []
    loads: list[VerificationUniformLoad] = []
    member_id = 1
    for girder_index in range(1, girder_count + 1):
        row = rows.get((girder_index, stage))
        execution_udl = 0.0 if row is None else float(row.execution_udl_kn_m)
        segments = segments_by_girder[girder_index]
        for x_index in range(len(x_values) - 1):
            x0 = x_values[x_index]
            x1 = x_values[x_index + 1]
            beams.append(
                VerificationBeam(
                    member_id=member_id,
                    node_i=node_id(girder_index, x_index),
                    node_j=node_id(girder_index, x_index + 1),
                    material_id=1,
                    section_id=girder_index,
                )
            )
            midpoint = 0.5 * (x0 + x1)
            magnitude = execution_udl + sum(
                segment.magnitude_kn_m
                for segment in segments
                if segment.x_start_m - 1.0e-9 <= midpoint <= segment.x_end_m + 1.0e-9
            )
            if magnitude > 0.0:
                loads.append(
                    VerificationUniformLoad(
                        member_id=member_id,
                        direction="GZ",
                        magnitude_kn_m=-magnitude,
                    )
                )
            member_id += 1

    supports: list[VerificationSupport] = []
    for girder_index in range(1, girder_count + 1):
        supports.append(
            VerificationSupport(
                node_id=node_id(girder_index, 0),
                ux=True,
                uy=True,
                uz=True,
            )
        )
        supports.append(
            VerificationSupport(
                node_id=node_id(girder_index, len(x_values) - 1),
                uy=True,
                uz=True,
            )
        )

    return VerificationModel(
        name=f"{project.name} - construction stage {stage.value}",
        nodes=nodes,
        materials=(material,),
        sections=tuple(sections),
        beams=tuple(beams),
        supports=tuple(supports),
        load_cases=(
            VerificationLoadCase(
                load_case_id=1,
                name=f"construction stage {stage.value}",
                uniform_loads=tuple(loads),
            ),
        ),
        metadata={
            "source": "RC-Bridge-Analysis-ANN",
            "purpose": "construction_stage_application_verification",
            "construction_stage": stage.value,
            "structural_model": (
                "independent longitudinal girder lines for the pre-final construction "
                "state; deck components that have not developed verified structural "
                "stiffness are represented as loads, not fictitious beam members"
            ),
            "physical_presence": (
                "precast girders present; precast false slab is present from the precast "
                "stage as permanent load; wet in-situ deck is present as load during the "
                "deck-construction stage but is not credited with hardened deck stiffness"
            ),
            "stiffness_basis": "physical longitudinal section active at this construction stage",
            "load_basis": "exact stage-tagged permanent segments plus explicit execution UDL",
        },
    )


def _vertical_wind_model(
    project: ProjectInput,
    actions: ExtendedActionSuite,
    *,
    grid_spacing_m: float,
) -> VerificationModel | None:
    wind = actions.wind
    if wind is None or abs(wind.vertical_pressure_kn_m2) <= 1.0e-12:
        return None
    total_length = sum(float(value) for value in project.geometry.span_lengths_m)
    half_width = 0.5 * float(project.geometry.deck_width_m)
    model = build_project_grillage_verification_model(
        project,
        transverse_stations_m=_grid_stations(total_length, grid_spacing_m),
        load_case=GrillageVerificationLoadCase(
            name="vertical wind characteristic",
            area_loads=(
                GrillageAreaLoad(
                    x_start_m=0.0,
                    x_end_m=total_length,
                    y_start_m=-half_width,
                    y_end_m=half_width,
                    pressure_kn_m2=abs(wind.vertical_pressure_kn_m2),
                    label="vertical wind pressure",
                ),
            ),
        ),
    )
    if wind.vertical_pressure_kn_m2 < 0.0:
        case = model.load_cases[0]
        case = replace(
            case,
            nodal_loads=tuple(
                replace(load, fz_kn=-load.fz_kn)
                for load in case.nodal_loads
            ),
        )
        model = replace(model, load_cases=(case,))
    return replace(
        model,
        name=f"{project.name} - vertical wind characteristic",
        metadata={
            **model.metadata,
            "verification_export": "vertical_wind_characteristic",
            "vertical_pressure_kn_m2": f"{wind.vertical_pressure_kn_m2:.12g}",
        },
    )



def _coordinate_key(x_m: float, y_m: float, z_m: float) -> tuple[float, float, float]:
    return (round(float(x_m), 10), round(float(y_m), 10), round(float(z_m), 10))


def _remap_load_case_to_common_model(
    source_model: VerificationModel,
    source_case: VerificationLoadCase,
    target_model: VerificationModel,
    *,
    load_case_id: int,
    name: str,
) -> VerificationLoadCase:
    """Map one exact static load case onto a geometrically richer common grillage mesh.

    The unified Stage-5 model is built from the union of every retained service-action
    grid line. Source nodal loads therefore map by exact coordinates. Member loads are
    split over collinear target members while preserving their physical loaded length
    and intensity. No load is smeared to a different girder or transverse line.
    """

    source_nodes = {node.node_id: node for node in source_model.nodes}
    source_beams = {beam.member_id: beam for beam in source_model.beams}
    target_nodes = {node.node_id: node for node in target_model.nodes}
    target_by_coordinate = {
        _coordinate_key(node.x_m, node.y_m, node.z_m): node.node_id
        for node in target_model.nodes
    }

    nodal: list[VerificationNodalLoad] = []
    for load in source_case.nodal_loads:
        node = source_nodes[load.node_id]
        target_id = target_by_coordinate.get(
            _coordinate_key(node.x_m, node.y_m, node.z_m)
        )
        if target_id is None:
            raise RuntimeError("Unified service mesh is missing a source nodal-load coordinate.")
        nodal.append(
            replace(
                load,
                node_id=target_id,
            )
        )

    uniform: list[VerificationUniformLoad] = []
    point: list[VerificationPointLoad] = []

    def target_members_on_line(
        *,
        longitudinal: bool,
        fixed_coordinate: float,
    ):
        rows = []
        for beam in target_model.beams:
            ni = target_nodes[beam.node_i]
            nj = target_nodes[beam.node_j]
            if longitudinal:
                if (
                    abs(ni.y_m - fixed_coordinate) <= 1.0e-9
                    and abs(nj.y_m - fixed_coordinate) <= 1.0e-9
                    and abs(nj.x_m - ni.x_m) > 1.0e-12
                ):
                    rows.append((beam, ni, nj))
            elif (
                abs(ni.x_m - fixed_coordinate) <= 1.0e-9
                and abs(nj.x_m - fixed_coordinate) <= 1.0e-9
                and abs(nj.y_m - ni.y_m) > 1.0e-12
            ):
                rows.append((beam, ni, nj))
        return rows

    for load in source_case.uniform_loads:
        beam = source_beams[load.member_id]
        ni = source_nodes[beam.node_i]
        nj = source_nodes[beam.node_j]
        length = source_model.member_length_m(beam.member_id)
        start = 0.0 if load.start_m is None else float(load.start_m)
        end = length if load.end_m is None else float(load.end_m)
        if abs(nj.x_m - ni.x_m) > 1.0e-12 and abs(nj.y_m - ni.y_m) <= 1.0e-9:
            sign = 1.0 if nj.x_m > ni.x_m else -1.0
            x0 = ni.x_m + sign * start
            x1 = ni.x_m + sign * end
            lo, hi = sorted((x0, x1))
            candidates = target_members_on_line(
                longitudinal=True,
                fixed_coordinate=ni.y_m,
            )
            for target_beam, ti, tj in candidates:
                member_lo, member_hi = sorted((ti.x_m, tj.x_m))
                overlap_lo = max(lo, member_lo)
                overlap_hi = min(hi, member_hi)
                if overlap_hi <= overlap_lo + 1.0e-12:
                    continue
                if tj.x_m >= ti.x_m:
                    local_start = overlap_lo - ti.x_m
                    local_end = overlap_hi - ti.x_m
                else:
                    local_start = ti.x_m - overlap_hi
                    local_end = ti.x_m - overlap_lo
                uniform.append(
                    VerificationUniformLoad(
                        member_id=target_beam.member_id,
                        direction=load.direction,
                        magnitude_kn_m=load.magnitude_kn_m,
                        start_m=local_start,
                        end_m=local_end,
                    )
                )
        elif abs(nj.y_m - ni.y_m) > 1.0e-12 and abs(nj.x_m - ni.x_m) <= 1.0e-9:
            sign = 1.0 if nj.y_m > ni.y_m else -1.0
            y0 = ni.y_m + sign * start
            y1 = ni.y_m + sign * end
            lo, hi = sorted((y0, y1))
            candidates = target_members_on_line(
                longitudinal=False,
                fixed_coordinate=ni.x_m,
            )
            for target_beam, ti, tj in candidates:
                member_lo, member_hi = sorted((ti.y_m, tj.y_m))
                overlap_lo = max(lo, member_lo)
                overlap_hi = min(hi, member_hi)
                if overlap_hi <= overlap_lo + 1.0e-12:
                    continue
                if tj.y_m >= ti.y_m:
                    local_start = overlap_lo - ti.y_m
                    local_end = overlap_hi - ti.y_m
                else:
                    local_start = ti.y_m - overlap_hi
                    local_end = ti.y_m - overlap_lo
                uniform.append(
                    VerificationUniformLoad(
                        member_id=target_beam.member_id,
                        direction=load.direction,
                        magnitude_kn_m=load.magnitude_kn_m,
                        start_m=local_start,
                        end_m=local_end,
                    )
                )
        else:
            raise RuntimeError(
                "Unified Stage-5 remapping currently requires horizontal orthogonal "
                "grillage members."
            )

    for load in source_case.point_loads:
        beam = source_beams[load.member_id]
        ni = source_nodes[beam.node_i]
        nj = source_nodes[beam.node_j]
        length = source_model.member_length_m(beam.member_id)
        ratio = 0.0 if length <= 0.0 else load.distance_from_i_m / length
        x = ni.x_m + ratio * (nj.x_m - ni.x_m)
        y = ni.y_m + ratio * (nj.y_m - ni.y_m)
        z = ni.z_m + ratio * (nj.z_m - ni.z_m)
        exact_node = target_by_coordinate.get(_coordinate_key(x, y, z))
        if exact_node is not None and load.direction in {"GX", "GY", "GZ"}:
            kwargs = {
                "fx_kn": load.magnitude_kn if load.direction == "GX" else 0.0,
                "fy_kn": load.magnitude_kn if load.direction == "GY" else 0.0,
                "fz_kn": load.magnitude_kn if load.direction == "GZ" else 0.0,
            }
            nodal.append(VerificationNodalLoad(node_id=exact_node, **kwargs))
            continue

        longitudinal = abs(nj.x_m - ni.x_m) > 1.0e-12
        candidates = target_members_on_line(
            longitudinal=longitudinal,
            fixed_coordinate=ni.y_m if longitudinal else ni.x_m,
        )
        found = False
        for target_beam, ti, tj in candidates:
            if longitudinal:
                lo, hi = sorted((ti.x_m, tj.x_m))
                coordinate = x
                if not (lo - 1.0e-9 <= coordinate <= hi + 1.0e-9):
                    continue
                distance = (
                    coordinate - ti.x_m
                    if tj.x_m >= ti.x_m
                    else ti.x_m - coordinate
                )
            else:
                lo, hi = sorted((ti.y_m, tj.y_m))
                coordinate = y
                if not (lo - 1.0e-9 <= coordinate <= hi + 1.0e-9):
                    continue
                distance = (
                    coordinate - ti.y_m
                    if tj.y_m >= ti.y_m
                    else ti.y_m - coordinate
                )
            point.append(
                VerificationPointLoad(
                    member_id=target_beam.member_id,
                    direction=load.direction,
                    magnitude_kn=load.magnitude_kn,
                    distance_from_i_m=max(distance, 0.0),
                )
            )
            found = True
            break
        if not found:
            raise RuntimeError("Unified service mesh could not locate a source point load.")

    return VerificationLoadCase(
        load_case_id=load_case_id,
        name=name,
        self_weight_gz_factor=source_case.self_weight_gz_factor,
        uniform_loads=tuple(uniform),
        point_loads=tuple(point),
        nodal_loads=tuple(nodal),
    )


def build_unified_final_service_verification_model(
    project: ProjectInput,
    lm1: ProjectNativeLM1GrillageSearchResult,
    actions: ExtendedActionSuite,
    *,
    action_settings: ExtendedActionSettings,
    combination_factors: BridgeActionCombinationFactors,
    grid_spacing_m: float,
) -> VerificationModel:
    """Build one completed-bridge model containing the global in-service vertical actions.

    For the current simple-span application profile, permanent force effects are
    statically determinate, so the final-composite permanent load case reproduces
    staged reactions/M/V even though staged deflection must still be checked from the
    construction-stage results. Continuous-span permanent redistribution is therefore
    rejected here until a genuine construction-stage external-result combination is
    implemented rather than being silently approximated.
    """

    if project.geometry.support_system is not SupportSystem.SIMPLY_SUPPORTED:
        raise ValueError(
            "Unified Stage-5 verification currently requires a simply-supported bridge; "
            "continuous bridges need construction-stage result combination rather than "
            "reapplying all permanent loads to final stiffness."
        )
    if len(project.geometry.span_lengths_m) != 1:
        raise ValueError(
            "Unified Stage-5 verification currently requires one simple span."
        )

    permanent = _all_permanent_reference_model(
        project,
        grid_spacing_m=grid_spacing_m,
    )
    characteristic_lm1 = build_consolidated_governing_lm1_verification_model(
        project,
        lm1,
    )

    source_groups: list[tuple[str, VerificationModel]] = [
        ("permanent", permanent),
        ("lm1", characteristic_lm1),
    ]
    if actions.gr2_frequent_lm1 is not None:
        source_groups.append(
            (
                "gr2",
                build_consolidated_governing_lm1_verification_model(
                    project,
                    actions.gr2_frequent_lm1.search,
                ),
            )
        )
    if actions.pedestrian is not None and actions.pedestrian.applied:
        if actions.pedestrian.model is None:
            raise RuntimeError("Pedestrian result is missing its analysed grillage model.")
        source_groups.append(("pedestrian", actions.pedestrian.model))
    if actions.lm2 is not None:
        source_groups.extend(
            ("lm2", model) for model in actions.lm2.governing_models
        )
    wind = _vertical_wind_model(
        project,
        actions,
        grid_spacing_m=grid_spacing_m,
    )
    if wind is not None:
        source_groups.append(("wind", wind))

    x_stations = tuple(
        sorted(
            {
                round(float(node.x_m), 12)
                for _, model in source_groups
                for node in model.nodes
            }
        )
    )
    y_stations = tuple(
        sorted(
            {
                round(float(node.y_m), 12)
                for _, model in source_groups
                for node in model.nodes
            }
        )
    )
    base = build_project_grillage_verification_model(
        project,
        transverse_stations_m=x_stations,
        additional_transverse_y_m=y_stations,
        load_case=GrillageVerificationLoadCase(name="Stage 5 common final-service mesh"),
    )

    load_cases: list[VerificationLoadCase] = []
    case_groups: dict[str, list[int]] = {}
    case_identity: list[dict[str, object]] = []
    next_case_id = 1
    for group, model in source_groups:
        for source_case in model.load_cases:
            case_id = next_case_id
            next_case_id += 1
            name = f"{group.upper()}_{source_case.name}"
            remapped = _remap_load_case_to_common_model(
                model,
                source_case,
                base,
                load_case_id=case_id,
                name=name,
            )
            load_cases.append(remapped)
            case_groups.setdefault(group, []).append(case_id)
            case_identity.append(
                {
                    "stage5_case_id": case_id,
                    "group": group,
                    "source_case_id": source_case.load_case_id,
                    "source_case_name": source_case.name,
                }
            )

    permanent_id = case_groups["permanent"][0]
    combinations: list[VerificationLoadCombination] = []
    next_combination_id = 10001

    def add_combination(
        name: str,
        terms: tuple[tuple[int, float], ...],
        *,
        category: str,
        description: str,
    ) -> None:
        nonlocal next_combination_id
        combinations.append(
            VerificationLoadCombination(
                combination_id=next_combination_id,
                name=name,
                terms=tuple(
                    VerificationLoadCombinationTerm(load_case_id=case_id, factor=factor)
                    for case_id, factor in terms
                    if abs(factor) > 1.0e-12
                ),
                category=category,
                description=description,
            )
        )
        next_combination_id += 1

    gamma_g = combination_factors.uls.gamma_g_unfavourable
    gamma_q = combination_factors.uls.gamma_q_traffic
    pedestrian_ratio = 0.0
    pedestrian_ids = case_groups.get("pedestrian", [])
    if pedestrian_ids and action_settings.pedestrian_load_kn_m2 > 0.0:
        pedestrian_ratio = min(
            action_settings.pedestrian_reduced_with_lm1_kn_m2
            / action_settings.pedestrian_load_kn_m2,
            1.0,
        )

    for index, case_id in enumerate(case_groups.get("lm1", ()), start=1):
        extra = (
            ((pedestrian_ids[0], gamma_q * pedestrian_ratio),)
            if pedestrian_ids and pedestrian_ratio > 0.0
            else ()
        )
        add_combination(
            f"ULS_GR1A_{index:02d}",
            ((permanent_id, gamma_g), (case_id, gamma_q), *extra),
            category="ULS",
            description="gr1a LM1 leading plus reduced pedestrian footway",
        )
        extra_sls = (
            ((pedestrian_ids[0], pedestrian_ratio),)
            if pedestrian_ids and pedestrian_ratio > 0.0
            else ()
        )
        add_combination(
            f"SLS_CHAR_GR1A_{index:02d}",
            ((permanent_id, 1.0), (case_id, 1.0), *extra_sls),
            category="SLS characteristic",
            description="gr1a characteristic service combination",
        )

    for index, case_id in enumerate(case_groups.get("gr2", ()), start=1):
        add_combination(
            f"ULS_GR2_VERTICAL_{index:02d}",
            ((permanent_id, gamma_g), (case_id, gamma_q)),
            category="ULS",
            description="gr2 vertical frequent-LM1 component; braking checked at bearings",
        )
        add_combination(
            f"SLS_FREQ_GR1A_{index:02d}",
            ((permanent_id, 1.0), (case_id, 1.0)),
            category="SLS frequent",
            description="frequent LM1 vertical component",
        )

    for index, case_id in enumerate(case_groups.get("lm2", ()), start=1):
        add_combination(
            f"ULS_GR1B_{index:02d}",
            ((permanent_id, gamma_g), (case_id, gamma_q)),
            category="ULS",
            description="gr1b LM2 isolated axle",
        )
        add_combination(
            f"SLS_CHAR_GR1B_{index:02d}",
            ((permanent_id, 1.0), (case_id, 1.0)),
            category="SLS characteristic",
            description="gr1b characteristic LM2",
        )
        add_combination(
            f"SLS_FREQ_GR1B_{index:02d}",
            (
                (permanent_id, 1.0),
                (case_id, combination_factors.psi1_lm2),
            ),
            category="SLS frequent",
            description="gr1b frequent LM2",
        )

    if pedestrian_ids:
        add_combination(
            "ULS_GR3_PEDESTRIAN",
            ((permanent_id, gamma_g), (pedestrian_ids[0], gamma_q)),
            category="ULS",
            description="gr3 pedestrian footway leading",
        )
        add_combination(
            "SLS_CHAR_GR3_PEDESTRIAN",
            ((permanent_id, 1.0), (pedestrian_ids[0], 1.0)),
            category="SLS characteristic",
            description="gr3 characteristic pedestrian footway",
        )

    for index, case_id in enumerate(case_groups.get("wind", ()), start=1):
        add_combination(
            f"ULS_VERTICAL_WIND_{index:02d}",
            (
                (permanent_id, gamma_g),
                (case_id, combination_factors.gamma_q_nontraffic),
            ),
            category="ULS",
            description="vertical wind leading",
        )
        add_combination(
            f"SLS_CHAR_VERTICAL_WIND_{index:02d}",
            ((permanent_id, 1.0), (case_id, 1.0)),
            category="SLS characteristic",
            description="vertical wind characteristic",
        )

    add_combination(
        "SLS_QUASI_PERMANENT_G",
        ((permanent_id, 1.0),),
        category="SLS quasi-permanent",
        description="permanent actions only for current traffic psi2 basis",
    )

    metadata = {
        **base.metadata,
        "verification_export": "unified_stage5_final_service",
        "service_model_scope": (
            "completed final composite bridge; global vertical service actions and "
            "Eurocode application combinations represented as static cases/combinations"
        ),
        "construction_history": (
            "simple-span reactions/M/V from permanent actions are statically determinate; "
            "staged permanent deflection remains verified from construction-stage models "
            "and is not replaced by the final-stiffness permanent displacement"
        ),
        "horizontal_action_boundary": (
            "braking, transverse wind and thermal restraint/movement remain bearing/"
            "restraint verification actions; they are not fabricated as vertical-grillage loads"
        ),
        "case_identity": json.dumps(case_identity, sort_keys=True),
        "combination_basis": (
            "gr1a characteristic LM1 plus reduced footway; gr1b LM2; gr2 vertical "
            "frequent-LM1 component with braking checked separately; gr3 pedestrian; "
            "vertical wind; ULS/SLS factors from persisted application design basis"
        ),
    }
    model = replace(
        base,
        name=f"{project.name} - Stage 5 unified final-service verification",
        load_cases=tuple(load_cases),
        load_combinations=tuple(combinations),
        metadata=metadata,
    )
    model.validate_load_positions()
    return model


def _selected_flm3_case_models(
    fatigue: FatigueApplicationResult | None,
) -> tuple[tuple[int, VerificationModel], ...]:
    if fatigue is None:
        return ()
    selected: set[int] = set()
    for row in fatigue.search.girders:
        if row.minimum_case_id is not None:
            selected.add(row.minimum_case_id)
        if row.maximum_case_id is not None:
            selected.add(row.maximum_case_id)
    for row in fatigue.search.shears:
        if row.minimum_case_id is not None:
            selected.add(row.minimum_case_id)
        if row.maximum_case_id is not None:
            selected.add(row.maximum_case_id)
    by_id = {case.case_id: case.model for case in fatigue.search.cases}
    return tuple(
        (case_id, by_id[case_id])
        for case_id in sorted(selected)
        if case_id in by_id
    )


def _effects_dict(effects) -> dict[str, float]:
    return {
        "moment_knm": float(effects.moment_knm),
        "shear_kn": float(effects.shear_kn),
        "torsion_knm": float(effects.torsion_knm),
    }


def _action_summary(
    actions: ExtendedActionSuite | None,
    combinations: IntegratedActionCombinationSuite | None,
    local_deck: LocalDeckDesignResult | None,
) -> dict[str, object]:
    summary: dict[str, object] = {}
    if actions is not None:
        if actions.braking is not None:
            item = actions.braking
            summary["braking_acceleration"] = {
                "characteristic_force_kn": item.characteristic_force_kn,
                "uncapped_force_kn": item.uncapped_force_kn,
                "minimum_force_kn": item.minimum_force_kn,
                "maximum_force_kn": item.maximum_force_kn,
                "loaded_length_m": item.loaded_length_m,
                "status": item.status,
                "external_check": "scalar action and bearing/restraint resultant",
            }
        if actions.thermal is not None:
            item = actions.thermal
            summary["thermal"] = {
                "expansion_movement_mm": item.expansion_movement_mm,
                "contraction_movement_mm": item.contraction_movement_mm,
                "heat_gradient_curvature_per_m": item.heat_gradient_curvature_per_m,
                "cool_gradient_curvature_per_m": item.cool_gradient_curvature_per_m,
                "modelled_restraint_expansion_force_kn": item.modelled_restraint_expansion_force_kn,
                "modelled_restraint_contraction_force_kn": item.modelled_restraint_contraction_force_kn,
                "status": item.status,
                "external_check": (
                    "scalar/kinematic check; current beam verification schema has no "
                    "temperature-gradient load primitive"
                ),
            }
        if actions.wind is not None:
            item = actions.wind
            summary["wind"] = {
                "basic_velocity_m_s": item.basic_velocity_m_s,
                "effective_pressure_kn_m2": item.effective_pressure_kn_m2,
                "transverse_characteristic_force_kn": item.transverse_characteristic_force_kn,
                "transverse_line_load_kn_m": item.transverse_line_load_kn_m,
                "vertical_characteristic_force_kn": item.vertical_characteristic_force_kn,
                "vertical_pressure_kn_m2": item.vertical_pressure_kn_m2,
                "overturning_reference_moment_knm": item.overturning_reference_moment_knm,
                "status": item.status,
                "external_check": (
                    "vertical component exported as a grillage model when non-zero; "
                    "transverse resultant retained here for bearing/lateral-restraint check"
                ),
            }
        if actions.barrier_impact is not None:
            item = actions.barrier_impact
            summary["barrier_accidental"] = {
                "transverse_characteristic_force_kn": item.transverse_characteristic_force_kn,
                "accompanying_vertical_wheel_load_kn": item.accompanying_vertical_wheel_load_kn,
                "barrier_base_moment_knm": item.barrier_base_moment_knm,
                "status": item.status,
                "external_check": "local restraint/deck-edge scalar demand",
            }
        if actions.pedestrian is not None:
            summary["pedestrian"] = {
                "applied": actions.pedestrian.applied,
                "loaded_area_m2": actions.pedestrian.loaded_area_m2,
                "total_characteristic_load_kn": actions.pedestrian.total_characteristic_load_kn,
                "status": actions.pedestrian.status,
            }
        if actions.lm2 is not None:
            summary["lm2"] = {
                "evaluated_case_count": actions.lm2.evaluated_case_count,
                "wheel_load_kn": actions.lm2.wheel_load_kn,
                "axle_load_kn": actions.lm2.axle_load_kn,
                "contact_pressure_kn_m2": actions.lm2.contact_pressure_kn_m2,
                "governing_export_model_count": len(actions.lm2.governing_models),
                "status": actions.lm2.status,
            }

    if combinations is not None:
        summary["integrated_action_combinations"] = {
            "girders": [
                {
                    "girder_index": row.girder_index,
                    "permanent": _effects_dict(row.permanent),
                    "governing_uls_moment_situation": row.governing_uls_moment_situation,
                    "governing_uls_shear_situation": row.governing_uls_shear_situation,
                    "governing_uls_torsion_situation": row.governing_uls_torsion_situation,
                    "situations": [
                        {
                            "name": situation.name,
                            "group": situation.group,
                            "variable_effects": _effects_dict(situation.variable_effects),
                            "uls_effects": _effects_dict(situation.uls_effects),
                            "characteristic_sls_effects": _effects_dict(
                                situation.characteristic_sls_effects
                            ),
                            "frequent_sls_effects": _effects_dict(
                                situation.frequent_sls_effects
                            ),
                            "quasi_permanent_sls_effects": _effects_dict(
                                situation.quasi_permanent_sls_effects
                            ),
                            "basis": situation.basis,
                        }
                        for situation in row.situations
                    ],
                }
                for row in combinations.girders
            ],
            "blockers": list(combinations.blockers),
        }
        if combinations.bearing is not None:
            bearing = combinations.bearing
            summary["bearing_restraint"] = {
                "persistent_uls_total_longitudinal_kn": bearing.persistent_uls_total_longitudinal_kn,
                "persistent_uls_per_bearing_kn": bearing.persistent_uls_per_bearing_kn,
                "persistent_uls_total_transverse_kn": bearing.persistent_uls_total_transverse_kn,
                "persistent_uls_transverse_per_bearing_kn": bearing.persistent_uls_transverse_per_bearing_kn,
                "required_movement_mm": bearing.required_movement_mm,
                "governing_situation": bearing.persistent_uls_governing_situation,
                "status": bearing.status,
            }

    if local_deck is not None:
        summary["local_deck"] = {
            "lm2_case_count": local_deck.lm2_case_count,
            "lm2_governing_axle_centre_y_m": local_deck.lm2_governing_axle_centre_y_m,
            "uls_positive_moment_knm_per_m": local_deck.uls_positive_moment_knm_per_m,
            "uls_negative_moment_knm_per_m": local_deck.uls_negative_moment_knm_per_m,
            "accidental_positive_moment_knm_per_m": local_deck.accidental_positive_moment_knm_per_m,
            "accidental_negative_moment_knm_per_m": local_deck.accidental_negative_moment_knm_per_m,
            "one_way_shear_design_kn_per_m": local_deck.one_way_shear.design_shear_kn_per_m,
            "status": local_deck.status,
            "external_check": (
                "native one-metre transverse strip result summary; it is intentionally "
                "not mislabeled as a general two-way plate FE model"
            ),
        }
    return summary


def write_application_verification_campaign(
    project: ProjectInput,
    lm1: ProjectNativeLM1GrillageSearchResult,
    directory: str | Path,
    *,
    extended_actions: ExtendedActionSuite | None = None,
    action_combinations: IntegratedActionCombinationSuite | None = None,
    local_deck: LocalDeckDesignResult | None = None,
    fatigue: FatigueApplicationResult | None = None,
    grid_spacing_m: float = 1.0,
    base_name: str = "application_verification",
) -> WrittenVerificationCampaign:
    """Write the complete independent-verification campaign available from the app.

    Exact MIDAS/STAAD packages are written for every action whose native analysis
    already has an explicit structural model. Scalar/kinematic action families that
    do not map honestly onto the current vertical beam/grillage schema are included
    in action_summary.json rather than being silently omitted or fabricated.
    """

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(base_name)
    written: list[WrittenCampaignModel] = []

    lm1_model = build_consolidated_governing_lm1_verification_model(project, lm1)
    written.append(
        _write_model(
            lm1_model,
            root / "lm1_characteristic",
            family="LM1 characteristic",
            label="consolidated governing LM1",
            base_name=f"{stem}_lm1_characteristic",
        )
    )

    permanent_model = _all_permanent_reference_model(
        project,
        grid_spacing_m=grid_spacing_m,
    )
    written.append(
        _write_model(
            permanent_model,
            root / "permanent_actions",
            family="permanent actions",
            label="all permanent actions final-composite reference",
            base_name=f"{stem}_permanent_reference",
        )
    )

    if extended_actions is not None:
        if extended_actions.gr2_frequent_lm1 is not None:
            gr2_model = build_consolidated_governing_lm1_verification_model(
                project,
                extended_actions.gr2_frequent_lm1.search,
            )
            written.append(
                _write_model(
                    gr2_model,
                    root / "gr2_frequent_lm1",
                    family="gr2 frequent LM1",
                    label="consolidated governing gr2 frequent LM1",
                    base_name=f"{stem}_gr2_frequent_lm1",
                )
            )

        pedestrian = extended_actions.pedestrian
        if pedestrian is not None and pedestrian.applied and pedestrian.model is not None:
            written.append(
                _write_model(
                    pedestrian.model,
                    root / "pedestrian",
                    family="pedestrian",
                    label="characteristic footway loading",
                    base_name=f"{stem}_pedestrian",
                )
            )

        lm2 = extended_actions.lm2
        if lm2 is not None:
            for index, model in enumerate(lm2.governing_models, start=1):
                case_id = model.load_cases[0].load_case_id
                written.append(
                    _write_model(
                        model,
                        root / "lm2" / f"case_{case_id:04d}",
                        family="LM2",
                        label=f"governing LM2 case {case_id}",
                        base_name=f"{stem}_lm2_case_{case_id:04d}_{index:02d}",
                    )
                )

        wind_model = _vertical_wind_model(
            project,
            extended_actions,
            grid_spacing_m=grid_spacing_m,
        )
        if wind_model is not None:
            written.append(
                _write_model(
                    wind_model,
                    root / "wind_vertical",
                    family="vertical wind",
                    label="characteristic vertical wind",
                    base_name=f"{stem}_wind_vertical",
                )
            )

        if extended_actions.construction is not None:
            for stage in PermanentActionStage:
                model = _construction_stage_physical_model(project, extended_actions, stage)
                if model is None:
                    continue
                written.append(
                    _write_model(
                        model,
                        root / "construction" / stage.value,
                        family="construction stage",
                        label=stage.value,
                        base_name=f"{stem}_construction_{stage.value}",
                    )
                )

    for case_id, model in _selected_flm3_case_models(fatigue):
        written.append(
            _write_model(
                model,
                root / "flm3" / f"case_{case_id:04d}",
                family="FLM3 fatigue",
                label=f"governing FLM3 range case {case_id}",
                base_name=f"{stem}_flm3_case_{case_id:04d}",
            )
        )

    action_summary = _action_summary(
        extended_actions,
        action_combinations,
        local_deck,
    )
    action_summary_path = root / f"{stem}_action_summary.json"
    _write_text_atomic(
        action_summary_path,
        json.dumps(action_summary, indent=2, sort_keys=True),
    )

    family_counts: dict[str, int] = {}
    for item in written:
        family_counts[item.family] = family_counts.get(item.family, 0) + 1

    manifest = {
        "schema_version": 1,
        "campaign_type": "application_independent_verification",
        "project_name": project.name,
        "model_count": len(written),
        "family_counts": family_counts,
        "model_packages": [
            {
                "family": item.family,
                "label": item.label,
                "directory": str(item.directory.relative_to(root)),
                "files": [path.name for path in item.files],
            }
            for item in written
        ],
        "coverage": {
            "exact_external_structural_models": [
                "LM1 characteristic governing cases",
                "all permanent action load definition on final composite grillage",
                "gr2 frequent LM1 governing cases when enabled",
                "pedestrian footway grillage when applicable",
                "LM2 governing M/V/T axle placements",
                "vertical wind grillage when a non-zero vertical coefficient is supplied",
                "simple-span construction-stage longitudinal girder models",
                "FLM3 governing minimum/maximum moment/shear range cases",
            ],
            "scalar_or_kinematic_verification_records": [
                "braking/acceleration resultant",
                "thermal movement/gradient/restraint resultants",
                "transverse wind bearing/restraint resultant",
                "barrier accidental local demand",
                "integrated traffic-group/ULS/SLS combination summaries",
                "local one-metre transverse deck-strip result summary",
            ],
        },
        "important_boundary": (
            "No action family is silently omitted. Structural models are exported only "
            "where the application has an honest matching beam/grillage representation. "
            "Scalar/kinematic/local-strip actions remain explicit in action_summary.json "
            "instead of being fabricated as unrelated grillage load cases."
        ),
    }
    manifest_path = root / f"{stem}_campaign_manifest.json"
    _write_text_atomic(
        manifest_path,
        json.dumps(manifest, indent=2, sort_keys=True),
    )
    return WrittenVerificationCampaign(
        directory=root,
        manifest_json=manifest_path,
        action_summary_json=action_summary_path,
        models=tuple(written),
    )
