import csv
import io

import pytest

from rc_bridge.export.line_benchmark_results import (
    normalize_midas_line_benchmark_tables,
    parse_staad_line_benchmark_results,
)
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
        name="line benchmark result adapter",
        nodes=(
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 10.0, 0.0, 0.0),
            VerificationNode(3, 20.0, 0.0, 0.0),
        ),
        materials=(VerificationMaterial(1, "Concrete", 30.0e6),),
        sections=(
            VerificationSection(
                1,
                "Line",
                area_m2=0.5,
                torsion_constant_m4=0.04,
                iy_m4=0.03,
                iz_m4=0.08,
            ),
        ),
        beams=(
            VerificationBeam(1, 1, 2, 1, 1),
            VerificationBeam(2, 2, 3, 1, 1),
        ),
        supports=(VerificationSupport(1), VerificationSupport(2), VerificationSupport(3)),
        load_cases=(VerificationLoadCase(1, "BENCH"),),
    )


def _staad_anl() -> str:
    return """
JOINT DISPLACEMENT (CM RADIANS) STRUCTURE TYPE = SPACE
JOINT LOAD X-TRANS Y-TRANS Z-TRANS X-ROTAN Y-ROTAN Z-ROTAN
1 1 0 0 0 0 0.001 0
2 1 0 0 0 0 -0.002 0
3 1 0 0 0 0 0.003 0
************** END OF LATEST ANALYSIS RESULT **************

SUPPORT REACTIONS -UNIT KN METE STRUCTURE TYPE = SPACE
JOINT LOAD FORCE-X FORCE-Y FORCE-Z MOM-X MOM-Y MOM Z
1 1 0 0 75 0 0 0
2 1 0 0 250 0 0 0
3 1 0 0 75 0 0 0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
1 1 1 0 0 75 0 0 0
2 0 0 -125 0 -250 0
************** END OF LATEST ANALYSIS RESULT **************

MEMBER END FORCES STRUCTURE TYPE = SPACE
ALL UNITS ARE -- KNS METE (GLOBAL)
MEMBER LOAD JT FX FY FZ MX MY MZ
2 1 2 0 0 125 0 -250 0
3 0 0 -75 0 0 0
************** END OF LATEST ANALYSIS RESULT **************
"""


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_staad_line_adapter_returns_only_global_reaction_translation_and_rotation() -> None:
    rows = _rows(parse_staad_line_benchmark_results(_staad_anl(), _model()))

    assert len(rows) == 9
    assert {row["component"] for row in rows} == {"FZ", "DZ", "RY"}
    assert not any(row["result_type"] == "member_end_force" for row in rows)

    values = {(row["result_type"], row["object_id"]): float(row["value"]) for row in rows}
    assert values[("support_reaction", "2")] == pytest.approx(250.0)
    assert values[("node_displacement", "2")] == pytest.approx(0.0)
    assert values[("node_rotation", "1")] == pytest.approx(0.001)
    assert values[("node_rotation", "2")] == pytest.approx(-0.002)


def test_midas_line_adapter_filters_load_case_and_includes_ry() -> None:
    reaction = "Node,Load,FZ\n1,BENCH,75\n2,BENCH,250\n3,BENCH,75\n1,OTHER,999\n"
    displacement = (
        "Node,Load,DZ,RY\n"
        "1,BENCH,0,0.001\n"
        "2,BENCH,0,-0.002\n"
        "3,BENCH,0,0.003\n"
        "1,OTHER,9,9\n"
    )
    rows = _rows(
        normalize_midas_line_benchmark_tables(
            reaction_table=reaction,
            displacement_table=displacement,
            load_case="BENCH",
        )
    )

    assert len(rows) == 9
    assert {row["component"] for row in rows} == {"FZ", "DZ", "RY"}
    assert max(float(row["value"]) for row in rows if row["component"] == "FZ") == 250.0
    assert all(row["object_id"] in {"1", "2", "3"} for row in rows)


def test_staad_line_adapter_requires_one_rotation_per_model_node() -> None:
    text = _staad_anl().replace("3 1 0 0 0 0 0.003 0\n", "")
    with pytest.raises(ValueError, match="one selected-load Y rotation"):
        parse_staad_line_benchmark_results(text, _model())
