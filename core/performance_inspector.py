"""Heuristic performance inspection of C# scripts.

Every finding produced here is a **heuristic observation**, never a proven
runtime problem. Each finding carries ``confidence=low`` and a message that
says so. Nothing is reported as an error, and nothing suggests blindly
replacing an API without checking the target Unity version.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Confidence, Finding, Severity

LOGGER = logging.getLogger("unity_sentinel.performance")

_METHOD_HEADER = r"(?:public|private|protected|internal|static|virtual|override|sealed|async|extern|unsafe|\s)*void\s+{name}\s*\("

_HOT_PATTERNS: dict[str, tuple[str, str, str]] = {
    "PERF_FIND_IN_HOT_PATH": (
        r"\b(?:Object\.)?FindObjectOfType\s*<|\bFindAnyObjectByType\s*<|\bFindObjectsOfType\s*<|\bGameObject\.Find\s*\(",
        "Object lookup (Find*) inside a per-frame method.",
        "Cache the reference in Awake/Start or inject it via the inspector.",
    ),
    "PERF_GETCOMPONENT_IN_HOT_PATH": (
        r"\bGetComponent(?:InChildren|InParent)?\s*<",
        "GetComponent* called in a per-frame method.",
        "Cache the component once; prefer TryGetComponent in Unity 2019.2+.",
    ),
    "PERF_STRING_ALLOC_IN_HOT_PATH": (
        r"(?:\"[^\"]*\"\s*\+|\+\s*\"[^\"]*\"|\$\"[^\"]*\")",
        "String concatenation/interpolation in a per-frame method, allocating every frame.",
        "Build strings only when needed; use StringBuilder or cache the result.",
    ),
    "PERF_LINQ_IN_HOT_PATH": (
        r"(?:\.Select\(|\.Where\(|\.OrderBy\(|\.ToList\(|\.ToArray\(|\bEnumerable\.)",
        "LINQ usage in a per-frame method typically allocates and enumerates.",
        "Measure with the Profiler before refactoring; iterate a cached list if it is hot.",
    ),
    "PERF_CAMERA_MAIN": (
        r"\bCamera\.main\b",
        "Camera.main performs a tag lookup; in recent Unity versions it is cached internally, but repeated use in hot paths is still a smell.",
        "Cache Camera.main in a field if used often.",
    ),
}

_SYNC_IO_PATTERNS: dict[str, tuple[str, str, str]] = {
    "PERF_SYNC_IO": (
        r"\bFile\.(?:ReadAllText|ReadAllBytes|WriteAllText|WriteAllBytes|Open)\s*\(|"
        r"\bnew\s+StreamReader\s*\(|\bnew\s+StreamWriter\s*\(",
        "Synchronous file I/O in a runtime script.",
        "Use async APIs or load through Unity's asset pipeline / Addressables.",
    ),
}


@dataclass
class HotMethod:
    """A method body discovered by the lightweight scanner."""

    name: str
    start_line: int
    body: str


def _find_method_body(text: str, method_name: str) -> tuple[int, str] | None:
    """Return ``(start_line, body)`` for a method, using brace matching."""
    pattern = re.compile(_METHOD_HEADER.format(name=re.escape(method_name)))
    match = pattern.search(text)
    if not match:
        return None
    brace_start = text.find("{", match.end())
    if brace_start == -1:
        return None
    depth = 0
    for idx in range(brace_start, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                line = text.count("\n", 0, match.start()) + 1
                return line, text[brace_start : idx + 1]
    return None


def inspect_script(path: Path, root: Path | None = None, hot_methods: tuple[str, ...] = ("Update", "FixedUpdate", "LateUpdate", "OnGUI")) -> list[Finding]:
    """Inspect one C# file for heuristic performance smells."""
    rel = path.relative_to(root).as_posix() if root else path.name
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        LOGGER.debug("Cannot read %s: %s", path, exc)
        return []

    findings: list[Finding] = []
    for method in hot_methods:
        found = _find_method_body(text, method)
        if not found:
            continue
        start_line, body = found
        for code, (pattern, message, recommendation) in _HOT_PATTERNS.items():
            match = re.search(pattern, body)
            if match:
                findings.append(
                    Finding(
                        code=code,
                        message=f"{message} (heuristic, not profiled)",
                        severity=Severity.INFO,
                        path=rel,
                        line=start_line + body.count("\n", 0, match.start()),
                        confidence=Confidence.LOW,
                        evidence=body[match.start() : match.start() + 80].replace("\n", " ").strip(),
                        recommendation=recommendation,
                        category="performance",
                    )
                )
    for code, (pattern, message, recommendation) in _SYNC_IO_PATTERNS.items():
        match = re.search(pattern, text)
        if match:
            findings.append(
                Finding(
                    code=code,
                    message=f"{message} (heuristic)",
                    severity=Severity.INFO,
                    path=rel,
                    line=text.count("\n", 0, match.start()) + 1,
                    confidence=Confidence.LOW,
                    evidence=text[match.start() : match.start() + 80].replace("\n", " ").strip(),
                    recommendation=recommendation,
                    category="performance",
                )
            )
    return findings


def inspect_project(root: Path, script_paths: list[str], config=None) -> list[Finding]:
    """Inspect every script in the project."""
    hot = ("Update", "FixedUpdate", "LateUpdate", "OnGUI")
    if config is not None:
        configured = config.get("performance.hot_methods")
        if isinstance(configured, list) and configured:
            hot = tuple(str(name) for name in configured)
    findings: list[Finding] = []
    for rel in script_paths:
        findings.extend(inspect_script(root / rel, root, hot))
    return findings
