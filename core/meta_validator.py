"""``.meta`` file validation.

Checks performed (file-based, deterministic):

* ``META_MISSING`` — an asset inside ``Assets/`` has no sibling ``.meta``.
* ``META_ORPHAN`` — a ``.meta`` file has no corresponding asset.
* ``META_INVALID`` — the ``.meta`` file has no parsable ``guid``.
* ``META_INVALID_GUID_FORMAT`` — guid does not match the 32 lowercase hex format.
* ``META_DUPLICATE_GUID`` — the same guid is used by more than one ``.meta``.

The validator **never** edits ``.meta`` files: a changed GUID silently breaks
every serialised reference in scenes, prefabs and assets.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import Confidence, Finding, Severity

LOGGER = logging.getLogger("unity_sentinel.meta")

_GUID_RE = re.compile(r"^guid:\s*([0-9a-zA-Z]+)\s*$", re.MULTILINE)
_VALID_GUID_RE = re.compile(r"^[0-9a-f]{32}$")
# Unity writes .meta for folders, and for its own hidden assets (e.g. cvs).
_IGNORED_META_NAMES = {"cvs.meta"}


@dataclass
class MetaIndex:
    """Result of indexing ``.meta`` files."""

    guids: dict[str, list[str]] = field(default_factory=dict)  # guid -> [meta paths]
    path_to_guid: dict[str, str] = field(default_factory=dict)  # asset path -> guid
    invalid: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    orphan: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    @property
    def known_guids(self) -> set[str]:
        return set(self.guids)


def read_guid(meta_path: Path) -> str | None:
    """Extract the ``guid`` value from a ``.meta`` file, or ``None``."""
    try:
        with meta_path.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(4096)
    except OSError as exc:
        LOGGER.debug("Cannot read %s: %s", meta_path, exc)
        return None
    match = _GUID_RE.search(head)
    return match.group(1) if match else None


def iter_assets(assets_root: Path) -> tuple[list[Path], list[Path]]:
    """Return (asset files, meta files) below ``Assets/`` (files and folders)."""
    assets: list[Path] = []
    metas: list[Path] = []
    for path in sorted(assets_root.rglob("*")):
        if path.name.endswith("~"):
            continue
        if path.is_symlink() and not path.resolve().is_relative_to(assets_root.resolve()):
            continue
        if path.suffix == ".meta" and path.is_file():
            metas.append(path)
        elif path.is_file():
            assets.append(path)
        elif path.is_dir():
            # Folders are assets too and must have .meta files.
            assets.append(path)
    return assets, metas


def build_meta_index(root: Path, *, ignore_root_level_meta: bool = True) -> MetaIndex:
    """Index every ``.meta`` file below the project root.

    Folders under ``Assets/`` are assets in Unity's asset database and are
    therefore required to have ``.meta`` files as well. ``ignore_root_level_meta``
    controls whether stray ``*.meta`` files directly at the *project* root
    (outside ``Assets/``, where they are not managed by Unity) are reported as
    orphans.
    """
    index = MetaIndex()
    assets_root = root / "Assets"
    if not assets_root.is_dir():
        return index

    assets, metas = iter_assets(assets_root)
    asset_paths = {path for path in assets}
    meta_by_asset: dict[Path, Path] = {}
    for meta in metas:
        asset = meta.with_suffix("")
        meta_by_asset[asset] = meta
        guid = read_guid(meta)
        rel_meta = meta.relative_to(root).as_posix()
        if guid is None:
            index.invalid.append(rel_meta)
            continue
        if not _VALID_GUID_RE.match(guid):
            index.invalid.append(rel_meta)
            index.guids.setdefault(guid, []).append(rel_meta)
            continue
        index.guids.setdefault(guid, []).append(rel_meta)
        index.path_to_guid[asset.relative_to(root).as_posix()] = guid

    for asset in assets:
        if asset == assets_root:
            continue
        if asset not in meta_by_asset:
            index.missing.append(asset.relative_to(root).as_posix())

    for asset, meta in meta_by_asset.items():
        if not asset.exists() and meta.name not in _IGNORED_META_NAMES:
            index.orphan.append(meta.relative_to(root).as_posix())

    if not ignore_root_level_meta:
        for stray in sorted(root.glob("*.meta")):
            index.orphan.append(stray.relative_to(root).as_posix())

    return index


def validate_meta(root: Path, *, config=None) -> tuple[MetaIndex, list[Finding]]:
    """Validate ``.meta`` files and return the index plus findings."""
    ignore_root = True
    if config is not None:
        ignore_root = bool(config.get("meta.ignore_root_level_meta", True))
    index = build_meta_index(root, ignore_root_level_meta=ignore_root)
    findings: list[Finding] = []

    for rel in index.missing:
        findings.append(
            Finding(
                code="META_MISSING",
                message="Asset has no .meta file; Unity will generate a new GUID on import.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Let Unity regenerate the .meta, or restore it from version control.",
                category="meta",
            )
        )
    for rel in index.orphan:
        findings.append(
            Finding(
                code="META_ORPHAN",
                message="Orphan .meta file without a corresponding asset.",
                severity=Severity.WARNING,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Delete the orphan only if you are sure the asset was removed intentionally.",
                category="meta",
            )
        )
    for rel in index.invalid:
        findings.append(
            Finding(
                code="META_INVALID",
                message="Meta file has no parsable 32-character hexadecimal guid.",
                severity=Severity.ERROR,
                path=rel,
                confidence=Confidence.HIGH,
                recommendation="Do not invent a GUID; restore the original .meta from version control.",
                category="meta",
            )
        )
    for guid, rel_paths in sorted(index.guids.items()):
        if len(rel_paths) > 1:
            findings.append(
                Finding(
                    code="META_DUPLICATE_GUID",
                    message=f"GUID {guid} is used by {len(rel_paths)} meta files.",
                    severity=Severity.ERROR,
                    path=sorted(rel_paths)[0],
                    confidence=Confidence.HIGH,
                    evidence=", ".join(sorted(rel_paths)[:5]),
                    recommendation="Restore one of the assets from version control; never rewrite GUIDs blindly.",
                    category="meta",
                )
            )
    return index, findings
