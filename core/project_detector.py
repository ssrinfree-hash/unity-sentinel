"""Detect Unity project facts from files that are safe to read.

The detector only reports what it can prove from files on disk. Anything it
cannot establish (for example the render pipeline when ``manifest.json`` is
missing) is reported as ``unknown`` with a low confidence instead of a guess.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import Confidence, UnityProjectInfo
from .paths import looks_like_unity_project, resolve_project_root

LOGGER = logging.getLogger("unity_sentinel.detector")

_URP_PACKAGES = ("com.unity.render-pipelines.universal",)
_HDRP_PACKAGES = ("com.unity.render-pipelines.high-definition",)


def _read_text(path: Path, limit: int = 256 * 1024) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError as exc:  # pragma: no cover - depends on OS permissions
        LOGGER.warning("Cannot read %s: %s", path, exc)
        return None


def read_unity_version(root: Path) -> tuple[str | None, str | None]:
    """Read ``ProjectSettings/ProjectVersion.txt``.

    Returns a ``(version, source)`` tuple. The version is ``None`` when the
    file is missing or malformed — we never infer a Unity version from
    unrelated evidence.
    """
    version_file = root / "ProjectSettings" / "ProjectVersion.txt"
    if not version_file.is_file():
        return None, None
    text = _read_text(version_file)
    if not text:
        return None, str(version_file)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("m_EditorVersion:"):
            value = line.split(":", 1)[1].strip()
            return (value or None), "ProjectSettings/ProjectVersion.txt"
    return None, "ProjectSettings/ProjectVersion.txt"


def read_manifest(root: Path) -> tuple[dict | None, str | None]:
    """Read ``Packages/manifest.json``.

    Returns ``(manifest, error)``; the error is a short human readable string
    suitable for reports (never a full traceback).
    """
    manifest_path = root / "Packages" / "manifest.json"
    if not manifest_path.is_file():
        return None, None
    text = _read_text(manifest_path)
    if text is None:
        return None, "manifest.json is not readable"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"manifest.json is not valid JSON (line {exc.lineno}, column {exc.colno})"
    if not isinstance(parsed, dict):
        return None, "manifest.json must contain a JSON object"
    return parsed, None


def detect_render_pipeline(root: Path, manifest: dict | None) -> tuple[str, Confidence, str | None]:
    """Determine the render pipeline from available evidence only."""
    dependencies: dict = {}
    if isinstance(manifest, dict):
        raw_deps = manifest.get("dependencies")
        if isinstance(raw_deps, dict):
            dependencies = raw_deps

    for pkg in _URP_PACKAGES:
        if pkg in dependencies:
            return "URP", Confidence.HIGH, f"package {pkg} declared in manifest.json"
    for pkg in _HDRP_PACKAGES:
        if pkg in dependencies:
            return "HDRP", Confidence.HIGH, f"package {pkg} declared in manifest.json"

    # GraphicsSettings gives a strong signal even without a manifest.
    graphics = root / "ProjectSettings" / "GraphicsSettings.asset"
    if graphics.is_file():
        text = _read_text(graphics) or ""
        if "UniversalRenderPipelineAsset" in text or "UniversalRenderPipeline" in text:
            return "URP", Confidence.MEDIUM, "UniversalRenderPipelineAsset referenced in ProjectSettings/GraphicsSettings.asset"
        if "HDRenderPipelineAsset" in text or "HDRenderPipeline" in text:
            return "HDRP", Confidence.MEDIUM, "HDRenderPipelineAsset referenced in ProjectSettings/GraphicsSettings.asset"
        if manifest is not None:
            return "Built-in", Confidence.LOW, "no SRP package declared; GraphicsSettings has no SRP asset reference"

    return "unknown", Confidence.LOW, None


def detect_scripting_backend(root: Path) -> str | None:
    """Read ``apiCompatibilityLevel``/``scriptingBackend`` hints where possible.

    Unity stores these per platform inside ``ProjectSettings.asset``. The file
    is a YAML-ish asset; we only read simple scalar keys and never modify it.
    """
    settings = root / "ProjectSettings" / "ProjectSettings.asset"
    if not settings.is_file():
        return None
    text = _read_text(settings)
    if not text:
        return None
    for key in ("scriptingBackend", "apiCompatibilityLevel"):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(key + ":"):
                value = stripped.split(":", 1)[1].strip()
                if value and value != "{}":
                    return f"{key}={value}"
    return None


def detect_platforms(root: Path) -> list[str]:
    """List target platforms that are explicitly enabled in build settings."""
    platforms: list[str] = []
    settings = root / "ProjectSettings" / "EditorBuildSettings.asset"
    if settings.is_file():
        text = _read_text(settings) or ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("path:") or stripped.startswith("- enabled:"):
                continue
        if "m_Scenes:" in text:
            platforms.append("scenes-configured")
    # Platform toggles live in ProjectSettings.asset; we only surface names we
    # can actually see, never defaults.
    project_settings = root / "ProjectSettings" / "ProjectSettings.asset"
    if project_settings.is_file():
        text = _read_text(project_settings) or ""
        for platform in ("Android", "iPhone", "WebGL", "Standalone", "tvOS"):
            if f"{platform}:" in text or f"  {platform}:" in text:
                platforms.append(platform)
    return sorted(set(platforms))


def detect_project(raw_path: str | Path) -> UnityProjectInfo:
    """Build a :class:`UnityProjectInfo` for the given path."""
    root = resolve_project_root(raw_path)
    info = UnityProjectInfo(root=".", is_unity_project=looks_like_unity_project(root))

    if not info.is_unity_project:
        info.notes.append(
            "Assets/ was not found; this does not look like a Unity project root."
        )
        return info

    version, source = read_unity_version(root)
    info.unity_version = version
    info.unity_version_source = source
    if version is None:
        info.notes.append(
            "ProjectSettings/ProjectVersion.txt is missing or has no m_EditorVersion; "
            "Unity version is unknown."
        )

    manifest, manifest_error = read_manifest(root)
    info.manifest_present = (root / "Packages" / "manifest.json").is_file()
    info.manifest_parse_error = manifest_error
    info.packages_lock_present = (root / "Packages" / "packages-lock.json").is_file()

    if isinstance(manifest, dict):
        deps = manifest.get("dependencies")
        if isinstance(deps, dict):
            info.packages = sorted(str(name) for name in deps.keys())
    if manifest_error:
        info.notes.append(manifest_error)
    elif not info.manifest_present:
        info.notes.append("Packages/manifest.json is missing; package list is unknown.")

    pipeline, confidence, evidence = detect_render_pipeline(root, manifest)
    info.render_pipeline = pipeline
    info.render_pipeline_confidence = confidence
    info.render_pipeline_evidence = evidence

    info.scripting_backend = detect_scripting_backend(root)
    info.platforms = detect_platforms(root)
    return info
