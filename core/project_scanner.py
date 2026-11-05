"""Read-only project scanner.

Guarantees:

* never writes to the project;
* skips generated directories (Library, Temp, Obj, Logs, Builds, ...);
* never follows symlinks pointing outside the root;
* never reads files above the configured size limit;
* keeps going when an individual file cannot be read.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from .config import SentinelConfig, load_config
from .models import ScanSummary
from .paths import (
    DEFAULT_EXCLUDED_DIRECTORIES,
    is_secret_like,
    resolve_project_root,
)
from .project_detector import detect_project

LOGGER = logging.getLogger("unity_sentinel.scanner")

SCRIPTABLE_OBJECT_HINT = "ScriptableObject"


def scriptable_object_guess(path: Path, max_bytes: int = 64 * 1024) -> bool:
    """Heuristically detect ScriptableObject assets without full parsing.

    Unity stores ScriptableObject instances as YAML assets whose
    ``MonoBehaviour`` block contains ``m_Script``. We look for the
    ``ScriptableObject`` marker in the script the asset points to only when it
    is cheap to do so; otherwise the *asset* is treated as a generic asset.
    """
    try:
        if path.stat().st_size > max_bytes:
            return False
        text = path.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
    except OSError:
        return False
    return "MonoBehaviour:" in text and "m_Script:" in text and "m_Name:" in text


def scan_project(
    raw_path: str | Path,
    *,
    config: SentinelConfig | None = None,
    include_hashes: bool = False,
) -> ScanSummary:
    """Scan a Unity project and return an aggregate summary.

    Args:
        raw_path: path to the Unity project root (a parent folder is accepted
            as long as it contains ``Assets/``).
        config: optional effective configuration.
        include_hashes: reserved for future use; hashing is done by the
            regression engine so that scan stays cheap.

    Returns:
        A populated :class:`ScanSummary`.
    """
    cfg = config or load_config()
    root = resolve_project_root(raw_path)
    excluded = {d.lower() for d in cfg.excluded_directories or DEFAULT_EXCLUDED_DIRECTORIES}
    max_file_size = int(cfg.get("scan.max_file_size_bytes", 8 * 1024 * 1024))
    max_files = int(cfg.get("scan.max_files", 200_000))
    max_depth = int(cfg.get("scan.max_depth", 40))

    started = time.monotonic()
    summary = ScanSummary(root=".")
    summary.project = detect_project(root)

    extension_counts: dict[str, int] = {}
    total_bytes = 0
    total_files = 0

    for child in sorted(root.iterdir()):
        if child.is_dir() and child.name.lower() in excluded:
            summary.skipped_directories.append(child.name)

    scan_roots = [p for p in (root / "Assets", root / "Packages", root / "ProjectSettings") if p.is_dir()]
    if not scan_roots and (root / "Assets").is_dir():  # pragma: no cover - defensive
        scan_roots = [root / "Assets"]

    for scan_root in scan_roots:
        base_depth = 0
        for dirpath, dirnames, filenames in os.walk(scan_root, followlinks=False):
            current = Path(dirpath)
            try:
                depth = len(current.relative_to(root).parts) - base_depth
            except ValueError:  # pragma: no cover - defensive
                depth = 0
            if depth > max_depth:
                summary.skipped_directories.append(current.relative_to(root).as_posix())
                dirnames[:] = []
                continue

            kept_dirs: list[str] = []
            for name in sorted(dirnames):
                child = current / name
                if name.lower() in excluded or name.endswith("~"):
                    summary.skipped_directories.append(child.relative_to(root).as_posix())
                    continue
                if child.is_symlink():
                    try:
                        target = child.resolve(strict=False)
                        target.relative_to(root)
                    except (OSError, ValueError):
                        summary.skipped_directories.append(
                            child.relative_to(root).as_posix() + " (symlink escape)"
                        )
                        continue
                kept_dirs.append(name)
            dirnames[:] = kept_dirs

            for name in sorted(filenames):
                file_path = current / name
                if file_path.is_symlink():
                    try:
                        file_path.resolve(strict=False).relative_to(root)
                    except (OSError, ValueError):
                        summary.skipped_directories.append(
                            file_path.relative_to(root).as_posix() + " (symlink escape)"
                        )
                        continue
                rel = file_path.relative_to(root).as_posix()
                try:
                    stat = file_path.stat()
                except OSError as exc:
                    LOGGER.debug("Cannot stat %s: %s", rel, exc)
                    summary.unreadable_files.append(rel)
                    continue
                if stat.st_size > max_file_size:
                    summary.oversized_files.append(rel)
                    continue

                total_files += 1
                total_bytes += stat.st_size
                if total_files > max_files:
                    summary.truncated = True
                    break

                suffix = file_path.suffix.lower()
                extension_counts[suffix or "<none>"] = extension_counts.get(suffix or "<none>", 0) + 1

                if is_secret_like(file_path):
                    # Never index credential-like files beyond their existence.
                    continue

                if suffix == ".cs":
                    summary.scripts.append(rel)
                elif suffix == ".asmdef":
                    summary.assembly_definitions.append(rel)
                elif suffix == ".asmref":
                    summary.assembly_references.append(rel)
                elif suffix == ".unity":
                    summary.scenes.append(rel)
                elif suffix == ".prefab":
                    summary.prefabs.append(rel)
                elif suffix == ".meta":
                    summary.meta_files.append(rel)
                elif suffix == ".asset" and scriptable_object_guess(file_path):
                    summary.scriptable_objects.append(rel)

            if summary.truncated:
                break
        if summary.truncated:
            break

    summary.extension_counts = dict(sorted(extension_counts.items()))
    summary.total_files = total_files
    summary.total_bytes = total_bytes
    summary.duration_ms = int((time.monotonic() - started) * 1000)
    summary.skipped_directories = sorted(set(summary.skipped_directories))
    return summary
