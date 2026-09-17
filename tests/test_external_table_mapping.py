import csv
from io import StringIO

import pytest

from rc_bridge.export.external_results import parse_verification_results_csv
from rc_bridge.export.table_mapping import (
    DisplacementTableMapping,
    ExternalTableMappingProfile,
    MemberForceTableMapping,
    ReactionTableMapping,
    TableFilter,
    midas_civil_global_profile,
    normalize_external_result_tables,
)


def test_midas_global_profile_filters_load_case_and_normalizes_reaction_displacement() -> None:
    reaction_table = "Node,Load,FZ\n1,LM1,100.0\n1,OTHER,999.0\n2,LM1,125.0\n"
    displacement_table = "Node,Load,DZ\n1,LM1,-0.012\n1,OTHER,-9.0\n2,LM1,-0.009\n"

    normalized = normalize_external_result_tables(
        midas_civil_global_profile(load_case="LM1"),
        reaction_table=reaction_table,
        displacement_table=displacement_table,
    )
    records = parse_verification_results_csv(normalized)

    assert len(records) == 4
    by_key = {(item.result_type, item.object_id): item for item in records}
    assert by_key[("support_reaction", "1")].value == pytest.approx(100.0)
    assert by_key[("support_reaction", "2")].value == pytest.approx(125.0)
    assert by_key[("node_displacement", "1")].value == pytest.approx(-0.012)
    assert by_key[("node_displacement", "2")].value == pytest.approx(-0.009)


def test_member_force_mapping_requires_explicit_local_axis_confirmation() -> None:
    with pytest.raises(ValueError, match="local_axis_mapping_verified"):
        MemberForceTableMapping(
            member_column="Elem",
            end_column="Part",
            vertical_shear_column="Shear - z",
            vertical_bending_column="Moment - y",
            torsion_column="Torsion",
        )


def test_explicit_member_force_mapping_normalizes_i_j_ends_and_components() -> None:
    member_table = (
        "Elem,Load,Part,Shear - z,Moment - y,Torsion\n"
        "10,LM1,I-End,42.5,180.0,12.0\n"
        "10,LM1,J-End,-39.0,-170.0,-11.5\n"
        "10,OTHER,I-End,999,999,999\n"
    )
    mapping = MemberForceTableMapping(
        member_column="Elem",
        end_column="Part",
        vertical_shear_column="Shear - z",
        vertical_bending_column="Moment - y",
        torsion_column="Torsion",
        end_aliases={"I-End": "I", "J-End": "J"},
        local_axis_mapping_verified=True,
        row_filter=TableFilter({"Load": "LM1"}),
    )
    profile = ExternalTableMappingProfile(name="verified local mapping", member_force=mapping)

    normalized = normalize_external_result_tables(profile, member_force_table=member_table)
    records = parse_verification_results_csv(normalized)
    assert len(records) == 6

    values = {(item.position_m, item.component): item.value for item in records}
    assert values[("I", "V_VERTICAL")] == pytest.approx(42.5)
    assert values[("I", "M_VERTICAL")] == pytest.approx(180.0)
    assert values[("I", "T")] == pytest.approx(12.0)
    assert values[("J", "V_VERTICAL")] == pytest.approx(-39.0)
    assert values[("J", "M_VERTICAL")] == pytest.approx(-170.0)
    assert values[("J", "T")] == pytest.approx(-11.5)


def test_unit_scaling_converts_external_mm_displacement_to_m() -> None:
    profile = ExternalTableMappingProfile(
        name="mm displacement",
        displacement=DisplacementTableMapping(
            node_column="Node",
            vertical_displacement_column="DZ_mm",
            scale_to_output_unit=0.001,
            row_filter=TableFilter({"Case": "SLS"}),
        ),
    )
    normalized = normalize_external_result_tables(
        profile,
        displacement_table="Node,Case,DZ_mm\n4,SLS,-12.5\n",
    )
    record = parse_verification_results_csv(normalized)[0]
    assert record.value == pytest.approx(-0.0125)
    assert record.unit == "m"


def test_duplicate_normalized_identity_requires_filtering() -> None:
    profile = ExternalTableMappingProfile(
        name="unfiltered reactions",
        reaction=ReactionTableMapping(node_column="Node", vertical_reaction_column="FZ"),
    )
    with pytest.raises(ValueError, match="duplicate normalized result identities"):
        normalize_external_result_tables(
            profile,
            reaction_table="Node,Load,FZ\n1,LC1,100\n1,LC2,110\n",
        )


def test_tab_delimited_external_table_is_supported() -> None:
    profile = ExternalTableMappingProfile(
        name="tab reactions",
        reaction=ReactionTableMapping(
            node_column="Node",
            vertical_reaction_column="FZ",
            row_filter=TableFilter({"Load": "LC1"}),
        ),
        delimiter="\t",
    )
    normalized = normalize_external_result_tables(
        profile,
        reaction_table="Node\tLoad\tFZ\n1\tLC1\t95.5\n",
    )
    rows = list(csv.DictReader(StringIO(normalized)))
    assert len(rows) == 1
    assert rows[0]["object_id"] == "1"
    assert float(rows[0]["value"]) == pytest.approx(95.5)
