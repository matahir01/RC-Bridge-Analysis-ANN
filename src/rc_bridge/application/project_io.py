from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rc_bridge.core.models import ProjectInput

PROJECT_DOCUMENT_FORMAT = "rc_bridge_project"
PROJECT_DOCUMENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProjectDocument:
    project: ProjectInput
    schema_version: int = PROJECT_DOCUMENT_SCHEMA_VERSION
    document_format: str = PROJECT_DOCUMENT_FORMAT

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_DOCUMENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported project schema version {self.schema_version}; "
                f"expected {PROJECT_DOCUMENT_SCHEMA_VERSION}."
            )
        if self.document_format != PROJECT_DOCUMENT_FORMAT:
            raise ValueError(
                f"Unsupported project document format {self.document_format!r}."
            )

    @property
    def project_sha256(self) -> str:
        return hashlib.sha256(
            self.project.model_dump_json(
                by_alias=True,
                exclude_none=False,
            ).encode("utf-8")
        ).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_format": self.document_format,
            "schema_version": self.schema_version,
            "project_sha256": self.project_sha256,
            "project": self.project.model_dump(mode="json", exclude_none=False),
        }


def dumps_project_document(project: ProjectInput, *, indent: int = 2) -> str:
    if indent < 0:
        raise ValueError("indent cannot be negative.")
    document = ProjectDocument(project=project)
    return json.dumps(
        document.as_dict(),
        indent=indent,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def loads_project_document(text: str) -> ProjectDocument:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Project file is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise TypeError("Project file root must be a JSON object.")

    document_format = payload.get("document_format")
    schema_version = payload.get("schema_version")
    project_payload = payload.get("project")
    checksum = payload.get("project_sha256")
    if document_format != PROJECT_DOCUMENT_FORMAT:
        raise ValueError(
            f"Unsupported project document format {document_format!r}; "
            f"expected {PROJECT_DOCUMENT_FORMAT!r}."
        )
    if schema_version != PROJECT_DOCUMENT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schema version {schema_version!r}; "
            f"expected {PROJECT_DOCUMENT_SCHEMA_VERSION}."
        )
    if not isinstance(project_payload, dict):
        raise TypeError("Project file does not contain a valid project object.")

    project = ProjectInput.model_validate(project_payload)
    document = ProjectDocument(
        project=project,
        schema_version=int(schema_version),
        document_format=str(document_format),
    )
    if checksum is not None and checksum != document.project_sha256:
        raise ValueError(
            "Project checksum does not match the validated project data; "
            "the file may have been edited or corrupted."
        )
    return document


def save_project(project: ProjectInput, path: str | Path) -> Path:
    destination = Path(path)
    if destination.suffix.lower() != ".json":
        raise ValueError("RC bridge project files must use the .json extension.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(dumps_project_document(project), encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_project(path: str | Path) -> ProjectInput:
    source = Path(path)
    return loads_project_document(source.read_text(encoding="utf-8")).project
