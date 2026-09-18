"""Analytical/software tests; these are not external construction validation."""

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from rc_bridge.analysis.grillage_solver import solve_vertical_grillage
from rc_bridge.core.models import (
    BridgeGeometry,
    DesignCode,
    MaterialProperties,
    PermanentActionModel,
    PermanentActionStage,
    PermanentLineAction,
    PermanentLineActionCategory,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
    SupportSystem,
    SurfacingLayer,
)
from rc_bridge.export.midas_mct import export_midas_mct
from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.workflow.grillage_verification_export import GrillageSectionProperties
from rc_bridge.workflow.project_bridge import UniformPermanentLoadInput
from rc_bridge.workflow.project_construction import (
    PermanentGrillageStageInput,
    build_construction_stage_verification_packages,
    run_project_construction_grillage,
)


def _project(*, continuous: bool = False) -> ProjectInput:
    # Equal physical strips and symmetric loading reduce this TEST grillage to
    # independent line-beam closed forms. This is not the research baseline.
    return ProjectInput(
        geometry=BridgeGeometry(
            span_lengths_m=[10.0, 10.0] if continuous else [10.0],
            support_system=SupportSystem.CONTINUOUS
            if continuous
            else SupportSystem.SIMPLY_SUPPORTED,
            deck_width_m=6.0,
            carriageway_width_m=6.0,
            girder_count=3,
            girder_spacing_m=2.0,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.3, depth_m=0.95),
        ),
        permanent_actions=PermanentActionModel(
            surfacing_layers=[
                SurfacingLayer(
                    name="test uniform surfacing",
                    thickness_m=0.08,
                    density_kn_m3=24.0,
                    y_start_m=-3.0,
                    y_end_m=3.0,
                )
            ]
        ),
    )


def _stages() -> tuple[PermanentGrillageStageInput, ...]:
    transverse = GrillageSectionProperties("test equivalent cross-beam", 0.2, 0.005, 0.002, 0.002)
    return tuple(
        PermanentGrillageStageInput(
            stage=stage,
            basis="Symmetric analytical test only; identical cross-members at each mesh station",
            transverse_section=transverse if stage != PermanentActionStage.SUPERIMPOSED else None,
        )
        for stage in PermanentActionStage
    )


def _run(project: ProjectInput | None = None, **kwargs):
    project = project or _project()
    return run_project_construction_grillage(
        project,
        stages=kwargs.pop("stages", _stages()),
        transverse_stations_m=(5.0, 15.0) if len(project.geometry.span_lengths_m) == 2 else (5.0,),
        unchanged_supports_and_continuity_basis=kwargs.pop(
            "unchanged_supports_and_continuity_basis",
            "Analytical test: all supports and continuity present before first load",
        ),
        **kwargs,
    )


def test_stage_deflections_match_closed_forms_using_each_stages_actual_ei() -> None:
    result = _run()
    q_stages = (0.3 * 0.95 * 25.0, 2.0 * 0.25 * 25.0, 2.0 * 0.08 * 24.0)
    expected_cumulative = 0.0
    for stage, q in zip(result.stages, q_stages, strict=True):
        model = stage.model
        mid = next(n for n in model.nodes if n.x_m == 5.0 and n.y_m == 0.0)
        response = next(n for n in stage.increment.nodes if n.node_id == mid.node_id)
        ei = model.materials[0].elastic_modulus_kn_m2 * model.sections[0].iy_m4
        expected = -5.0 * q * 10.0**4 / (384.0 * ei)
        expected_cumulative += expected
        assert response.vertical_displacement_m == pytest.approx(expected)
        total_mid = next(n for n in stage.cumulative.nodes if n.node_id == mid.node_id)
        assert total_mid.vertical_displacement_m == pytest.approx(expected_cumulative)
        assert stage.increment.total_applied_vertical_load_kn == pytest.approx(-3.0 * q * 10.0)
        assert stage.increment.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1e-8)
        assert model.load_cases[0].self_weight_gz_factor == 0.0
    assert result.stages[0].model.sections[0].iy_m4 == result.stages[1].model.sections[0].iy_m4
    assert result.stages[2].model.sections[0].iy_m4 > result.stages[1].model.sections[0].iy_m4
    final_ei = (
        result.stages[-1].model.materials[0].elastic_modulus_kn_m2
        * result.stages[-1].model.sections[0].iy_m4
    )
    wrong_final_stiffness_deflection = -5.0 * sum(q_stages) * 10.0**4 / (384.0 * final_ei)
    assert abs(expected_cumulative) > abs(wrong_final_stiffness_deflection)
    assert result.final_response.total_vertical_reaction_kn == pytest.approx(
        3.0 * sum(q_stages) * 10.0
    )


