"""File-level structural validation of Unity prefabs (``.prefab``).

Detected anomalies: no GameObject document, duplicated ``fileID``s, missing
script references (``m_Script: {fileID: 0}``), and prefab files without the
Unity YAML header.

Prefab overrides, nested-prefab cycles and broken prefab variants require the
Unity Editor API (``PrefabUtility``) and are handled by the Editor module.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .models import Confidence, Finding, Severity
from .unity_yaml import CLASS_GAMEOBJECT, read_unity_yaml

LOGGER = logging.getLogger("unity_sentinel.prefabs")


def validate_prefab(path: Path, root: Path | None = None) -> list[Finding]:
    """Validate a single prefab file and return findings."""
    rel = path.relative_to(root).as_posix() if root else path.name
    findings: list[Finding] = []
    info = read_unity_yaml(path)

    if not info.is_text:
        findings.append(
            Finding(
                code="PREFAB_BINARY",
                message="Prefab appears to be binary-serialised; file-level validation skipped.",
                severity=Severity.INFO,
                path=rel,
                confidence=Confidence.MEDIUM,
                category="prefabs",
            )
        )
        return findings

    if info.parse_error:
        findings.append(
            Finding(
                code="PREFAB_STRUCTURE",
                message=f"Prefab structure could not be parsed: {info.parse_error}",
                severity=Severity.ERROR,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Restore the prefab from version control.",
                category="prefabs",
            )
        )
        return findings

    if info.class_counts.get(CLASS_GAMEOBJECT, 0) == 0:
        findings.append(
            Finding(
                code="PREFAB_NO_GAMEOBJECT",
                message="Prefab contains no GameObject documents.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.MEDIUM,
                recommendation="A prefab root must contain a GameObject; inspect in Unity.",
                category="prefabs",
            )
        )

    for file_id in sorted(set(info.duplicate_file_ids)):
        findings.append(
            Finding(
                code="PREFAB_DUPLICATE_FILEID",
                message=f"Duplicate object fileID {file_id} in prefab.",
                severity=Severity.ERROR,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Restore the prefab from version control.",
                category="prefabs",
            )
        )

    for line in info.missing_script_lines:
        findings.append(
            Finding(
                code="PREFAB_MISSING_SCRIPT",
                message="MonoBehaviour has m_Script: {fileID: 0} (Missing Script).",
                severity=Severity.ERROR,
                path=rel,
                line=line,
                confidence=Confidence.HIGH,
                recommendation="Restore the missing script (check git history for its .meta GUID).",
                category="prefabs",
            )
        )
    return findings


def validate_prefabs(root: Path, prefab_paths: list[str]) -> list[Finding]:
    """Validate every prefab returned by the scanner."""
    findings: list[Finding] = []
    for rel in prefab_paths:
        path = root / rel
        try:
            findings.extend(validate_prefab(path, root))
        except Exception as exc:  # noqa: BLE001 - one bad file must not abort the scan
            LOGGER.warning("Prefab validation failed for %s: %s", rel, exc)
            findings.append(
                Finding(
                    code="PREFAB_UNREADABLE",
                    message=f"Prefab could not be analysed: {exc.__class__.__name__}",
                    severity=Severity.WARNING,
                    path=rel,
                    confidence=Confidence.LOW,
                    category="prefabs",
                )
            )
    return findings
