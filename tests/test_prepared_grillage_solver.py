import pytest

from rc_bridge.analysis.grillage_solver import solve_vertical_grillage
from rc_bridge.analysis.prepared_grillage_solver import (
    prepare_vertical_grillage,
    solve_prepared_vertical_grillage,
    vertical_grillage_structure_signature,
)
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNodalLoad,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
)


def _model(load_kn: float) -> VerificationModel:
    return VerificationModel(
        name=f"prepared line beam {load_kn:g}",
        nodes=(
            VerificationNode(1, 0.0, 0.0, 0.0),
            VerificationNode(2, 5.0, 0.0, 0.0),
            VerificationNode(3, 10.0, 0.0, 0.0),
        ),
        materials=(
            VerificationMaterial(
                material_id=1,
                name="Concrete",
                elastic_modulus_kn_m2=30.0e6,
            ),
        ),
        sections=(
            VerificationSection(
                section_id=1,
                name="Beam",
                area_m2=0.45,
                torsion_constant_m4=0.01,
                iy_m4=1.0e6 / 30.0e6,
                iz_m4=0.05,
            ),
        ),
        beams=(
            VerificationBeam(1, 1, 2, 1, 1),
            VerificationBeam(2, 2, 3, 1, 1),
        ),
        supports=(
            VerificationSupport(1, uz=True, rx=True),
            VerificationSupport(3, uz=True),
        ),
        load_cases=(
            VerificationLoadCase(
                1,
                "point load",
                nodal_loads=(
                    VerificationNodalLoad(node_id=2, fz_kn=-load_kn),
                ),
            ),
        ),
    )


@pytest.mark.parametrize("load_kn", [50.0, 100.0, 175.0])
def test_prepared_sparse_solver_matches_existing_dense_solver(load_kn: float) -> None:
    model = _model(load_kn)
    expected = solve_vertical_grillage(model)
    prepared = prepare_vertical_grillage(model)
    actual = solve_prepared_vertical_grillage(prepared, model)

    assert actual.total_applied_vertical_load_kn == pytest.approx(
        expected.total_applied_vertical_load_kn
    )
    assert actual.total_vertical_reaction_kn == pytest.approx(
        expected.total_vertical_reaction_kn
    )
    assert actual.vertical_equilibrium_residual_kn == pytest.approx(
        expected.vertical_equilibrium_residual_kn,
        abs=1.0e-8,
    )
    for expected_node, actual_node in zip(
        expected.nodes,
        actual.nodes,
        strict=True,
    ):
        assert actual_node.vertical_displacement_m == pytest.approx(
            expected_node.vertical_displacement_m,
            rel=1.0e-10,
            abs=1.0e-12,
        )
        assert actual_node.vertical_reaction_kn == pytest.approx(
            expected_node.vertical_reaction_kn,
            rel=1.0e-10,
            abs=1.0e-9,
        )


def test_one_prepared_factorization_can_solve_multiple_load_models() -> None:
    first = _model(50.0)
    second = _model(150.0)
    assert vertical_grillage_structure_signature(first) == (
        vertical_grillage_structure_signature(second)
    )

    prepared = prepare_vertical_grillage(first)
    first_result = solve_prepared_vertical_grillage(prepared, first)
    second_result = solve_prepared_vertical_grillage(prepared, second)

    first_mid = first_result.nodes[1].vertical_displacement_m
    second_mid = second_result.nodes[1].vertical_displacement_m
    assert second_mid == pytest.approx(3.0 * first_mid)
