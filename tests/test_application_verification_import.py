import json

import pytest

from rc_bridge.application.verification_import import (
    VerificationEngineeringReview,
    VerificationImportTolerance,
    combined_load_case,
    import_midas_table_verification_results,
    write_verification_import_evidence,
)
from rc_bridge.export.midas_mct import export_midas_mct, midas_result_name_map
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationLoadCombination,
    VerificationLoadCombinationTerm,
    VerificationMaterial,
    VerificationModel,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
)


def _zero_model() -> VerificationModel:
    return VerificationModel(
        name="Stage 5 import test",
        nodes=(
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 10.0, 0.0, 0.0),
        ),
        materials=(VerificationMaterial(1, "Concrete", 30.0e6),),
        sections=(
            VerificationSection(
                1,
                "Section",
                area_m2=0.5,
                torsion_constant_m4=0.04,
                iy_m4=0.03,
                iz_m4=0.08,
            ),
        ),
        beams=(VerificationBeam(1, 1, 2, 1, 1),),
        supports=(
            VerificationSupport(1, uz=True, rx=True),
            VerificationSupport(2, uz=True),
        ),
        load_cases=(VerificationLoadCase(1, "SERVICE_CASE"),),
        load_combinations=(
            VerificationLoadCombination(
                10001,
                "ULS_SERVICE_CASE",
                (VerificationLoadCombinationTerm(1, 1.5),),
                category="ULS",
            ),
        ),
    )


def _midas_tables(model: VerificationModel) -> tuple[str, str, str]:
    names = midas_result_name_map(model)
    load_names = (
        names[("case", 1)],
        names[("combination", 10001)],
    )
    reactions = "Node,Load,FZ\n" + "".join(
        f"{node},{load},0\n"
        for load in load_names
        for node in (1, 2)
    )
    displacements = "Node,Load,DZ\n" + "".join(
        f"{node},{load},0\n"
        for load in load_names
        for node in (1, 2)
    )
    forces = "Elem,Part,Load,Shear-z,Moment-y,Torsion\n" + "".join(
        f"1,{end},{load},0,0,0\n"
        for load in load_names
        for end in ("I", "J")
    )
    return reactions, displacements, forces


def test_midas_import_compares_load_cases_and_combinations_in_one_pass(tmp_path) -> None:
    model = _zero_model()
    reactions, displacements, forces = _midas_tables(model)

    report = import_midas_table_verification_results(
        model,
        reaction_table=reactions,
        displacement_table=displacements,
        member_force_table=forces,
        tolerance=VerificationImportTolerance(relative_tolerance=0.0),
    )

    assert report.passes is True
    assert report.engineering_acceptance_pending is True
    assert report.engineering_accepted is False
    assert report.engineering_acceptance_status == "PENDING REVIEW"
    assert report.combination_envelope_comparison is not None
    assert report.combination_envelope_comparison.passes is True
    assert report.imported_result_ids == (1, 10001)
    assert report.missing_result_ids == ()
    assert all(item.coverage.complete for item in report.result_sets)

    written = write_verification_import_evidence(
        report,
        tmp_path,
        base_name="stage5_check",
    )
    assert written.summary_json.exists()
    assert written.comparisons_csv.exists()
    summary = json.loads(written.summary_json.read_text(encoding="utf-8"))
    assert summary["passes"] is True
    assert summary["combination_envelope_comparison_passes"] is True
    assert summary["combination_envelope_comparison"]["passes"] is True
    assert summary["imported_result_ids"] == [1, 10001]
    assert len(written.normalized_result_files) == 2
    assert len(written.expected_result_files) == 2


def test_combination_solver_case_scales_every_member_load() -> None:
    model = _zero_model()
    loaded = VerificationLoadCase(
        1,
        "BASE",
        uniform_loads=(VerificationUniformLoad(1, "GZ", -12.0),),
    )
    combination = VerificationLoadCombination(
        10001,
        "ULS",
        (VerificationLoadCombinationTerm(1, 1.35),),
    )
    model = VerificationModel(
        name=model.name,
        nodes=model.nodes,
        materials=model.materials,
        sections=model.sections,
        beams=model.beams,
        supports=model.supports,
        load_cases=(loaded,),
        load_combinations=(combination,),
    )

    combined = combined_load_case(model, combination)

    assert combined.load_case_id == 10001
    assert combined.uniform_loads[0].magnitude_kn_m == pytest.approx(-16.2)


