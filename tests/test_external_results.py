import csv
import io

from rc_bridge.export.external_results import (
    compare_external_results_csv,
    parse_verification_results_csv,
)

_EXPECTED = """result_type,object_id,span_index,position_m,component,value,unit
support_reaction,1,,,FZ,100,kN
member_end_force,1,0,0,M_i,-250,kNm
span_deflection,1,0,5,DZ_max_abs,0.012,m
"""


def _replace_value(text: str, *, component: str, value: float) -> str:
    source = io.StringIO(text)
    rows = list(csv.DictReader(source))
    for row in rows:
        if row["component"] == component:
            row["value"] = str(value)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def test_parse_verification_results_csv_preserves_result_identity() -> None:
    records = parse_verification_results_csv(_EXPECTED)
    assert len(records) == 3
    assert records[1].component == "M_i"
    assert records[1].value == -250.0
    assert records[1].unit == "kNm"


def test_external_result_comparison_passes_within_relative_tolerance() -> None:
    external = _replace_value(_EXPECTED, component="M_i", value=-252.0)
    result = compare_external_results_csv(
        expected_csv=_EXPECTED,
        external_csv=external,
        source_name="MIDAS Civil",
        relative_tolerance=0.02,
        absolute_tolerance_by_unit={"kN": 0.1, "kNm": 0.1, "m": 1.0e-5},
    )

    assert result.passes is True
    assert result.failed_target_names == ()
    assert result.missing_external_keys == ()
    assert result.extra_external_keys == ()


def test_external_result_comparison_flags_out_of_tolerance_value() -> None:
    external = _replace_value(_EXPECTED, component="FZ", value=90.0)
    result = compare_external_results_csv(
        expected_csv=_EXPECTED,
        external_csv=external,
        source_name="STAAD.Pro",
        relative_tolerance=0.02,
    )

    assert result.passes is False
    assert len(result.failed_target_names) == 1
    assert "FZ" in result.failed_target_names[0]


def test_external_result_comparison_requires_same_result_set() -> None:
    lines = _EXPECTED.splitlines()
    external = "\n".join(lines[:-1]) + "\n"
    result = compare_external_results_csv(
        expected_csv=_EXPECTED,
        external_csv=external,
        source_name="MIDAS Civil",
    )

    assert result.passes is False
    assert len(result.missing_external_keys) == 1
    assert "DZ_max_abs" in result.missing_external_keys[0]
