"""Minimal, read-only helpers for Unity's text-serialised YAML.

Unity YAML is *not* standard YAML (it uses ``--- !u!<classID> &<fileID>``
document markers and custom tags), so parsing it with a generic YAML loader
requires hacks. For the structural checks in UNITY SENTINEL a small,
line-oriented parser is sufficient and much safer.

This module never modifies files. It is intentionally conservative: anything
it cannot understand is reported as "unknown" rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_DOC_HEADER_RE = re.compile(r"^--- !u!(\d+) &(-?\d+)", re.MULTILINE)
_YAML_HEADER = "%YAML"
_UNITY_HEADER = "%TAG !u! tag:unity3d.com,2011:"
_MISSING_SCRIPT_RE = re.compile(r"m_Script:\s*\{fileID:\s*0\}", re.MULTILINE)
_FILEID_RE = re.compile(r"^(?:  )?m_[A-Za-z]+:\s*\{fileID:\s*(-?\d+)", re.MULTILINE)

# Unity class IDs that are useful for structural checks.
CLASS_GAMEOBJECT = "1"
CLASS_TRANSFORM = "4"
CLASS_MONOBEHAVIOUR = "114"
CLASS_SCRIPTABLE_OBJECT = "114"


@dataclass
class UnityDocument:
    """A single ``--- !u!`` document inside a Unity YAML file."""

    class_id: str
    file_id: str
    line: int
    body: str


@dataclass
class UnityYamlInfo:
    """Summary extracted from a text-serialised Unity asset."""

    is_text: bool = False
    has_unity_header: bool = False
    documents: list[UnityDocument] = field(default_factory=list)
    class_counts: dict[str, int] = field(default_factory=dict)
    duplicate_file_ids: list[str] = field(default_factory=list)
    missing_script_lines: list[int] = field(default_factory=list)
    parse_error: str | None = None


def read_unity_yaml(path: Path, max_bytes: int = 32 * 1024 * 1024) -> UnityYamlInfo:
    """Parse structural information out of a Unity YAML file."""
    info = UnityYamlInfo()
    try:
        if path.stat().st_size > max_bytes:
            info.parse_error = "file exceeds size limit"
            return info
        raw = path.read_bytes()
    except OSError as exc:
        info.parse_error = f"cannot read file: {exc}"
        return info

    if raw.startswith(b"\x00") or b"\x00" in raw[:64]:
        info.is_text = False
        return info

    text = raw.decode("utf-8", errors="replace")
    info.is_text = True
    info.has_unity_header = text.startswith(_YAML_HEADER) and _UNITY_HEADER in text[:512]

    matches = list(_DOC_HEADER_RE.finditer(text))
    if not matches:
        info.parse_error = "no Unity YAML documents (--- !u!...) found"
        return info

    seen: set[str] = set()
    for idx, match in enumerate(matches):
        class_id, file_id = match.group(1), match.group(2)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        line = text.count("\n", 0, match.start()) + 1
        info.documents.append(
            UnityDocument(class_id=class_id, file_id=file_id, line=line, body=text[start:end])
        )
        info.class_counts[class_id] = info.class_counts.get(class_id, 0) + 1
        if file_id in seen:
            info.duplicate_file_ids.append(file_id)
        seen.add(file_id)

    for match in _MISSING_SCRIPT_RE.finditer(text):
        info.missing_script_lines.append(text.count("\n", 0, match.start()) + 1)

    return info
