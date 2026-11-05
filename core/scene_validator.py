"""File-level structural validation of Unity scenes (``.unity``).

What this module **can** do without Unity: detect YAML/structural anomalies
that are objectively wrong — no Unity documents, duplicated ``fileID``s, and
``m_Script: {fileID: 0}`` (a MonoBehaviour with no script, i.e. a missing
script reference).

What it **cannot** do: resolve prefab overrides, validate serialised
references against the asset database, or verify that a scene loads. Those
checks are implemented in the Unity Editor module (``unity/Editor``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from .models import Confidence, Finding, Severity
from .unity_yaml import CLASS_GAMEOBJECT, read_unity_yaml

LOGGER = logging.getLogger("unity_sentinel.scenes")


def validate_scene(path: Path, root: Path | None = None) -> list[Finding]:
    """Validate a single scene file and return findings."""
    rel = path.relative_to(root).as_posix() if root else path.name
    findings: list[Finding] = []
    info = read_unity_yaml(path)

    if not info.is_text:
        findings.append(
            Finding(
                code="SCENE_BINARY",
                message="Scene appears to be binary-serialised; file-level validation skipped.",
                severity=Severity.INFO,
                path=rel,
                confidence=Confidence.MEDIUM,
                recommendation="Use the Unity Editor module for binary assets.",
                category="scenes",
            )
        )
        return findings

    if info.parse_error:
        findings.append(
            Finding(
                code="SCENE_STRUCTURE",
                message=f"Scene structure could not be parsed: {info.parse_error}",
                severity=Severity.ERROR,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Open the scene in Unity; a corrupt scene should be restored from version control.",
                category="scenes",
            )
        )
        return findings

    if not info.has_unity_header:
        findings.append(
            Finding(
                code="SCENE_HEADER",
                message="Scene is missing the standard %YAML/%TAG Unity header.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.MEDIUM,
                recommendation="Verify the file was not truncated or hand-edited.",
                category="scenes",
            )
        )

    if info.class_counts.get(CLASS_GAMEOBJECT, 0) == 0:
        findings.append(
            Finding(
                code="SCENE_NO_GAMEOBJECTS",
                message="Scene contains no GameObject documents.",
                severity=Severity.INFO,
                path=rel,
                confidence=Confidence.MEDIUM,
                recommendation="This may be intentional for an empty bootstrap scene.",
                category="scenes",
            )
        )

    for file_id in sorted(set(info.duplicate_file_ids)):
        findings.append(
            Finding(
                code="SCENE_DUPLICATE_FILEID",
                message=f"Duplicate object fileID {file_id} in scene.",
                severity=Severity.ERROR,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Restore the scene from version control; duplicated fileIDs corrupt loading.",
                category="scenes",
            )
        )

    for line in info.missing_script_lines:
        findings.append(
            Finding(
                code="SCENE_MISSING_SCRIPT",
                message="MonoBehaviour has m_Script: {fileID: 0} (Missing Script).",
                severity=Severity.ERROR,
                path=rel,
                line=line,
                confidence=Confidence.HIGH,
                recommendation=(
                    "Find which script was removed (git history / .meta GUID) and restore it, "
                    "or remove the component intentionally in Unity."
                ),
                category="scenes",
            )
        )
    return findings


def validate_scenes(root: Path, scene_paths: list[str]) -> list[Finding]:
    """Validate every scene returned by the scanner."""
    findings: list[Finding] = []
    for rel in scene_paths:
        path = root / rel
        try:
            findings.extend(validate_scene(path, root))
        except Exception as exc:  # noqa: BLE001 - one bad file must not abort the scan
            LOGGER.warning("Scene validation failed for %s: %s", rel, exc)
            findings.append(
                Finding(
                    code="SCENE_UNREADABLE",
                    message=f"Scene could not be analysed: {exc.__class__.__name__}",
                    severity=Severity.WARNING,
                    path=rel,
                    confidence=Confidence.LOW,
                    category="scenes",
                )
            )
    return findings
