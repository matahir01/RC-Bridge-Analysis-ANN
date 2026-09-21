import pytest

from rc_bridge.application.project_editor import application_default_project
from rc_bridge.research.msc_input_space import (
    MSC_CORE_VARIABLES,
    MSC_DEFLECTION_LIMIT_SPAN_RATIO,
    MSC_SCOPE_LOCK,
    DistributionFamily,
    ResearchVariableRole,
    deflection_limit_mm,
    msc_variable,
    require_input_space_frozen,
    scope_lock_project_blockers,
    unresolved_sampling_items,
)


def test_msc_scope_lock_matches_verified_15m_baseline() -> None:
    project = application_default_project()

    assert scope_lock_project_blockers(project) == ()
    assert MSC_SCOPE_LOCK.analysis_span_m == pytest.approx(15.0)
    assert MSC_SCOPE_LOCK.physical_precast_girder_length_m == pytest.approx(14.95)
    assert MSC_SCOPE_LOCK.baseline_precast_width_m == pytest.approx(0.40)
    assert MSC_SCOPE_LOCK.baseline_precast_depth_m == pytest.approx(0.95)


def test_l_over_250_is_the_current_research_deflection_criterion() -> None:
    assert MSC_DEFLECTION_LIMIT_SPAN_RATIO == pytest.approx(250.0)
    assert deflection_limit_mm(15.0) == pytest.approx(60.0)
    assert MSC_SCOPE_LOCK.baseline_deflection_limit_mm == pytest.approx(60.0)


def test_design_and_random_variables_are_separated_explicitly() -> None:
    roles = {item.name: item.role for item in MSC_CORE_VARIABLES}

    assert roles["girder_width_m"] is ResearchVariableRole.DESIGN
    assert roles["girder_depth_m"] is ResearchVariableRole.DESIGN
    assert roles["longitudinal_steel_area_mm2"] is ResearchVariableRole.DESIGN
    assert roles["fck_mpa"] is ResearchVariableRole.RANDOM
    assert roles["fyk_mpa"] is ResearchVariableRole.RANDOM
    assert roles["permanent_action_multiplier"] is ResearchVariableRole.RANDOM
    assert roles["traffic_action_multiplier"] is ResearchVariableRole.RANDOM


def test_first_pass_probabilistic_evidence_is_machine_readable() -> None:
    fck = msc_variable("fck_mpa")
    fyk = msc_variable("fyk_mpa")
    permanent = msc_variable("permanent_action_multiplier")
    traffic = msc_variable("traffic_action_multiplier")

    assert fck.distribution is DistributionFamily.LOGNORMAL
    assert fck.coefficient_of_variation == pytest.approx(0.17)
    assert fyk.distribution is DistributionFamily.NORMAL
    assert fyk.mean == pytest.approx(560.0)
    assert fyk.standard_deviation == pytest.approx(30.0)
    assert permanent.distribution is DistributionFamily.NORMAL
    assert traffic.distribution is DistributionFamily.EXTREME_VALUE


def test_dataset_generation_remains_locked_until_bounds_and_parameters_are_frozen() -> None:
    blockers = unresolved_sampling_items()

    assert "girder_width_m: sampling bounds" in blockers
    assert "girder_depth_m: sampling bounds" in blockers
    assert "longitudinal_steel_area_mm2: sampling bounds" in blockers
    assert "permanent_action_multiplier: reliability parameters" in blockers
    assert "traffic_action_multiplier: reliability parameters" in blockers
    with pytest.raises(RuntimeError, match="not frozen"):
        require_input_space_frozen()