def test_midas_export_deduplicates_truncated_result_names() -> None:
    model = _zero_model()
    prefix = "X" * 45
    model = VerificationModel(
        name=model.name,
        nodes=model.nodes,
        materials=model.materials,
        sections=model.sections,
        beams=model.beams,
        supports=model.supports,
        load_cases=(
            VerificationLoadCase(1, prefix + "_A"),
            VerificationLoadCase(2, prefix + "_B"),
        ),
        load_combinations=(
            VerificationLoadCombination(
                10001,
                prefix + "_C",
                (VerificationLoadCombinationTerm(1, 1.0),),
            ),
        ),
    )

    names = midas_result_name_map(model)
    assert len(set(names.values())) == 3
    assert all(len(value) <= 40 for value in names.values())

    mct = export_midas_mct(model)
    for value in names.values():
        assert value in mct


def test_external_result_ids_cannot_overlap_load_case_ids() -> None:
    model = _zero_model()
    with pytest.raises(ValueError, match="globally unique"):
        VerificationModel(
            name=model.name,
            nodes=model.nodes,
            materials=model.materials,
            sections=model.sections,
            beams=model.beams,
            supports=model.supports,
            load_cases=(VerificationLoadCase(1, "CASE"),),
            load_combinations=(
                VerificationLoadCombination(
                    1,
                    "COMB",
                    (VerificationLoadCombinationTerm(1, 1.0),),
                ),
            ),
        )



def _complete_engineering_review() -> VerificationEngineeringReview:
    return VerificationEngineeringReview(
        source_reference="STAAD run 2026-09-20 / exported Stage-5 STD",
        solver_version="STAAD.Pro CONNECT Edition",
        exported_model_identity_verified=True,
        geometry_equivalent=True,
        section_properties_equivalent=True,
        material_properties_equivalent=True,
        boundary_conditions_equivalent=True,
        loading_equivalent=True,
        load_combinations_equivalent=True,
        result_axes_verified=True,
        notes="Reviewed against the exported verification package.",
    )


def test_engineering_acceptance_requires_complete_review_and_numerical_pass(tmp_path) -> None:
    model = _zero_model()
    reactions, displacements, forces = _midas_tables(model)
    report = import_midas_table_verification_results(
        model,
        reaction_table=reactions,
        displacement_table=displacements,
        member_force_table=forces,
        tolerance=VerificationImportTolerance(relative_tolerance=0.0),
    )

    incomplete = VerificationEngineeringReview(
        source_reference="MIDAS result export",
        solver_version="MIDAS Civil",
        geometry_equivalent=True,
    )
    reviewed = report.with_engineering_review(incomplete)
    assert reviewed.engineering_acceptance_pending is True
    assert reviewed.engineering_accepted is False
    assert "loading_equivalent" in incomplete.missing_checks()

    accepted = report.with_engineering_review(_complete_engineering_review())
    assert accepted.engineering_acceptance_pending is False
    assert accepted.engineering_accepted is True
    assert accepted.engineering_acceptance_status == "ACCEPTED"

    written = write_verification_import_evidence(
        accepted,
        tmp_path,
        base_name="accepted_stage5",
    )
    summary = json.loads(written.summary_json.read_text(encoding="utf-8"))
    assert summary["engineering_accepted"] is True
    assert summary["engineering_acceptance_status"] == "ACCEPTED"
    assert summary["engineering_review"]["complete"] is True
    assert summary["engineering_review"]["missing_checks"] == []


def test_complete_engineering_review_cannot_override_numerical_failure() -> None:
    model = _zero_model()
    reactions, displacements, forces = _midas_tables(model)
    bad_forces = forces.replace(",0,0,0\n", ",0,10,0\n", 1)
    report = import_midas_table_verification_results(
        model,
        reaction_table=reactions,
        displacement_table=displacements,
        member_force_table=bad_forces,
        tolerance=VerificationImportTolerance(
            relative_tolerance=0.0,
            absolute_moment_knm=0.0,
        ),
    ).with_engineering_review(_complete_engineering_review())

    assert report.numerical_agreement_passes is False
    assert report.engineering_acceptance_pending is False
    assert report.engineering_accepted is False
    assert report.engineering_acceptance_status == "REVIEW / FAIL"
