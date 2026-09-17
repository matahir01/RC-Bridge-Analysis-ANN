import pytest

from rc_bridge.export.external_results import (
    parse_verification_results_csv,
    validate_external_result_coverage,
)
from rc_bridge.export.model_verification_package import build_model_verification_export_package
from rc_bridge.export.staad_anl import parse_staad_anl_results
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
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
