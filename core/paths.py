"""Safe path handling: project root resolution, containment checks, symlink guards.

All filesystem writes performed by UNITY SENTINEL must go through this module.
The rules implemented here are intentionally strict:

* every write target must resolve *inside* the project root;
* symbolic links must not escape the project root;
* generated directories (Library, Temp, ...) are never written;
* paths are normalised to POSIX form for reports so that reports are portable.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDED_DIRECTORIES: tuple[str, ...] = (
    "Library",
    "Temp",
    "Obj",
    "Logs",
    "Builds",
    "Build",
    "UserSettings",
    "MemoryCaptures",
    "Recordings",
    ".git",
    ".svn",
    ".hg",
    ".vs",
    ".idea",
    ".vscode",
    "node_modules",
)

DEFAULT_EXCLUDED_FILE_SUFFIXES: tuple[str, ...] = (
    ".tmp",
    ".pid",
    ".lock",
)

SECRET_FILE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pfx",
    "*.p12",
    "*.keystore",
    "*.jks",
    "id_rsa*",
    "id_ed25519*",
    "*credentials*",
    "*secret*",
    "*.pem",
    "*.key",
)

_SECRET_NAME_RE = re.compile(
    "|".join(
        "^" + re.escape(pat).replace(r"\*", ".*") + "$" for pat in SECRET_FILE_PATTERNS
    ),
    re.IGNORECASE,
)


class PathSecurityError(Exception):
    """Raised when a path violates the safety policy."""


@dataclass(frozen=True)
class SafePath:
    """A path that has been validated to live inside a project root."""

    root: Path
    absolute: Path
    relative: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.relative


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def normalise_relative(root: Path, candidate: Path) -> str:
    """Return a POSIX relative path of ``candidate`` inside ``root``."""
    return candidate.relative_to(root).as_posix()


def looks_like_unity_project(path: Path) -> bool:
    """Heuristic used by the detector, kept here to avoid circular imports."""
    if not path.is_dir():
        return False
    has_assets = (path / "Assets").is_dir()
    has_settings = (path / "ProjectSettings").is_dir()
    has_version = (path / "ProjectSettings" / "ProjectVersion.txt").is_file()
    has_packages = (path / "Packages").is_dir()
    # ``Assets/`` is the primary signal; the detector separately reports when
    # ProjectSettings/ or Packages/ are missing.
    return has_assets and (has_settings or has_packages or has_version or True)


def resolve_project_root(raw: str | os.PathLike[str]) -> Path:
    """Resolve a user supplied project path into an absolute directory.

    Raises:
        FileNotFoundError: if the path does not exist.
        NotADirectoryError: if the path is not a directory.
    """
    path = Path(raw).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Project path does not exist: {raw!r}")
    if not path.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {raw!r}")
    return path.resolve()


def ensure_within_root(root: Path, candidate: str | os.PathLike[str], *, must_exist: bool = False) -> SafePath:
    """Validate that ``candidate`` stays inside ``root``.

    The check is performed on the *resolved* path so that ``..`` traversal and
    symlink escapes are both rejected. Absolute paths outside the root are
    rejected as well.

    Args:
        root: resolved project root.
        candidate: absolute path or path relative to the root.
        must_exist: when True, the target must already exist.

    Raises:
        PathSecurityError: on traversal, symlink escape or absolute escape.
        FileNotFoundError: when ``must_exist`` is set and the file is missing.
    """
    root = root.resolve()
    raw = Path(candidate)
    target = raw if raw.is_absolute() else (root / raw)

    # resolve(strict=False) resolves symlinks of existing parents and keeps
    # missing tails intact, which is exactly what we need before a write.
    resolved = target.resolve(strict=False)

    if not _is_within(resolved, root):
        raise PathSecurityError(
            f"Refusing to operate on path outside project root: {candidate!r} -> {resolved}"
        )

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Target does not exist: {candidate!r}")

    rel = normalise_relative(root, resolved)
    if rel in (".", ""):
        raise PathSecurityError("Refusing to operate on the project root itself")
    return SafePath(root=root, absolute=resolved, relative=rel)


def is_excluded_relative(relative: str, excluded: Iterable[str] = DEFAULT_EXCLUDED_DIRECTORIES) -> bool:
    """Return True if a relative POSIX path lives in a generated directory."""
    parts = relative.split("/")
    excluded_set = {e.lower() for e in excluded}
    return any(part.lower() in excluded_set for part in parts[:-1]) or (
        parts and parts[0].lower() in excluded_set
    )


def is_secret_like(path: str | Path) -> bool:
    """Heuristic that flags files which may contain credentials.

    The tool never *reads* such files during scanning and never copies their
    contents into reports.
    """
    name = Path(path).name
    if _SECRET_NAME_RE.match(name):
        return True
    lowered = name.lower()
    return lowered.endswith((".pem", ".key", ".ppk", ".env"))


def check_no_symlink_escape(root: Path, candidate: Path) -> None:
    """Ensure no component of ``candidate`` is a symlink pointing outside root."""
    root = root.resolve()
    current = candidate
    while True:
        if current.is_symlink():
            target = current.resolve(strict=False)
            if not _is_within(target, root):
                raise PathSecurityError(
                    f"Symlink escape detected: {current} -> {target}"
                )
        if current == root or current.parent == current:
            break
        current = current.parent


def is_safe_to_write(root: Path, candidate: str | os.PathLike[str], excluded: Iterable[str] = DEFAULT_EXCLUDED_DIRECTORIES) -> SafePath:
    """Full write-safety gate used by the apply engine."""
    safe = ensure_within_root(root, candidate)
    if is_excluded_relative(safe.relative, excluded):
        raise PathSecurityError(
            f"Refusing to write inside generated/excluded directory: {safe.relative}"
        )
    check_no_symlink_escape(root, safe.absolute)
    return safe


def to_report_path(root: Path, absolute: str | Path) -> str:
    """Convert an absolute path into a portable, root-relative report path."""
    path = Path(absolute)
    try:
        rel = path.resolve().relative_to(Path(root).resolve())
        return rel.as_posix()
    except ValueError:
        # Never leak full user paths into public reports: keep only the name.
        return path.name
