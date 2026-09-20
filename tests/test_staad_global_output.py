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


def _strided_section_model(member_count: int = 245, section_count: int = 7) -> VerificationModel:
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
            section_id=(index % section_count) + 1,
        )
        for index in range(member_count)
    )
    sections = tuple(
        VerificationSection(
            section_id=index + 1,
            name=f"Section {index + 1}",
            area_m2=0.5,
            torsion_constant_m4=0.02,
            iy_m4=0.03,
            iz_m4=0.04,
        )
        for index in range(section_count)
    )
    return VerificationModel(
        name="STAAD Strided Grillage Property Test",
        nodes=nodes,
        materials=(
            VerificationMaterial(
                material_id=1,
                name="Concrete",
                elastic_modulus_kn_m2=30_000_000.0,
            ),
        ),
        sections=sections,
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


def test_staad_export_chunks_member_ranges_for_properties_and_materials() -> None:
    text = export_staad_std(_model(85))

    assert "SET Z UP" in text
    assert "1 TO 12 PRIS" in text
    assert "73 TO 84 PRIS" in text
    assert "85 PRIS" in text
    assert "MATERIAL Concrete MEMB 1 TO 24" in text
    assert "MATERIAL Concrete MEMB 73 TO 85" in text


def test_staad_export_chunks_strided_grillage_property_assignments() -> None:
    text = export_staad_std(_strided_section_model())
    property_block = text.split("MEMBER PROPERTY\n", 1)[1].split(
        "DEFINE MATERIAL START\n",
        1,
    )[0]
    physical_lines = [line for line in property_block.splitlines() if line.strip()]

    logical_commands: list[str] = []
    current = ""
    for line in physical_lines:
        continuation = line.endswith(" -")
        content = line[:-2] if continuation else line
        current = f"{current} {content}".strip()
        if not continuation:
            logical_commands.append(current)
            current = ""

    property_commands = [
        command for command in logical_commands if " PRIS " in command
    ]

    assert len(property_commands) > 7
    assert all(
        " AX " in command
        and " IX " in command
        and " IY " in command
        and " IZ " in command
        for command in property_commands
    )
    assert max(map(len, physical_lines)) <= 78


def test_large_staad_model_chunks_global_member_force_requests() -> None:
    text = export_staad_std(_model(85))
    commands = [
        line
        for line in text.splitlines()
        if line.startswith("PRINT MEMBER FORCES GLOBAL LIST ")
    ]

    assert len(commands) == 4
    member_ids = [
        int(value)
        for command in commands
        for value in command.removeprefix("PRINT MEMBER FORCES GLOBAL LIST ").split()
    ]
    assert member_ids == list(range(1, 86))
