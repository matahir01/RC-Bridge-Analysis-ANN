import pytest

from rc_bridge.export.external_results import (
    parse_verification_results_csv,
    validate_external_result_coverage,
)
from rc_bridge.export.model_verification_package import build_model_verification_export_package
from rc_bridge.export.staad_anl import (
    parse_staad_anl_result_sets,
    parse_staad_anl_results,
)
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
)


def _model() -> VerificationModel:
    return VerificationModel(
        name="STAAD ANL parser test",
        nodes=(
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 10.0, 0.0, 0.0),
            VerificationNode(3, 10.0, 5.0, 0.0),
        ),
        materials=(VerificationMaterial(1, "Concrete", 30.0e6),),
        sections=(
            VerificationSection(
                1,
                "Test section",
                area_m2=0.5,
                torsion_constant_m4=0.04,
                iy_m4=0.03,
                iz_m4=0.08,
            ),
        ),
        beams=(
            VerificationBeam(10, 1, 2, 1, 1),
            VerificationBeam(11, 2, 3, 1, 1),
        ),
        supports=(VerificationSupport(1), VerificationSupport(3)),
        load_cases=(VerificationLoadCase(1, "LM1"),),
    )


def _anl_text() -> str:
    return """
STAAD SPACE -- PAGE NO. 10
JOINT DISPLACEMENT (CM RADIANS) STRUCTURE TYPE = SPACE
------------------
JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN
1 1 0.0 0.0 -1.25 0.0 0.0 0.0
2 1 0.0 0.0 -0.80 0.0 0.0 0.0
3 1 0.0 0.0 -0.40 0.0 0.0 0.0
************** END OF LATEST ANALYSIS RESULT **************

SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE
-----------------
JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z
1 1 0.0 0.0 100.0 0.0 0.0 0.0
3 1 0.0 0.0 120.0 0.0 0.0 0.0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
-----------------
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
10 1 1 0.0 0.0 40.0 5.0 180.0 0.0
2 0.0 0.0 -40.0 -5.0 -170.0 0.0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
-----------------
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
11 1 2 0.0 0.0 20.0 -90.0 7.0 0.0
3 0.0 0.0 -20.0 85.0 -6.0 0.0
************** END OF LATEST ANALYSIS RESULT **************
"""


def test_staad_anl_parser_normalizes_units_and_global_member_vectors() -> None:
    normalized = parse_staad_anl_results(_anl_text(), _model())
    records = parse_verification_results_csv(normalized)
    values = {
        (item.result_type, item.object_id, item.position_m, item.component): item.value
        for item in records
    }

    assert values[("node_displacement", "1", "", "DZ")] == pytest.approx(-0.0125)
    assert values[("support_reaction", "1", "", "FZ")] == pytest.approx(100.0)

    assert values[("member_end_force", "10", "I", "V_VERTICAL")] == pytest.approx(40.0)
    assert values[("member_end_force", "10", "I", "M_VERTICAL")] == pytest.approx(180.0)
    assert values[("member_end_force", "10", "I", "T")] == pytest.approx(5.0)

    # Member 11 runs in +global Y. For the beta-zero horizontal basis its local
    # vertical-bending axis is -global X and its torsion axis is +global Y.
    assert values[("member_end_force", "11", "I", "V_VERTICAL")] == pytest.approx(20.0)
    assert values[("member_end_force", "11", "I", "M_VERTICAL")] == pytest.approx(90.0)
    assert values[("member_end_force", "11", "I", "T")] == pytest.approx(7.0)
    assert values[("member_end_force", "11", "J", "M_VERTICAL")] == pytest.approx(-85.0)
    assert values[("member_end_force", "11", "J", "T")] == pytest.approx(-6.0)


def test_staad_anl_parser_output_exactly_covers_verification_package_template() -> None:
    model = _model()
    normalized = parse_staad_anl_results(_anl_text(), model)
    package = build_model_verification_export_package(model)
    coverage = validate_external_result_coverage(
        template_csv=package.external_results_template_csv,
        external_csv=normalized,
    )
    assert coverage.complete
    assert coverage.matched_count == coverage.requested_count


def test_staad_anl_parser_rejects_local_member_force_output() -> None:
    local_text = _anl_text().replace(" (GLOBAL)", "")
    with pytest.raises(ValueError, match="GLOBAL axes"):
        parse_staad_anl_results(local_text, _model())


def test_staad_anl_parser_requires_explicit_case_for_multi_case_model() -> None:
    base = _model()
    model = VerificationModel(
        name=base.name,
        nodes=base.nodes,
        materials=base.materials,
        sections=base.sections,
        beams=base.beams,
        supports=base.supports,
        load_cases=(VerificationLoadCase(1, "LM1"), VerificationLoadCase(2, "OTHER")),
    )
    with pytest.raises(ValueError, match="requires load_case_id"):
        parse_staad_anl_results(_anl_text(), model)


