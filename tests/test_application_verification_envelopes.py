import json

import pytest

from rc_bridge.application.verification_envelopes import compare_staad_lm1_envelopes
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationSection,
    VerificationSupport,
    VerificationUniformLoad,
    VerificationNode,
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


def test_staad_envelope_comparison_matches_native_governing_cases() -> None:
    report = compare_staad_lm1_envelopes(
        _stage5_model(),
        _lm1(),
        staad_anl_text=_anl(),
        relative_tolerance=0.05,
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
        staad_anl_text=bad,
        relative_tolerance=0.05,
    )

    moment = next(item for item in report.items if item.quantity == "Moment")
    assert moment.passes is False
    assert report.passes is False
