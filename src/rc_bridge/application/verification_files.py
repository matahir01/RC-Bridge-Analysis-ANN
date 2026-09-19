from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rc_bridge.export.model_verification_package import ModelVerificationExportPackage
from rc_bridge.workflow.lm1_grillage_search import (
    ProjectNativeLM1GrillageSearchResult,
    build_governing_lm1_search_verification_packages,
)


@dataclass(frozen=True)
class WrittenVerificationPackage:
    case_id: int | None
    directory: Path
    files: tuple[Path, ...]


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    if not stem:
        raise ValueError("Verification package base name cannot be empty.")
    return stem


def write_verification_package(
    package: ModelVerificationExportPackage,
    directory: str | Path,
    *,
    base_name: str,
    case_id: int | None = None,
) -> WrittenVerificationPackage:
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(base_name)
    written: list[Path] = []
    for filename, content in package.files(stem).items():
        path = target / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        written.append(path)
    return WrittenVerificationPackage(
        case_id=case_id,
        directory=target,
        files=tuple(sorted(written)),
    )


def write_governing_lm1_verification_packages(
    result: ProjectNativeLM1GrillageSearchResult,
    directory: str | Path,
    *,
    base_name: str = "lm1_governing",
) -> tuple[WrittenVerificationPackage, ...]:
    root = Path(directory)
    packages = build_governing_lm1_search_verification_packages(result)
    written: list[WrittenVerificationPackage] = []
    for case_id, package in sorted(packages.items()):
        case_directory = root / f"case_{case_id:04d}"
        written.append(
            write_verification_package(
                package,
                case_directory,
                base_name=f"{base_name}_case_{case_id:04d}",
                case_id=case_id,
            )
        )
    return tuple(written)
