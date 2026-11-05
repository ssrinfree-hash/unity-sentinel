"""Regression tracking: baseline capture and post-change comparison.

A baseline stores the finding set plus SHA-256 hashes of the files that matter
(scripts, meta files, assets) so that:

* new findings are separated from pre-existing ones;
* unexpected file changes are surfaced even if they produce no finding;
* a modified file is **not** treated as an error by itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import (
    Baseline,
    Check,
    CheckResult,
    Confidence,
    Finding,
    Severity,
    Status,
)
from .paths import is_secret_like

LOGGER = logging.getLogger("unity_sentinel.regression")

HASHED_SUFFIXES = {
    ".cs",
    ".asmdef",
    ".asmref",
    ".shader",
    ".cginc",
    ".hlsl",
    ".meta",
    ".unity",
    ".prefab",
    ".asset",
    ".json",
    ".txt",
}

MAX_HASH_BYTES = 8 * 1024 * 1024


def _hash_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_HASH_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:  # pragma: no cover - permission errors
        LOGGER.debug("Cannot hash %s: %s", path, exc)
        return None


def hash_project_files(root: Path, relative_paths: Iterable[str] | None = None) -> dict[str, str]:
    """Compute SHA-256 for tracked project files.

    When ``relative_paths`` is omitted, ``Assets/``, ``Packages/`` and
    ``ProjectSettings/`` are walked (generated directories excluded by the
    caller, which normally passes scanner output).
    """
    hashes: dict[str, str] = {}
    if relative_paths is None:
        candidates: list[Path] = []
        for sub in ("Assets", "Packages", "ProjectSettings"):
            base = root / sub
            if base.is_dir():
                candidates.extend(p for p in base.rglob("*") if p.is_file())
        relative_paths = [p.relative_to(root).as_posix() for p in candidates]

    for rel in relative_paths:
        path = root / rel
        if path.suffix.lower() not in HASHED_SUFFIXES:
            continue
        if is_secret_like(path):
            continue
        digest = _hash_file(path)
        if digest:
            hashes[rel] = digest
    return hashes


def create_baseline(
    root: Path,
    *,
    findings: list[Finding],
    checks: list[Check],
    status: Status,
    mode: str = "scan",
    relative_paths: Iterable[str] | None = None,
) -> Baseline:
    """Build a baseline object from a completed scan."""
    return Baseline(
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        project_root=".",
        status=status.value,
        findings=sorted(findings, key=lambda f: f.key()),
        file_hashes=hash_project_files(root, relative_paths),
        checks=checks,
    )


def save_baseline(baseline: Baseline, path: Path) -> None:
    """Write a baseline as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_baseline(path: Path) -> Baseline:
    """Read a baseline JSON file.

    Raises:
        ValueError: when the file is not a valid baseline.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Baseline is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"Cannot read baseline {path}: {exc}") from exc
    if not isinstance(data, dict) or "findings" not in data or "file_hashes" not in data:
        raise ValueError("File is not a UNITY SENTINEL baseline (missing findings/file_hashes)")

    findings = [
        Finding(
            code=item.get("code", "UNKNOWN"),
            message=item.get("message", ""),
            severity=Severity(item.get("severity", "warning")),
            path=item.get("path"),
            line=item.get("line"),
            confidence=Confidence(item.get("confidence", "medium")),
            evidence=item.get("evidence"),
            recommendation=item.get("recommendation"),
            category=item.get("category", "general"),
        )
        for item in data.get("findings", [])
    ]
    checks = [
        Check(
            id=item.get("id", "unknown"),
            title=item.get("title", ""),
            result=CheckResult(item.get("result", "skipped")),
            details=item.get("details"),
            requires=item.get("requires"),
        )
        for item in data.get("checks", [])
    ]
    return Baseline(
        created_at=data.get("created_at", ""),
        mode=data.get("mode", "scan"),
        project_root=data.get("project_root", "."),
        status=data.get("status", ""),
        findings=findings,
        file_hashes=dict(data.get("file_hashes", {})),
        checks=checks,
    )


def compare(baseline: Baseline, current: list[Finding], current_hashes: dict[str, str]) -> tuple[list[Finding], list[Finding], list[Finding], dict[str, list[str]]]:
    """Compare a baseline with the current state.

    Returns:
        ``(new_findings, resolved_findings, unchanged_findings, file_changes)``
        where ``file_changes`` maps ``added|removed|modified`` to path lists.
    """
    baseline_fps = {f.fingerprint: f for f in baseline.findings}
    current_fps = {f.fingerprint: f for f in current}

    new = [current_fps[fp] for fp in current_fps.keys() - baseline_fps.keys()]
    resolved = [baseline_fps[fp] for fp in baseline_fps.keys() - current_fps.keys()]
    unchanged = [current_fps[fp] for fp in current_fps.keys() & baseline_fps.keys()]

    added = sorted(current_hashes.keys() - baseline.file_hashes.keys())
    removed = sorted(baseline.file_hashes.keys() - current_hashes.keys())
    modified = sorted(
        rel
        for rel in current_hashes.keys() & baseline.file_hashes.keys()
        if current_hashes[rel] != baseline.file_hashes[rel]
    )
    file_changes = {"added": added, "removed": removed, "modified": modified}

    new.sort(key=lambda f: f.key())
    resolved.sort(key=lambda f: f.key())
    unchanged.sort(key=lambda f: f.key())
    return new, resolved, unchanged, file_changes


def regression_findings(
    new: list[Finding],
    resolved: list[Finding],
    file_changes: dict[str, list[str]],
    *,
    expected_changes: Iterable[str] = (),
) -> list[Finding]:
    """Turn a comparison into report findings.

    New *errors* are critical regressions; new warnings are regressions at
    warning level. File changes that were not expected are reported separately
    but are not errors by themselves.
    """
    expected = {path.replace("\\", "/") for path in expected_changes}
    findings: list[Finding] = []

    for finding in new:
        is_error = finding.severity in (Severity.ERROR, Severity.CRITICAL)
        findings.append(
            Finding(
                code="REGRESSION_NEW_ERROR" if is_error else "REGRESSION_NEW_WARNING",
                message=f"New finding after changes: [{finding.code}] {finding.message}",
                severity=Severity.CRITICAL if is_error else Severity.WARNING,
                path=finding.path,
                line=finding.line,
                confidence=finding.confidence,
                evidence=finding.evidence,
                recommendation=finding.recommendation,
                category="regression",
            )
        )
    for finding in resolved:
        findings.append(
            Finding(
                code="REGRESSION_RESOLVED",
                message=f"Previously reported finding is gone: [{finding.code}] {finding.message}",
                severity=Severity.INFO,
                path=finding.path,
                confidence=finding.confidence,
                category="regression",
            )
        )
    for rel in file_changes.get("modified", []):
        if rel in expected:
            continue
        findings.append(
            Finding(
                code="REGRESSION_UNEXPECTED_FILE_CHANGE",
                message="File content changed but was not part of the declared plan.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Review `git diff` for this file; Sentinel never edits files outside a plan.",
                category="regression",
            )
        )
    for rel in file_changes.get("added", []):
        if rel in expected:
            continue
        findings.append(
            Finding(
                code="REGRESSION_UNEXPECTED_FILE_ADDED",
                message="File was added outside the declared plan.",
                severity=Severity.INFO,
                path=rel,
                confidence=Confidence.HIGH,
                category="regression",
            )
        )
    for rel in file_changes.get("removed", []):
        if rel in expected:
            continue
        findings.append(
            Finding(
                code="REGRESSION_UNEXPECTED_FILE_REMOVED",
                message="File was removed outside the declared plan.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.HIGH,
                category="regression",
            )
        )
    return findings
