import pytest

from rc_bridge.codes.eurocode.materials import (
    concrete_properties_ec2,
    mean_compressive_strength_mpa,
    mean_tensile_strength_mpa,
    secant_elastic_modulus_mpa,
)


def test_c35_45_material_properties() -> None:
    properties = concrete_properties_ec2(35.0)
    assert properties.fcm_mpa == pytest.approx(43.0)
    assert properties.fctm_mpa == pytest.approx(3.2099624417)
    assert properties.ecm_mpa == pytest.approx(34077.1461992)


def test_high_strength_tensile_branch_is_used_above_c50_60() -> None:
    fctm = mean_tensile_strength_mpa(60.0)
    assert fctm == pytest.approx(4.3547423154)


def test_c30_37_modulus_matches_ec2_table_scale() -> None:
    assert mean_compressive_strength_mpa(30.0) == pytest.approx(38.0)
    assert secant_elastic_modulus_mpa(30.0) == pytest.approx(32836.5680313)


def test_first_generation_helper_rejects_strength_above_scope() -> None:
    with pytest.raises(ValueError, match="fck <= 90"):
        concrete_properties_ec2(95.0)
