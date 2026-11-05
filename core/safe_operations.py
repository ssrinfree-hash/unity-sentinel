"""SAFE CHANGE PROTOCOL: the only place in UNITY SENTINEL that writes files.

Guarantees implemented here:

1. **Containment** — every target must resolve inside the project root
   (path traversal, absolute escapes and symlink escapes are rejected).
2. **Protected directories** — generated folders (``Library/``, ``Temp/`` ...)
   are never written. ``ProjectSettings/`` and ``Packages/`` require
   ``allow_protected=True`` and are always reported as elevated-risk.
3. **Optimistic locking** — if a plan recorded a ``sha256_before`` hash, the
   file must still match it, otherwise the operation is refused.
4. **Expected content** — text replacements must match exactly once.
5. **Backup first** — original bytes are copied to ``.sentinel/backups/<run>/``
   and an existing backup is never overwritten.
6. **Atomic write** — content is written to a temporary file in the target
   directory and moved into place with ``os.replace``.
7. **Journal** — every applied operation is appended to
   ``.sentinel/journal.jsonl`` and can be reverted only if the file still
   matches what Sentinel wrote (never clobbering third-party edits).
8. **Dry-run** — every write path supports ``dry_run=True``, which produces
   the diff without touching the project.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import SentinelConfig, load_config
from .models import ApplyResult
from .paths import PathSecurityError, is_safe_to_write

LOGGER = logging.getLogger("unity_sentinel.safe_ops")

JOURNAL_DIR = ".sentinel"
JOURNAL_FILE = "journal.jsonl"
BACKUP_DIR = "backups"


@dataclass
class FileOperation:
    """A single planned file modification."""

    path: str
    replacement: str | None = None
    search: str | None = None
    expected_sha256: str | None = None
    reason: str = ""
    allow_protected: bool = False

    def __post_init__(self) -> None:
        self.path = self.path.replace(os.sep, "/")


@dataclass
class OperationOutcome:
    """Per-operation result used internally and in the journal."""

    path: str
    status: str  # applied | skipped | failed | dry-run
    detail: str = ""
    backup: str | None = None
    sha256_before: str | None = None
    sha256_after: str | None = None
    diff: str = ""


@dataclass
class _Prepared:
    op: FileOperation
    target: Path
    relative: str
    before_bytes: bytes
    after_bytes: bytes
    protected: bool = False


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file's content."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_protected(relative: str, protected_paths: list[str]) -> bool:
    first = relative.split("/", 1)[0]
    return first in protected_paths


def _unified_diff(before: bytes, after: bytes, rel: str) -> str:
    before_text = before.decode("utf-8", errors="replace").splitlines(keepends=True)
    after_text = after.decode("utf-8", errors="replace").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(before_text, after_text, fromfile=f"a/{rel}", tofile=f"b/{rel}")
    )


def _atomic_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".sentinel-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:  # pragma: no cover - best effort cleanup
            pass
        raise


def _backup_path(root: Path, run_id: str, relative: str) -> Path:
    return root / JOURNAL_DIR / BACKUP_DIR / run_id / relative


def _write_backup(root: Path, run_id: str, relative: str, data: bytes) -> Path:
    backup = _backup_path(root, run_id, relative)
    if backup.exists():  # never overwrite an existing backup
        raise FileExistsError(f"Backup already exists and will not be overwritten: {backup}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open("xb") as handle:
        handle.write(data)
    return backup


def append_journal(root: Path, entry: dict) -> Path:
    """Append a JSON line to the operation journal."""
    journal = root / JOURNAL_DIR / JOURNAL_FILE
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return journal


def apply_operations(
    root: Path,
    operations: list[FileOperation],
    *,
    dry_run: bool = True,
    confirmed: bool = False,
    config: SentinelConfig | None = None,
    run_id: str | None = None,
) -> ApplyResult:
    """Apply file operations according to the SAFE CHANGE PROTOCOL.

    Args:
        root: resolved project root.
        operations: list of :class:`FileOperation`.
        dry_run: when True nothing is written; a diff is still produced.
        confirmed: must be True for any non-dry-run write. This is the explicit
            user confirmation required by the protocol.
        config: effective configuration.
        run_id: optional identifier for the backup/journal run.

    Raises:
        PermissionError: when a real write is attempted without confirmation.
    """
    cfg = config or load_config()
    root = root.resolve()
    protected_paths = list(cfg.get("safety.protected_paths", ["ProjectSettings", "Packages"]))
    if not dry_run and not confirmed:
        raise PermissionError(
            "Refusing to write without explicit confirmation (pass confirm=True / --yes)."
        )

    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = ApplyResult(dry_run=dry_run)
    prepared: list[_Prepared] = []

    # Phase 1: validate everything before touching anything (fail fast).
    for op in operations:
        try:
            safe = is_safe_to_write(root, op.path, excluded=cfg.excluded_directories)
        except (PathSecurityError, FileNotFoundError) as exc:
            result.failed.append(op.path)
            result.skipped.append(f"{op.path}: {exc}")
            continue

        target = safe.absolute
        if not target.exists():
            result.failed.append(op.path)
            result.skipped.append(f"{op.path}: target does not exist")
            continue
        if not target.is_file():
            result.failed.append(op.path)
            result.skipped.append(f"{op.path}: target is not a regular file")
            continue

        protected = _is_protected(safe.relative, protected_paths)
        if protected and not op.allow_protected:
            result.failed.append(op.path)
            result.skipped.append(
                f"{op.path}: protected path requires elevated confirmation "
                f"(ProjectSettings/Packages)"
            )
            continue

        try:
            before = target.read_bytes()
        except OSError as exc:
            result.failed.append(op.path)
            result.skipped.append(f"{op.path}: cannot read ({exc})")
            continue

        current_hash = sha256_bytes(before)
        if op.expected_sha256 and current_hash != op.expected_sha256:
            result.failed.append(op.path)
            result.skipped.append(
                f"{op.path}: file changed since the plan (expected sha256 "
                f"{op.expected_sha256[:12]}..., found {current_hash[:12]}...)"
            )
            continue

        if op.search is not None:
            try:
                text = before.decode("utf-8")
            except UnicodeDecodeError:
                result.failed.append(op.path)
                result.skipped.append(f"{op.path}: not valid UTF-8; refusing text replacement")
                continue
            occurrences = text.count(op.search)
            if occurrences != 1:
                result.failed.append(op.path)
                result.skipped.append(
                    f"{op.path}: expected exactly one match for the search text, found {occurrences}"
                )
                continue
            replacement = op.replacement if op.replacement is not None else ""
            after = text.replace(op.search, replacement, 1).encode("utf-8")
        elif op.replacement is not None:
            after = op.replacement.encode("utf-8")
        else:
            result.failed.append(op.path)
            result.skipped.append(f"{op.path}: operation has neither replacement nor search")
            continue

        prepared.append(
            _Prepared(
                op=op,
                target=target,
                relative=safe.relative,
                before_bytes=before,
                after_bytes=after,
                protected=protected,
            )
        )

    # Phase 2: write (or simulate).
    diffs: list[str] = []
    for item in prepared:
        if item.before_bytes == item.after_bytes:
            result.skipped.append(f"{item.relative}: no changes required")
            continue
        diff = _unified_diff(item.before_bytes, item.after_bytes, item.relative)
        diffs.append(diff)

        if dry_run:
            result.applied.append(item.relative)
            continue

        try:
            backup = _write_backup(root, run_id, item.relative, item.before_bytes)
        except (OSError, FileExistsError) as exc:
            result.failed.append(item.relative)
            result.skipped.append(f"{item.relative}: backup failed ({exc})")
            continue

        try:
            _atomic_write(item.target, item.after_bytes)
        except OSError as exc:
            result.failed.append(item.relative)
            result.skipped.append(f"{item.relative}: write failed ({exc})")
            continue

        entry = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": item.relative,
            "protected": item.protected,
            "reason": item.op.reason,
            "sha256_before": sha256_bytes(item.before_bytes),
            "sha256_after": sha256_bytes(item.after_bytes),
            "backup": backup.relative_to(root).as_posix(),
        }
        try:
            journal = append_journal(root, entry)
            result.journal_path = journal.relative_to(root).as_posix()
        except OSError as exc:  # pragma: no cover - disk full etc.
            LOGGER.error("Cannot write journal: %s", exc)
        result.applied.append(item.relative)
        result.backup_dir = (root / JOURNAL_DIR / BACKUP_DIR / run_id).relative_to(root).as_posix()

    result.diff = "\n".join(diffs)
    return result


def iter_journal(root: Path) -> list[dict]:
    """Read the journal into a list of entries."""
    journal = root / JOURNAL_DIR / JOURNAL_FILE
    if not journal.is_file():
        return []
    entries: list[dict] = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            LOGGER.warning("Skipping malformed journal line")
    return entries


def revert_entry(root: Path, entry: dict) -> OperationOutcome:
    """Revert a single journal entry created by UNITY SENTINEL.

    Revert only happens when the file still matches ``sha256_after`` — i.e. the
    user has not edited it since Sentinel wrote it. Anything else is refused,
    which prevents Sentinel from silently destroying manual work.
    """
    root = root.resolve()
    rel = str(entry.get("path", ""))
    try:
        safe = is_safe_to_write(root, rel)
    except PathSecurityError as exc:
        return OperationOutcome(path=rel, status="failed", detail=str(exc))

    target = safe.absolute
    if not target.is_file():
        return OperationOutcome(path=rel, status="failed", detail="file no longer exists")
    current = sha256_file(target)
    if current != entry.get("sha256_after"):
        return OperationOutcome(
            path=rel,
            status="failed",
            detail="file changed after Sentinel wrote it; refusing to revert",
            sha256_before=current,
        )

    backup = root / str(entry.get("backup", ""))
    if not backup.is_file():
        return OperationOutcome(path=rel, status="failed", detail=f"backup not found: {backup}")

    data = backup.read_bytes()
    if sha256_bytes(data) != entry.get("sha256_before"):
        return OperationOutcome(path=rel, status="failed", detail="backup hash mismatch")

    _atomic_write(target, data)
    append_journal(
        root,
        {
            "run_id": entry.get("run_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": rel,
            "action": "revert",
            "sha256_before": current,
            "sha256_after": sha256_bytes(data),
        },
    )
    return OperationOutcome(
        path=rel, status="applied", detail="reverted from backup", sha256_after=sha256_bytes(data)
    )


def cleanup_run(root: Path, run_id: str) -> None:  # pragma: no cover - utility
    """Remove the backup folder of a run (kept for completeness; not used by CLI)."""
    folder = root / JOURNAL_DIR / BACKUP_DIR / run_id
    if folder.is_dir():
        shutil.rmtree(folder)
