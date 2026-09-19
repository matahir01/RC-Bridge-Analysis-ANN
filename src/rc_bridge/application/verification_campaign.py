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
from rc_bridge.application.action_combinations import IntegratedActionCombinationSuite
from rc_bridge.application.extended_actions import ExtendedActionSuite
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
    VerificationMaterial,
    VerificationModel,
    VerificationNode,
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


def _construction_stage_line_model(
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
                "independent simply-supported longitudinal girder lines matching "
                "the desktop construction-stage summary"
            ),
            "stiffness_basis": "physical section active at this construction stage",
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
                model = _construction_stage_line_model(project, extended_actions, stage)
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
