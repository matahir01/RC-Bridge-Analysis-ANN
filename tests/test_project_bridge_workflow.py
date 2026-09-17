import pytest

from rc_bridge.core.models import MaterialProperties, ProjectInput, SupportSystem
from rc_bridge.workflow.project_bridge import (
    UniformPermanentLoadInput,
    internal_girder_characteristic_permanent_effects,
    internal_girder_deck_self_weight_kn_m,
    project_eurocode_material_input,
    run_project_lm1_equal_share_verification,
)


def test_reference_project_material_input_uses_ec2_c35_45_properties() -> None:
    project = ProjectInput()
    materials = project_eurocode_material_input(project)
    assert materials.fck_mpa == pytest.approx(35.0)
    assert materials.fyk_mpa == pytest.approx(500.0)
    assert materials.ecm_mpa == pytest.approx(34077.1461992)
    assert materials.fct_eff_mpa == pytest.approx(3.2099624417)
    assert materials.es_mpa == pytest.approx(200000.0)


def test_project_material_input_respects_explicit_modulus_and_fct_eff() -> None:
    project = ProjectInput(
        materials=MaterialProperties(
            fck_mpa=35.0,
            fyk_mpa=500.0,
            concrete_density_kn_m3=25.0,
            elastic_modulus_mpa=32000.0,
        )
    )
    materials = project_eurocode_material_input(project, fct_eff_mpa=2.5)
    assert materials.ecm_mpa == pytest.approx(32000.0)
    assert materials.fct_eff_mpa == pytest.approx(2.5)


def test_reference_project_internal_girder_deck_self_weight() -> None:
    project = ProjectInput()
    assert internal_girder_deck_self_weight_kn_m(project) == pytest.approx(10.625)


def test_reference_project_deck_only_characteristic_effects() -> None:
    project = ProjectInput()
    effects = internal_girder_characteristic_permanent_effects(project)
    assert effects.moment_knm == pytest.approx(298.828125)
    assert effects.shear_kn == pytest.approx(79.6875)


def test_additional_permanent_line_loads_enter_same_effects_path() -> None:
    project = ProjectInput()
    additional = UniformPermanentLoadInput(
        girder_self_weight_kn_m=3.0,
        surfacing_and_finishes_kn_m=1.0,
        assigned_barrier_and_services_kn_m=0.5,
        other_kn_m=0.5,
    )
    effects = internal_girder_characteristic_permanent_effects(
        project,
        additional=additional,
    )
    assert additional.total_additional_kn_m == pytest.approx(5.0)
    assert effects.moment_knm == pytest.approx(439.453125)
    assert effects.shear_kn == pytest.approx(117.1875)


def test_reference_project_lm1_verification_uses_7m_carriageway_and_7_girders() -> None:
    project = ProjectInput()
    result = run_project_lm1_equal_share_verification(
        project,
        movement_steps=21,
        section_stations=31,
    )
    assert result.lane_layout.carriageway_width_m == pytest.approx(7.0)
    assert result.lane_layout.lane_count == 2
    assert result.lane_layout.remaining_width_m == pytest.approx(1.0)
    assert len(result.girder_effects) == 7
    assert all("verification_only" in item.method for item in result.girder_effects)


def test_project_equal_share_verification_rejects_continuous_system() -> None:
    project = ProjectInput()
    project.geometry.support_system = SupportSystem.CONTINUOUS
    with pytest.raises(ValueError, match="simple spans only"):
        run_project_lm1_equal_share_verification(project)
