import json

import pytest

from rc_bridge.application.project_io import (
    dumps_project_document,
    load_project,
    loads_project_document,
    save_project,
)
from rc_bridge.core.models import (
    BridgeGeometry,
    ProjectInput,
    RectangularGirderProfile,
    SectionType,
)


def _project() -> ProjectInput:
    return ProjectInput(
        name="Saved bridge",
        geometry=BridgeGeometry(
            deck_width_m=5.0,
            carriageway_width_m=5.0,
            girder_count=3,
            girder_spacing_m=2.0,
            section_type=SectionType.RECTANGULAR,
            girder_profile=RectangularGirderProfile(width_m=0.40, depth_m=0.95),
        ),
    )


def test_project_document_round_trips_with_checksum(tmp_path) -> None:
    project = _project()
    path = save_project(project, tmp_path / "bridge.json")
    loaded = load_project(path)

    assert loaded == project
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["document_format"] == "rc_bridge_project"
    assert payload["schema_version"] == 1
    assert len(payload["project_sha256"]) == 64


def test_project_document_rejects_tampered_payload() -> None:
    payload = json.loads(dumps_project_document(_project()))
    payload["project"]["name"] = "tampered"

    with pytest.raises(ValueError, match="checksum"):
        loads_project_document(json.dumps(payload))


def test_project_save_requires_json_extension(tmp_path) -> None:
    with pytest.raises(ValueError, match=".json"):
        save_project(_project(), tmp_path / "bridge.txt")