def test_staad_anl_parser_accepts_load_combination_result_id() -> None:
    base = _model()
    model = VerificationModel(
        name=base.name,
        nodes=base.nodes,
        materials=base.materials,
        sections=base.sections,
        beams=base.beams,
        supports=base.supports,
        load_cases=(VerificationLoadCase(2, "BASE"),),
        load_combinations=(
            VerificationLoadCombination(
                1,
                "COMB",
                (VerificationLoadCombinationTerm(2, 1.0),),
            ),
        ),
    )

    normalized = parse_staad_anl_results(
        _anl_text(),
        model,
        load_case_id=1,
    )
    records = parse_verification_results_csv(normalized)

    assert records
    assert any(item.component == "M_VERTICAL" for item in records)


def _multi_result_model() -> VerificationModel:
    base = _model()
    return VerificationModel(
        name="STAAD ANL all-results parser test",
        nodes=base.nodes,
        materials=base.materials,
        sections=base.sections,
        beams=base.beams,
        supports=base.supports,
        load_cases=(
            VerificationLoadCase(1, "PERMANENT"),
            VerificationLoadCase(2, "LM1"),
        ),
        load_combinations=(
            VerificationLoadCombination(
                10001,
                "ULS",
                (
                    VerificationLoadCombinationTerm(1, 1.35),
                    VerificationLoadCombinationTerm(2, 1.50),
                ),
                category="ULS",
            ),
        ),
    )


def _paginated_multi_result_anl_text() -> str:
    return """
STAAD SPACE -- PAGE NO. 10
JOINT DISPLACEMENT (CM RADIANS) STRUCTURE TYPE = SPACE
JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN
1 1 0.0 0.0 -1.00 0.0 0.0 0.0
1 2 0.0 0.0 -2.00 0.0 0.0 0.0
1 10001 0.0 0.0 -4.35 0.0 0.0 0.0
STAAD SPACE -- PAGE NO. 11
JOINT DISPLACEMENT (CM RADIANS) STRUCTURE TYPE = SPACE
JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN
2 1 0.0 0.0 -1.50 0.0 0.0 0.0
2 2 0.0 0.0 -2.50 0.0 0.0 0.0
2 10001 0.0 0.0 -5.775 0.0 0.0 0.0
3 1 0.0 0.0 -0.50 0.0 0.0 0.0
3 2 0.0 0.0 -0.80 0.0 0.0 0.0
3 10001 0.0 0.0 -1.875 0.0 0.0 0.0
************** END OF LATEST ANALYSIS RESULT **************

SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE
JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z
1 1 0.0 0.0 100.0 0.0 0.0 0.0
1 2 0.0 0.0 120.0 0.0 0.0 0.0
1 10001 0.0 0.0 315.0 0.0 0.0 0.0
STAAD SPACE -- PAGE NO. 12
SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE
JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z
3 1 0.0 0.0 110.0 0.0 0.0 0.0
3 2 0.0 0.0 130.0 0.0 0.0 0.0
3 10001 0.0 0.0 343.5 0.0 0.0 0.0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
10 1 1 0.0 0.0 40.0 5.0 180.0 0.0
1 2 0.0 0.0 -40.0 -5.0 -170.0 0.0
10 2 1 0.0 0.0 50.0 6.0 200.0 0.0
2 2 0.0 0.0 -50.0 -6.0 -190.0 0.0
STAAD SPACE -- PAGE NO. 13
MEMBER END FORCES STRUCTURE TYPE = SPACE
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
10001 1 0.0 0.0 129.0 15.75 543.0 0.0
10001 2 0.0 0.0 -129.0 -15.75 -514.5 0.0
11 1 2 0.0 0.0 20.0 -90.0 7.0 0.0
1 3 0.0 0.0 -20.0 85.0 -6.0 0.0
11 2 2 0.0 0.0 30.0 -100.0 8.0 0.0
2 3 0.0 0.0 -30.0 95.0 -7.0 0.0
11 10001 2 0.0 0.0 72.0 -271.5 21.45 0.0
10001 3 0.0 0.0 -72.0 257.25 -18.6 0.0
************** END OF LATEST ANALYSIS RESULT **************
"""


def test_staad_anl_parser_reads_all_primary_cases_and_combinations_once() -> None:
    model = _multi_result_model()
    result_sets = parse_staad_anl_result_sets(
        _paginated_multi_result_anl_text(),
        model,
    )

    assert set(result_sets) == {1, 2, 10001}
    combination = parse_verification_results_csv(result_sets[10001])
    values = {
        (item.result_type, item.object_id, item.position_m, item.component): item.value
        for item in combination
    }
    assert values[("support_reaction", "1", "", "FZ")] == pytest.approx(315.0)
    assert values[("node_displacement", "2", "", "DZ")] == pytest.approx(-0.05775)
    assert values[("member_end_force", "10", "I", "V_VERTICAL")] == pytest.approx(129.0)
    assert values[("member_end_force", "10", "I", "M_VERTICAL")] == pytest.approx(543.0)
    assert values[("member_end_force", "10", "I", "T")] == pytest.approx(15.75)


def test_staad_anl_parser_preserves_member_context_across_page_heading() -> None:
    model = _multi_result_model()
    result_sets = parse_staad_anl_result_sets(
        _paginated_multi_result_anl_text(),
        model,
        result_ids=(10001,),
    )
    combination = parse_verification_results_csv(result_sets[10001])

    member_10 = [
        item
        for item in combination
        if item.result_type == "member_end_force" and item.object_id == "10"
    ]
    assert len(member_10) == 6
    assert {item.position_m for item in member_10} == {"I", "J"}
