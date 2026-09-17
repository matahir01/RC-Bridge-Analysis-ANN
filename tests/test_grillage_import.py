import pytest

from rc_bridge.analysis.grillage_import import (
    GrillageImportMetadata,
    parse_grillage_effects_csv,
)

SEVEN_GIRDER_CSV = """girder_index,moment_knm,shear_kn,torsion_knm
1,420.0,180.0,22.0
2,510.0,205.0,18.0
3,590.0,225.0,12.0
4,625.0,235.0,8.0
5,590.0,225.0,12.0
6,510.0,205.0,18.0
7,420.0,180.0,22.0
"""


def _metadata() -> GrillageImportMetadata:
    return GrillageImportMetadata(
        source_software="Midas Civil",
        model_name="15 m benchmark grillage",
        load_case="LM1 characteristic envelope",
    )


def test_parse_seven_girder_grillage_envelope() -> None:
    envelope = parse_grillage_effects_csv(
        SEVEN_GIRDER_CSV,
        metadata=_metadata(),
        expected_girder_count=7,
    )
    assert envelope.girder_count == 7
    assert envelope.effect_for_girder(4).moment_knm == pytest.approx(625.0)
    assert envelope.effect_for_girder(4).shear_kn == pytest.approx(235.0)
    assert envelope.effect_for_girder(4).torsion_knm == pytest.approx(8.0)
    assert envelope.metadata.method == "imported_grillage_envelope"


def test_torsion_column_is_optional_and_defaults_to_zero() -> None:
    csv_text = """girder_index,moment_knm,shear_kn
1,100,40
2,120,45
"""
    envelope = parse_grillage_effects_csv(csv_text, metadata=_metadata())
    assert envelope.effect_for_girder(1).torsion_knm == pytest.approx(0.0)


def test_grillage_import_rejects_noncanonical_units() -> None:
    with pytest.raises(ValueError, match="only kN forces and kNm moments"):
        GrillageImportMetadata(
            source_software="Midas Civil",
            model_name="test",
            load_case="LM1",
            force_unit="N",
            moment_unit="Nm",
        )


def test_grillage_import_rejects_missing_required_column() -> None:
    csv_text = """girder_index,moment_knm
1,100
"""
    with pytest.raises(ValueError, match="Missing required grillage CSV columns"):
        parse_grillage_effects_csv(csv_text, metadata=_metadata())


def test_grillage_import_rejects_duplicate_or_incomplete_indices() -> None:
    duplicate = """girder_index,moment_knm,shear_kn
1,100,40
1,110,45
"""
    with pytest.raises(ValueError, match="Duplicate girder indices"):
        parse_grillage_effects_csv(duplicate, metadata=_metadata())

    incomplete = """girder_index,moment_knm,shear_kn
1,100,40
3,130,50
"""
    with pytest.raises(ValueError, match="complete consecutive set"):
        parse_grillage_effects_csv(incomplete, metadata=_metadata())


def test_grillage_import_rejects_project_girder_count_mismatch() -> None:
    csv_text = """girder_index,moment_knm,shear_kn
1,100,40
2,120,45
"""
    with pytest.raises(ValueError, match="does not match the project"):
        parse_grillage_effects_csv(
            csv_text,
            metadata=_metadata(),
            expected_girder_count=7,
        )


def test_grillage_envelopes_must_be_nonnegative_magnitudes() -> None:
    negative = """girder_index,moment_knm,shear_kn,torsion_knm
1,100,40,-2
"""
    with pytest.raises(ValueError, match="torsion must be non-negative"):
        parse_grillage_effects_csv(negative, metadata=_metadata())