def test_signed_cumulative_end_actions_match_continuous_two_span_closed_form() -> None:
    result = _run(_project(continuous=True))
    model = result.stages[-1].model
    nodes = {n.node_id: n for n in model.nodes}
    q = 0.3 * 0.95 * 25.0 + 2.0 * 0.25 * 25.0 + 2.0 * 0.08 * 24.0
    support = next(n for n in model.nodes if n.x_m == 10.0 and n.y_m == 0.0)
    reaction = next(n for n in result.final_response.nodes if n.node_id == support.node_id)
    assert reaction.vertical_reaction_kn == pytest.approx(5.0 * q * 10.0 / 4.0)
    left_member = next(
        m
        for m in result.final_response.members
        if (m.node_j == support.node_id and nodes[m.node_i].x_m < 10.0)
    )
    assert -left_member.j_vertical_bending_moment_knm == pytest.approx(-q * 10.0**2 / 8.0)
    for stage in result.stages:
        assert stage.increment.vertical_equilibrium_residual_kn == pytest.approx(0.0, abs=1e-8)


def test_partial_stage_action_is_clipped_exactly_without_new_cross_beams() -> None:
    project = _project()
    project.permanent_actions.line_actions.append(
        PermanentLineAction(
            name="test partial service",
            magnitude_kn_m=4.0,
            y_m=0.0,
            category=PermanentLineActionCategory.SERVICES,
            x_start_m=2.0,
            x_end_m=7.0,
            stage=PermanentActionStage.DECK_CONSTRUCTION,
        )
    )
    result = _run(project)
    wet_deck = result.stages[1]
    assignment = next(a for a in wet_deck.assignments if a.segment.source == "test partial service")
    assert assignment.girder_index == 2
    assert [(load.start_m, load.end_m) for load in assignment.member_loads] == [
        (2.0, 5.0),
        (0.0, 2.0),
    ]
    assert all(load.magnitude_kn_m == -4.0 for load in assignment.member_loads)
    assert {node.x_m for node in wet_deck.model.nodes} == {0.0, 5.0, 10.0}
    for stage in result.stages:
        expected = sum(item.segment.total_load_kn for item in stage.assignments)
        assert stage.increment.total_applied_vertical_load_kn == pytest.approx(-expected)
        assert stage.model.nodes == wet_deck.model.nodes
        assert stage.model.supports == wet_deck.model.supports
    sources = [a.segment.source for stage in result.stages for a in stage.assignments]
    assert sources.count("test partial service") == 1


def test_unchanged_stiffness_increment_sum_equals_one_combined_linear_solve() -> None:
    longitudinal = GrillageSectionProperties("test unchanged section", 0.5, 0.01, 0.04, 0.06)
    transverse = GrillageSectionProperties("test unchanged cross-member", 0.2, 0.005, 0.002, 0.002)
    stages = tuple(
        replace(s, longitudinal_sections_by_span=(longitudinal,), transverse_section=transverse)
        for s in _stages()
    )
    result = _run(stages=stages)
    model = result.stages[-1].model
    combined = replace(
        model,
        load_cases=(
            replace(
                model.load_cases[0],
                uniform_loads=tuple(
                    load
                    for stage in result.stages
                    for load in stage.model.load_cases[0].uniform_loads
                ),
            ),
        ),
    )
    direct = solve_vertical_grillage(combined)
    for summed, solved in zip(result.final_response.nodes, direct.nodes, strict=True):
        assert summed.vertical_displacement_m == pytest.approx(
            solved.vertical_displacement_m, abs=1e-10
        )
        assert summed.vertical_reaction_kn == pytest.approx(solved.vertical_reaction_kn, abs=1e-8)
    for summed, solved in zip(result.final_response.members, direct.members, strict=True):
        assert summed.i_vertical_bending_moment_knm == pytest.approx(
            solved.i_vertical_bending_moment_knm, abs=1e-8
        )
        assert summed.i_vertical_force_kn == pytest.approx(solved.i_vertical_force_kn, abs=1e-8)
        assert summed.i_torsion_knm == pytest.approx(solved.i_torsion_knm, abs=1e-8)


