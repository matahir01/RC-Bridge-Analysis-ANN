import json
from dataclasses import replace

import pytest

from rc_bridge.application.verification_envelopes import (
    compare_staad_lm1_envelopes,
    compare_stage5_combination_envelopes,
)
from rc_bridge.application.verification_results import VerificationResultDatabase
from rc_bridge.application.verification_tolerance import VerificationImportTolerance
from rc_bridge.export.staad_anl import parse_staad_anl_result_sets
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
from rc_bridge.workflow.lm1_grillage_search import (
    LM1GirderGoverningDeflection,
    LM1GirderGoverningEnvelope,
    LM1GoverningComponent,
    ProjectNativeLM1GrillageSearchResult,
)


def _stage5_model() -> VerificationModel:
    case_identity = [
        {"stage5_case_id": 1, "group": "permanent", "source_case_id": 1},
        {"stage5_case_id": 2, "group": "lm1", "source_case_id": 10},
        {"stage5_case_id": 3, "group": "lm1", "source_case_id": 11},
        {"stage5_case_id": 4, "group": "lm1", "source_case_id": 12},
        {"stage5_case_id": 5, "group": "lm1", "source_case_id": 13},
    ]
    return VerificationModel(
        name="Envelope comparison test",
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
        beams=(VerificationBeam(10, 1, 2, 1, 1),),
        supports=(
            VerificationSupport(1, uz=True, rx=True),
            VerificationSupport(2, uz=True),
        ),
        load_cases=(
            VerificationLoadCase(
                1,
                "PERMANENT",
                uniform_loads=(VerificationUniformLoad(10, "GZ", -10.0),),
            ),
            VerificationLoadCase(2, "LM1_M"),
            VerificationLoadCase(3, "LM1_V"),
            VerificationLoadCase(4, "LM1_T"),
            VerificationLoadCase(5, "LM1_D"),
        ),
        metadata={"case_identity": json.dumps(case_identity)},
    )


def _lm1() -> ProjectNativeLM1GrillageSearchResult:
    return ProjectNativeLM1GrillageSearchResult(
        cases=(),
        girders=(
            LM1GirderGoverningEnvelope(
                girder_index=1,
                y_m=0.0,
                moment_knm=LM1GoverningComponent(100.0, 10, 10),
                shear_kn=LM1GoverningComponent(50.0, 11, 10),
                torsion_knm=LM1GoverningComponent(10.0, 12, 10),
            ),
        ),
        longitudinal_step_m=1.0,
        search_strategy="synthetic",
        tandem_combinations_exhaustive=True,
        theoretical_tandem_combinations_per_transverse_layout=1,
        udl_pattern_count=1,
        deflections=(
            LM1GirderGoverningDeflection(
                girder_index=1,
                value_mm=5.0,
                case_id=13,
                node_id=2,
                position_m=10.0,
            ),
        ),
        evaluated_case_count_total=4,
    )


def _anl() -> str:
    return """
JOINT DISPLACEMENT (M RADIANS) STRUCTURE TYPE = SPACE
JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN
1 1 0 0 0 0 0 0
1 2 0 0 0 0 0 0
1 3 0 0 0 0 0 0
1 4 0 0 0 0 0 0
1 5 0 0 0 0 0 0
2 1 0 0 0 0 0 0
2 2 0 0 0 0 0 0
2 3 0 0 0 0 0 0
2 4 0 0 0 0 0 0
2 5 0 0 -0.00505 0 0 0
************** END OF LATEST ANALYSIS RESULT **************

SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE
JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z
1 1 0 0 50 0 0 0
1 2 0 0 0 0 0 0
1 3 0 0 0 0 0 0
1 4 0 0 0 0 0 0
1 5 0 0 0 0 0 0
2 1 0 0 50 0 0 0
2 2 0 0 0 0 0 0
2 3 0 0 0 0 0 0
2 4 0 0 0 0 0 0
2 5 0 0 0 0 0 0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
10 1 1 0 0 0 0 0 0
10 1 2 0 0 0 0 0 0
10 2 1 0 0 0 0 101 0
10 2 2 0 0 0 0 -101 0
10 3 1 0 0 50.5 0 0 0
10 3 2 0 0 -50.5 0 0 0
10 4 1 0 0 0 10.1 0 0
10 4 2 0 0 0 -10.1 0 0
10 5 1 0 0 0 0 0 0
10 5 2 0 0 0 0 0 0
************** END OF LATEST ANALYSIS RESULT **************
"""


