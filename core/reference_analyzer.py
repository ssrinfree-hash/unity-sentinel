"""GUID reference analysis for text-serialised Unity assets.

Unity serialises ``{fileID: ..., guid: <32 hex>, type: 3}`` references inside
YAML assets. This module scans those text files for GUIDs that do not exist in
the local ``.meta`` database.

Honest scope (also printed by the CLI):

* only **text** assets are scanned; binary-serialised assets and assets inside
  packages are not covered;
* a GUID may legitimately live in a package or in an engine assembly without a
  local ``.meta`` file, so a "missing" reference is reported as a *warning*
  with ``medium`` confidence, never as a proven error;
* references created via reflection, ``Resources.Load`` string paths or
  Addressables are invisible to this analysis.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import Confidence, Finding, Severity
from .paths import is_secret_like

LOGGER = logging.getLogger("unity_sentinel.references")

_GUID_REF_RE = re.compile(r"guid:\s*([0-9a-fA-F]{32})")

DEFAULT_REFERENCE_EXTENSIONS = (
    ".unity",
    ".prefab",
    ".asset",
    ".mat",
    ".anim",
    ".controller",
    ".overrideController",
    ".mask",
    ".physicMaterial",
    ".preset",
)

# Built-in Unity packages ship with their own asset database, so references to
# them have no project-local .meta file. We cannot enumerate their GUIDs, but we
# can at least avoid *duplicating* the same finding per file.
_MAX_MISSING_REPORTED = 200


@dataclass
class ReferenceIndex:
    """Aggregate statistics for the reference scan."""

    scanned_files: int = 0
    skipped_files: int = 0
    unknown_guids: dict[str, list[str]] = field(default_factory=dict)  # guid -> [files]
    total_references: int = 0
    limitations: list[str] = field(default_factory=list)


def scan_references(
    root: Path,
    known_guids: set[str],
    *,
    extensions: tuple[str, ...] = DEFAULT_REFERENCE_EXTENSIONS,
    max_file_size: int = 16 * 1024 * 1024,
) -> tuple[ReferenceIndex, list[Finding]]:
    """Find GUID references that are not present in ``known_guids``."""
    index = ReferenceIndex()
    assets_root = root / "Assets"
    if not assets_root.is_dir():
        index.limitations.append("Assets/ is missing; reference analysis skipped.")
        return index, []

    findings_by_guid: dict[str, Finding] = {}
    for path in sorted(assets_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        if is_secret_like(path):
            index.skipped_files += 1
            continue
        try:
            if path.stat().st_size > max_file_size:
                index.skipped_files += 1
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            LOGGER.debug("Cannot read %s: %s", path, exc)
            index.skipped_files += 1
            continue

        index.scanned_files += 1
        rel = path.relative_to(root).as_posix()
        for match in _GUID_REF_RE.finditer(text):
            guid = match.group(1).lower()
            index.total_references += 1
            if guid in known_guids or guid.startswith("0000000000000000"):
                continue
            line = text.count("\n", 0, match.start()) + 1
            index.unknown_guids.setdefault(guid, []).append(rel)
            if guid not in findings_by_guid and len(findings_by_guid) < _MAX_MISSING_REPORTED:
                findings_by_guid[guid] = Finding(
                    code="REF_UNKNOWN_GUID",
                    message=(
                        "GUID reference is not present in the project .meta database; "
                        "it may be a package/engine asset or a genuinely missing reference."
                    ),
                    severity=Severity.WARNING,
                    path=rel,
                    line=line,
                    confidence=Confidence.MEDIUM,
                    evidence=f"guid {guid}",
                    recommendation=(
                        "Confirm in the Unity Editor (Sentinel > Scan Project) whether the "
                        "reference is Missing; do not edit GUIDs by hand."
                    ),
                    category="references",
                )

    findings = [findings_by_guid[guid] for guid in sorted(findings_by_guid)]
    if len(index.unknown_guids) > _MAX_MISSING_REPORTED:
        findings.append(
            Finding(
                code="REF_TRUNCATED",
                message=(
                    f"{len(index.unknown_guids)} unknown GUIDs found; only the first "
                    f"{_MAX_MISSING_REPORTED} are listed."
                ),
                severity=Severity.INFO,
                confidence=Confidence.HIGH,
                category="references",
            )
        )
    index.limitations.append(
        "Only text-serialised assets are scanned; binary assets and package "
        "assets are not covered, and unknown GUIDs may belong to packages."
    )
    return index, findings