def test_exports_use_each_exact_stage_model_and_load_audit_without_certification() -> None:
    result = _run()
    packages = build_construction_stage_verification_packages(result)
    assert set(packages) == {stage.value for stage in PermanentActionStage}
    for stage in result.stages:
        package = packages[stage.input.stage.value]
        assert package.midas_mct == export_midas_mct(stage.model)
        assert package.staad_std == export_staad_std(stage.model)
        audit = json.loads(stage.model.metadata["permanent_load_audit"])
        assert all(item["stage"] == stage.input.stage.value for item in audit)
        assert len(audit) == len(stage.assignments)
        assert "requires_validation" in stage.model.metadata["purpose"]
        assert len(package.files(stage.input.stage.value)) == 6


@pytest.mark.parametrize("stages", [_stages()[:2], _stages()[::-1], (*_stages(), _stages()[0])])
def test_missing_duplicate_or_reordered_stage_cannot_drop_or_reapply_weight(stages) -> None:
    with pytest.raises(ValueError, match="exactly once in construction order"):
        _run(stages=stages)


def test_sequence_basis_and_early_transverse_stiffness_are_mandatory() -> None:
    with pytest.raises(ValueError, match="unchanged supports"):
        _run(unchanged_supports_and_continuity_basis=" ")
    with pytest.raises(ValueError, match="explicit transverse"):
        PermanentGrillageStageInput(PermanentActionStage.PRECAST_GIRDER, "no diaphragms known")
    with pytest.raises(ValueError, match="basis"):
        PermanentGrillageStageInput(PermanentActionStage.SUPERIMPOSED, " ")
    with pytest.raises(ValueError, match="only valid"):
        replace(_stages()[0], deck_construction_false_slab_participates=True)


def test_independent_multi_simple_spans_do_not_silently_gain_continuity() -> None:
    project = _project(continuous=True)
    project.geometry.support_system = SupportSystem.SIMPLY_SUPPORTED
    with pytest.raises(ValueError, match="separate construction models"):
        _run(project)


def test_permanent_load_double_count_and_girder_input_count_safeguards_survive() -> None:
    with pytest.raises(ValueError, match="girder count"):
        _run(additional_permanent_by_girder=(UniformPermanentLoadInput(),))
    with pytest.raises(ValueError, match="double count"):
        _run(
            additional_permanent_by_girder=(
                UniformPermanentLoadInput(surfacing_and_finishes_kn_m=2.0),
            )
            * 3
        )
    with pytest.raises(ValueError, match="conflicts"):
        _run(
            additional_permanent_by_girder=(
                UniformPermanentLoadInput(girder_self_weight_kn_m=99.0),
            )
            * 3
        )


def test_bs_construction_analysis_requires_explicit_modulus_not_ec2_strength_assumptions() -> None:
    project = _project()
    project.design_code = DesignCode.BS5400
    with pytest.raises(ValueError, match="elastic_modulus_mpa"):
        _run(project)
    project.materials = MaterialProperties(elastic_modulus_mpa=28000.0, fcu_mpa=45.0)
    result = _run(project)
    assert all(stage.model.materials[0].elastic_modulus_kn_m2 == 28e6 for stage in result.stages)


def test_zero_superimposed_stage_is_retained_but_does_not_reapply_earlier_loads() -> None:
    project = _project()
    project.permanent_actions = PermanentActionModel()
    result = _run(project)
    final = result.stages[-1]
    assert final.assignments == ()
    assert final.increment.total_applied_vertical_load_kn == 0.0
    assert final.cumulative == result.stages[-2].cumulative


@pytest.mark.parametrize(
    "module",
    [
        "rc_bridge.analysis.grillage_solver",
        "rc_bridge.workflow.project_construction",
    ],
)
def test_solver_and_construction_workflow_import_in_a_fresh_interpreter(module: str) -> None:
    # Full-suite collection previously masked an export -> workflow -> solver
    # cycle. Isolated consumers must not depend on a fortunate import order.
    subprocess.run([sys.executable, "-c", f"import {module}"], check=True, capture_output=True)