def _external_database() -> VerificationResultDatabase:
    model = _stage5_model()
    return VerificationResultDatabase.from_normalized_csvs(
        parse_staad_anl_result_sets(_anl(), model)
    )


def test_staad_envelope_comparison_matches_native_governing_cases() -> None:
    report = compare_staad_lm1_envelopes(
        _stage5_model(),
        _lm1(),
        external_results=_external_database(),
        tolerance=VerificationImportTolerance(relative_tolerance=0.05),
    )

    assert report.passes is True
    assert report.permanent_equilibrium is not None
    assert report.permanent_equilibrium.native_total_reaction_kn == pytest.approx(100.0)
    assert report.permanent_equilibrium.external_total_reaction_kn == pytest.approx(100.0)

    by_quantity = {item.quantity: item for item in report.items}
    assert by_quantity["Moment"].external_value == pytest.approx(101.0)
    assert by_quantity["Moment"].relative_difference == pytest.approx(0.01)
    assert by_quantity["Shear"].external_value == pytest.approx(50.5)
    assert by_quantity["Torsion"].external_value == pytest.approx(10.1)
    assert by_quantity["Deflection"].external_value == pytest.approx(5.05)
    assert all(item.passes for item in report.items)


def test_staad_envelope_comparison_flags_out_of_tolerance_response() -> None:
    bad = _anl().replace("10 2 1 0 0 0 0 101 0", "10 2 1 0 0 0 0 120 0").replace(
        "10 2 2 0 0 0 0 -101 0",
        "10 2 2 0 0 0 0 -120 0",
    )
    report = compare_staad_lm1_envelopes(
        _stage5_model(),
        _lm1(),
        external_results=VerificationResultDatabase.from_normalized_csvs(
            parse_staad_anl_result_sets(bad, _stage5_model())
        ),
        tolerance=VerificationImportTolerance(relative_tolerance=0.05),
    )

    moment = next(item for item in report.items if item.quantity == "Moment")
    assert moment.passes is False
    assert report.passes is False


def test_zero_native_envelope_does_not_auto_pass_nonzero_external_value() -> None:
    lm1 = _lm1()
    girder = lm1.girders[0]
    zero_torsion = replace(
        lm1,
        girders=(
            replace(
                girder,
                torsion_knm=LM1GoverningComponent(0.0, 12, 10),
            ),
        ),
    )

    report = compare_staad_lm1_envelopes(
        _stage5_model(),
        zero_torsion,
        external_results=_external_database(),
        tolerance=VerificationImportTolerance(
            relative_tolerance=0.05,
            absolute_moment_knm=0.10,
        ),
    )

    torsion = next(item for item in report.items if item.quantity == "Torsion")
    assert torsion.relative_difference is None
    assert torsion.absolute_difference == pytest.approx(10.1)
    assert torsion.allowable_absolute_difference == pytest.approx(0.10)
    assert torsion.passes is False
    assert report.passes is False



def _combination_model() -> VerificationModel:
    return VerificationModel(
        name="Combination envelope test",
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
        beams=(VerificationBeam(10, 1, 2, 1, 1),),
        supports=(
            VerificationSupport(1, uz=True, rx=True),
            VerificationSupport(2, uz=True),
        ),
        load_cases=(
            VerificationLoadCase(1, "G"),
            VerificationLoadCase(2, "Q"),
        ),
        load_combinations=(
            VerificationLoadCombination(
                10001,
                "ULS_A",
                (
                    VerificationLoadCombinationTerm(1, 1.35),
                    VerificationLoadCombinationTerm(2, 1.50),
                ),
                category="ULS",
            ),
            VerificationLoadCombination(
                10002,
                "ULS_B",
                (
                    VerificationLoadCombinationTerm(1, 1.35),
                    VerificationLoadCombinationTerm(2, 1.20),
                ),
                category="ULS",
            ),
            VerificationLoadCombination(
                10003,
                "SLS_A",
                (
                    VerificationLoadCombinationTerm(1, 1.0),
                    VerificationLoadCombinationTerm(2, 1.0),
                ),
                category="SLS characteristic",
            ),
        ),
    )


