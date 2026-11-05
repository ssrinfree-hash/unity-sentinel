"""Configuration loading with safe defaults.

Configuration is JSON (per the spec) and is merged over the defaults shipped in
``config/default.json``. Unknown keys are ignored on purpose so that a newer
config file never breaks an older tool version.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import DEFAULT_EXCLUDED_DIRECTORIES

LOGGER = logging.getLogger("unity_sentinel.config")

DEFAULT_CONFIG: dict[str, Any] = {
    "scan": {
        "exclude_directories": list(DEFAULT_EXCLUDED_DIRECTORIES),
        "max_file_size_bytes": 8 * 1024 * 1024,
        "max_files": 200_000,
        "max_depth": 40,
        "follow_symlinks": False,
    },
    "meta": {
        "ignore_root_level_meta": True,
        "treat_orphan_meta_as_warning": True,
    },
    "references": {
        "scan_extensions": [".unity", ".prefab", ".asset", ".mat", ".anim", ".controller", ".overrideController", ".playable", ".mask", ".physicMaterial", ".preset", ".spriteatlas"],
        "max_file_size_bytes": 16 * 1024 * 1024,
    },
    "safety": {
        "require_confirmation_for_apply": True,
        "backup_dir": ".sentinel/backups",
        "journal_path": ".sentinel/journal.jsonl",
        "protected_paths": ["ProjectSettings", "Packages"],
    },
    "report": {
        "omit_absolute_paths": True,
        "max_evidence_length": 200,
    },
    "performance": {
        "hot_methods": ["Update", "FixedUpdate", "LateUpdate", "OnGUI"],
    },
}


@dataclass
class SentinelConfig:
    """Merged, read-only view over the effective configuration."""

    data: dict[str, Any] = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_CONFIG)))
    source: str = "defaults"

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Read a nested value using a dotted key such as ``scan.max_files``."""
        node: Any = self.data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def excluded_directories(self) -> list[str]:
        return list(self.get("scan.exclude_directories", DEFAULT_EXCLUDED_DIRECTORIES))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.data))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> SentinelConfig:
    """Load configuration from ``path``; fall back to safe defaults.

    A malformed configuration file raises ``ValueError`` — silently ignoring it
    would make runs irreproducible.
    """
    data = json.loads(json.dumps(DEFAULT_CONFIG))
    source = "defaults"

    candidates: list[Path] = []
    if path is not None:
        candidates = [Path(path)]
    else:
        candidates = [
            Path.cwd() / ".sentinel" / "config.json",
            Path(__file__).resolve().parent.parent / "config" / "default.json",
        ]

    for candidate in candidates:
        if candidate.is_file():
            try:
                parsed = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON configuration at {candidate}: {exc}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"Configuration at {candidate} must be a JSON object")
            data = _deep_merge(data, parsed)
            source = str(candidate)
            break

    LOGGER.debug("Loaded configuration from %s", source)
    return SentinelConfig(data=data, source=source)
