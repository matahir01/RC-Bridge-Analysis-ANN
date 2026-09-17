from rc_bridge.export.staad_std import export_staad_std
from rc_bridge.export.verification_model import (
    VerificationBeam,
    VerificationLoadCase,
    VerificationMaterial,
    VerificationModel,
    VerificationNode,
    VerificationSection,
    VerificationSupport,
)


def _model(member_count: int) -> VerificationModel:
    nodes = tuple(
        VerificationNode(node_id=index + 1, x_m=float(index), y_m=0.0, z_m=0.0)
        for index in range(member_count + 1)
    )
    beams = tuple(
        VerificationBeam(
            member_id=index + 1,
            node_i=index + 1,
            node_j=index + 2,
            material_id=1,
            section_id=1,
        )
        for index in range(member_count)
    )
    return VerificationModel(
        name="STAAD Global Output Test",
        nodes=nodes,
        materials=(
            VerificationMaterial(
                material_id=1,
                name="Concrete",
                elastic_modulus_kn_m2=30_000_000.0,
            ),
        ),
        sections=(
            VerificationSection(
                section_id=1,
                name="Verification",
                area_m2=0.5,
                torsion_constant_m4=0.02,
                iy_m4=0.03,
                iz_m4=0.04,
            ),
        ),
        beams=beams,
        supports=(
            VerificationSupport(node_id=1, ux=True, uy=True, uz=True),
            VerificationSupport(node_id=member_count + 1, uy=True, uz=True),
        ),
        load_cases=(VerificationLoadCase(load_case_id=1, name="verification"),),
    )


def test_staad_export_requests_global_member_forces_and_global_nodal_results() -> None:
    text = export_staad_std(_model(2))

    assert "PRINT SUPPORT REACTION ALL" in text
    assert "PRINT JOINT DISPLACEMENTS ALL" in text
    assert "PRINT MEMBER FORCES GLOBAL LIST 1 2" in text
    assert "PRINT MEMBER FORCES ALL" not in text


def test_large_staad_model_chunks_global_member_force_requests() -> None:
    text = export_staad_std(_model(85))
    commands = [
        line
        for line in text.splitlines()
        if line.startswith("PRINT MEMBER FORCES GLOBAL LIST ")
    ]

    assert len(commands) == 3
    member_ids = [
        int(value)
        for command in commands
        for value in command.removeprefix("PRINT MEMBER FORCES GLOBAL LIST ").split()
    ]
    assert member_ids == list(range(1, 86))