def _normalized_result_csv(
    *,
    moment_knm: float,
    shear_kn: float,
    torsion_knm: float,
    displacement_m: float,
) -> str:
    return f"""result_type,object_id,span_index,position_m,component,value,unit
support_reaction,1,,,FZ,0,kN
support_reaction,2,,,FZ,0,kN
node_displacement,1,,,DZ,0,m
node_displacement,2,,,DZ,{-abs(displacement_m)},m
member_end_force,10,,I,V_VERTICAL,{shear_kn},kN
member_end_force,10,,I,M_VERTICAL,{moment_knm},kNm
member_end_force,10,,I,T,{torsion_knm},kNm
member_end_force,10,,J,V_VERTICAL,{-shear_kn},kN
member_end_force,10,,J,M_VERTICAL,{-moment_knm},kNm
member_end_force,10,,J,T,{-torsion_knm},kNm
"""


def _combination_databases(
    *,
    external_uls_a_moment: float = 101.0,
) -> tuple[VerificationResultDatabase, VerificationResultDatabase]:
    native = VerificationResultDatabase.from_normalized_csvs(
        {
            10001: _normalized_result_csv(
                moment_knm=100.0,
                shear_kn=50.0,
                torsion_knm=5.0,
                displacement_m=0.003,
            ),
            10002: _normalized_result_csv(
                moment_knm=120.0,
                shear_kn=45.0,
                torsion_knm=6.0,
                displacement_m=0.004,
            ),
            10003: _normalized_result_csv(
                moment_knm=80.0,
                shear_kn=35.0,
                torsion_knm=4.0,
                displacement_m=0.006,
            ),
        }
    )
    external = VerificationResultDatabase.from_normalized_csvs(
        {
            10001: _normalized_result_csv(
                moment_knm=external_uls_a_moment,
                shear_kn=50.5,
                torsion_knm=5.05,
                displacement_m=0.00305,
            ),
            10002: _normalized_result_csv(
                moment_knm=119.0,
                shear_kn=45.5,
                torsion_knm=6.05,
                displacement_m=0.00405,
            ),
            10003: _normalized_result_csv(
                moment_knm=80.8,
                shear_kn=35.2,
                torsion_knm=4.04,
                displacement_m=0.0061,
            ),
        }
    )
    return native, external


def test_combination_envelopes_track_native_and_external_governing_results() -> None:
    native, external = _combination_databases()
    report = compare_stage5_combination_envelopes(
        _combination_model(),
        native_results=native,
        external_results=external,
        tolerance=VerificationImportTolerance(relative_tolerance=0.05),
        source_name="STAAD.Pro",
    )

    assert report.passes is True
    uls_moment = next(
        item
        for item in report.items
        if item.category == "ULS" and item.quantity == "Moment"
    )
    assert uls_moment.native_governing_result_id == 10002
    assert uls_moment.external_governing_result_id == 10002
    assert uls_moment.native_value == pytest.approx(120.0)
    assert uls_moment.external_envelope_value == pytest.approx(119.0)

    sls_deflection = next(
        item
        for item in report.items
        if item.category == "SLS characteristic" and item.quantity == "Deflection"
    )
    assert sls_deflection.native_governing_result_id == 10003
    assert sls_deflection.external_envelope_value == pytest.approx(6.1)


def test_combination_envelope_detects_external_governing_switch_and_mismatch() -> None:
    native, external = _combination_databases(external_uls_a_moment=150.0)
    report = compare_stage5_combination_envelopes(
        _combination_model(),
        native_results=native,
        external_results=external,
        tolerance=VerificationImportTolerance(relative_tolerance=0.05),
    )

    uls_moment = next(
        item
        for item in report.items
        if item.category == "ULS" and item.quantity == "Moment"
    )
    assert uls_moment.native_governing_result_id == 10002
    assert uls_moment.external_governing_result_id == 10001
    assert uls_moment.governing_result_matches is False
    assert uls_moment.passes is False
    assert report.passes is False
