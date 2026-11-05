"""Orchestration layer: runs checks, builds reports, manages baseline files.

The CLI (``scripts/sentinel.py``) is a thin wrapper around this module so that
integration tests can exercise exactly the same code path.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import SentinelConfig, load_config
from .dependency_analyzer import analyze_dependencies
from .meta_validator import validate_meta
from .models import (
    Check,
    CheckResult,
    Confidence,
    EnvironmentInfo,
    Finding,
    Report,
    ReportMeta,
    Severity,
    Status,
)
from .paths import looks_like_unity_project, resolve_project_root
from .performance_inspector import inspect_project
from .prefab_validator import validate_prefabs
from .project_scanner import scan_project
from .reference_analyzer import scan_references
from .regression_engine import (
    compare,
    create_baseline,
    hash_project_files,
    load_baseline,
    regression_findings,
    save_baseline,
)
from .report_generator import build_report
from .scene_validator import validate_scenes
from .version import TOOL_NAME, __version__

LOGGER = logging.getLogger("unity_sentinel.pipeline")

BASELINE_RELATIVE_PATH = Path(".sentinel") / "baseline.json"


def detect_environment(unity_path: str | None = None) -> EnvironmentInfo:
    """Report availability of external tools without assuming they exist."""
    env = EnvironmentInfo(
        python_version=platform.python_version(),
        python_executable=sys.executable,
        os_name=f"{platform.system()} {platform.release()}",
    )

    git = shutil.which("git")
    if git:
        try:
            out = subprocess.run(
                [git, "--version"], capture_output=True, text=True, timeout=10, check=False
            )
            env.git_available = out.returncode == 0
            env.git_version = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            env.notes.append(f"git check failed: {exc}")
    else:
        env.notes.append("git executable not found on PATH")

    dotnet = shutil.which("dotnet")
    if dotnet:
        try:
            out = subprocess.run(
                [dotnet, "--version"], capture_output=True, text=True, timeout=10, check=False
            )
            env.dotnet_available = out.returncode == 0
            env.dotnet_version = out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            env.notes.append(f"dotnet check failed: {exc}")

    candidate = unity_path or os.environ.get("UNITY_EDITOR_PATH")
    editor_path = None
    if candidate:
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file():
            editor_path = candidate_path
        elif candidate_path.is_dir():
            for guess in (
                candidate_path / "Unity",
                candidate_path / "Unity.exe",
                candidate_path / "Contents" / "MacOS" / "Unity",
            ):
                if guess.is_file():
                    editor_path = guess
                    break
    if editor_path is None:
        found = shutil.which("unity") or shutil.which("Unity")
        if found:
            editor_path = Path(found)

    if editor_path is not None:
        env.unity_editor_available = True
        env.unity_editor_path = str(editor_path)
        try:
            out = subprocess.run(
                [str(editor_path), "-version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            env.unity_editor_version = (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else None
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
            env.notes.append(f"Unity -version failed: {exc}")
    else:
        env.notes.append(
            "Unity Editor not detected. Editor-side scene/prefab validation and Unity tests "
            "were NOT executed; set UNITY_EDITOR_PATH or pass --unity to enable them."
        )
    return env


def _git_status(root: Path) -> str | None:
    git = shutil.which("git")
    if not git or not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(
            [git, "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        return None


def run_analysis(
    root: Path,
    config: SentinelConfig,
    *,
    include_performance: bool = True,
    include_references: bool = True,
    include_scenes: bool = True,
    include_prefabs: bool = True,
) -> tuple[list[Finding], list[Check], list[str], object]:
    """Run all file-based checks.

    Returns:
        ``(findings, checks, limitations, scan_summary)``.
    """
    findings: list[Finding] = []
    checks: list[Check] = []
    limitations: list[str] = []

    scan = scan_project(root, config=config)
    checks.append(
        Check(
            id="scan.project",
            title="Project scan (Assets/Packages/ProjectSettings)",
            result=CheckResult.PASS,
            details=(
                f"{scan.total_files} files, {len(scan.scripts)} C# scripts, "
                f"{len(scan.scenes)} scenes, {len(scan.prefabs)} prefabs, "
                f"{len(scan.meta_files)} meta files"
            ),
        )
    )
    if scan.truncated:
        checks.append(
            Check(
                id="scan.limit",
                title="Scan file limit",
                result=CheckResult.WARN,
                details="Scan limit reached; results are partial. Increase scan.max_files.",
            )
        )
        limitations.append("Scan was truncated by the configured file limit.")
    if scan.oversized_files:
        limitations.append(
            f"{len(scan.oversized_files)} file(s) exceeded the size limit and were skipped."
        )
    if scan.unreadable_files:
        limitations.append(
            f"{len(scan.unreadable_files)} file(s) could not be read and were skipped."
        )

    project = scan.project
    checks.append(
        Check(
            id="detect.unity_version",
            title="Unity version detection",
            result=CheckResult.PASS if project.unity_version else CheckResult.WARN,
            details=f"Unity {project.unity_version}" if project.unity_version else "unknown",
        )
    )
    if not project.unity_version:
        limitations.append("Unity version could not be determined from ProjectVersion.txt.")
        findings.append(
            Finding(
                code="PROJECT_VERSION_UNKNOWN",
                message="Unity version is unknown: ProjectSettings/ProjectVersion.txt is missing or malformed.",
                severity=Severity.WARNING,
                path="ProjectSettings/ProjectVersion.txt",
                confidence=Confidence.HIGH,
                recommendation="Commit ProjectVersion.txt; without it builds and CI cannot be reproduced.",
                category="project",
            )
        )
    if project.manifest_parse_error:
        findings.append(
            Finding(
                code="PROJECT_MANIFEST_INVALID",
                message=f"Packages/manifest.json could not be parsed: {project.manifest_parse_error}",
                severity=Severity.ERROR,
                path="Packages/manifest.json",
                confidence=Confidence.HIGH,
                recommendation="Fix the JSON syntax; Unity cannot resolve packages otherwise.",
                category="project",
            )
        )
    checks.append(
        Check(
            id="detect.render_pipeline",
            title="Render pipeline detection",
            result=CheckResult.PASS if project.render_pipeline != "unknown" else CheckResult.WARN,
            details=f"{project.render_pipeline} ({project.render_pipeline_confidence.value} confidence)",
        )
    )

    # Meta validation
    _, meta_findings = validate_meta(root, config=config)
    findings.extend(meta_findings)
    checks.append(
        Check(
            id="meta.integrity",
            title="Meta file integrity",
            result=CheckResult.PASS if not meta_findings else CheckResult.WARN,
            details=f"{len(meta_findings)} finding(s) across {len(scan.meta_files)} meta files",
        )
    )

    # References
    if include_references:
        from .meta_validator import build_meta_index

        index = build_meta_index(root)
        ref_index, ref_findings = scan_references(
            root,
            index.known_guids,
            extensions=tuple(config.get("references.scan_extensions", ())),
            max_file_size=int(config.get("references.max_file_size_bytes", 16 * 1024 * 1024)),
        )
        findings.extend(ref_findings)
        checks.append(
            Check(
                id="references.guid",
                title="GUID reference scan",
                result=CheckResult.PASS if not ref_findings else CheckResult.WARN,
                details=(
                    f"{ref_index.scanned_files} asset(s) scanned, "
                    f"{ref_index.total_references} reference(s), "
                    f"{len(ref_index.unknown_guids)} unknown GUID(s)"
                ),
            )
        )
        limitations.extend(ref_index.limitations)

    # Dependencies
    dep_findings = analyze_dependencies(root, scan, config)
    findings.extend(dep_findings)
    checks.append(
        Check(
            id="dependencies.assemblies",
            title="Assembly dependency graph",
            result=CheckResult.PASS if not dep_findings else (
                CheckResult.FAIL
                if any(f.severity in (Severity.ERROR, Severity.CRITICAL) for f in dep_findings)
                else CheckResult.WARN
            ),
            details=f"{len(scan.assembly_definitions)} asmdef, {len(dep_findings)} finding(s)",
        )
    )

    # Scenes / prefabs (file level)
    if include_scenes:
        scene_findings = validate_scenes(root, scan.scenes)
        findings.extend(scene_findings)
        checks.append(
            Check(
                id="scenes.structure",
                title="Scene structural validation (file level)",
                result=CheckResult.PASS if not scene_findings else CheckResult.WARN,
                details=f"{len(scan.scenes)} scene(s) checked",
            )
        )
    if include_prefabs:
        prefab_findings = validate_prefabs(root, scan.prefabs)
        findings.extend(prefab_findings)
        checks.append(
            Check(
                id="prefabs.structure",
                title="Prefab structural validation (file level)",
                result=CheckResult.PASS if not prefab_findings else CheckResult.WARN,
                details=f"{len(scan.prefabs)} prefab(s) checked",
            )
        )

    limitations.append(
        "File-level scene/prefab checks cannot resolve serialised references or prefab "
        "overrides; use the Unity Editor module for authoritative validation."
    )
    checks.append(
        Check(
            id="unity.editor_checks",
            title="Unity Editor-side validation",
            result=CheckResult.SKIPPED,
            details="Requires a Unity Editor installation (Editor module / batchmode).",
            requires="unity-editor",
        )
    )
    checks.append(
        Check(
            id="unity.tests",
            title="Unity EditMode/PlayMode tests",
            result=CheckResult.SKIPPED,
            details="Requires a Unity Editor installation.",
            requires="unity-editor",
        )
    )
    limitations.append(
        "Unity EditMode/PlayMode tests were not executed (Unity Editor unavailable)."
    )

    if include_performance:
        perf_findings = inspect_project(root, scan.scripts, config)
        findings.extend(perf_findings)
        checks.append(
            Check(
                id="performance.heuristics",
                title="Performance heuristics (not profiling)",
                result=CheckResult.PASS if not perf_findings else CheckResult.WARN,
                details=f"{len(perf_findings)} heuristic observation(s)",
            )
        )
        limitations.append(
            "Performance findings are heuristics based on code patterns; they are not "
            "profiler measurements."
        )

    return findings, checks, limitations, scan


def build_scan_report(
    project_path: str | Path,
    *,
    config: SentinelConfig | None = None,
    mode: str = "scan",
    unity_path: str | None = None,
) -> tuple[Report, object]:
    """Run the analysis and build a report (without writing it)."""
    started = time.monotonic()
    cfg = config or load_config()
    root = resolve_project_root(project_path)

    if not looks_like_unity_project(root):
        raise ValueError(
            f"{project_path!r} does not look like a Unity project (Assets/ not found)."
        )

    findings, checks, limitations, scan = run_analysis(root, cfg)
    env = detect_environment(unity_path)

    git_state = _git_status(root)
    limitations.append(
        "Git working tree was clean before the run."
        if git_state == ""
        else (
            "Git working tree had uncommitted changes before the run; diffs may include "
            "unrelated edits." if git_state else
            "Project is not a Git repository (or git is unavailable); file hashes were used instead."
        )
    )

    meta = ReportMeta(
        tool=TOOL_NAME,
        version=__version__,
        mode=mode,
        project_root=".",
        unity_version=scan.project.unity_version,
        environment=env,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    report = build_report(
        meta=meta,
        findings=findings,
        checks=checks,
        limitations=limitations,
        recommendations=_recommendations(findings),
        max_evidence_length=int(cfg.get("report.max_evidence_length", 200)),
    )
    return report, scan


def _recommendations(findings: list[Finding]) -> list[str]:
    """Derive a short list of next actions from the findings."""
    recommendations: list[str] = []
    codes = {finding.code for finding in findings}
    if "META_MISSING" in codes or "META_ORPHAN" in codes:
        recommendations.append(
            "Commit missing .meta files: Unity generates new GUIDs on import, which breaks references."
        )
    if "META_DUPLICATE_GUID" in codes:
        recommendations.append(
            "Resolve duplicated GUIDs by restoring one asset from version control — never by editing GUIDs by hand."
        )
    if "SCENE_MISSING_SCRIPT" in codes or "PREFAB_MISSING_SCRIPT" in codes:
        recommendations.append(
            "Restore missing scripts (check the .meta GUID in git history) or remove the empty components in Unity."
        )
    if "ASM_CYCLE" in codes:
        recommendations.append("Break assembly cycles by extracting shared code into a lower-level assembly.")
    if "REF_UNKNOWN_GUID" in codes:
        recommendations.append(
            "Run Sentinel > Scan Project inside the Unity Editor to confirm whether the references are actually Missing."
        )
    if "PERF_FIND_IN_HOT_PATH" in codes:
        recommendations.append("Cache Find* results; profile before optimising further.")
    if not recommendations and findings:
        recommendations.append("Review the listed warnings; none of them block a build by themselves.")
    if not findings:
        recommendations.append(
            "No issues detected by file-based checks. Run the Unity Editor module for authoritative scene/prefab validation."
        )
    return recommendations


def _journal_paths_since(root: Path, created_at: str) -> set[str]:
    """Return paths Sentinel wrote after the baseline timestamp."""
    from .safe_operations import iter_journal

    expected: set[str] = set()
    for entry in iter_journal(root):
        if entry.get("action") == "revert":
            continue
        timestamp = str(entry.get("timestamp", ""))
        if created_at and timestamp and timestamp < created_at:
            continue
        path = str(entry.get("path", ""))
        if path:
            expected.add(path)
    return expected


def write_baseline(root: Path, report: Report, scan, *, config: SentinelConfig, mode: str = "scan") -> Path:
    """Persist a baseline next to the project (inside ``.sentinel/``)."""
    tracked = list(scan.scripts) + list(scan.scenes) + list(scan.prefabs) + list(scan.meta_files)
    baseline = create_baseline(
        root,
        findings=report.findings,
        checks=report.checks,
        status=report.status,
        mode=mode,
        relative_paths=tracked,
    )
    path = root / BASELINE_RELATIVE_PATH
    save_baseline(baseline, path)
    return path


def compare_with_baseline(root: Path, baseline_path: Path, config: SentinelConfig) -> tuple[Report, dict]:
    """Run a scan and compare it against a saved baseline."""
    baseline = load_baseline(baseline_path)
    report, scan = build_scan_report(root, config=config, mode="verify")

    tracked = list(scan.scripts) + list(scan.scenes) + list(scan.prefabs) + list(scan.meta_files)
    current_hashes = hash_project_files(root, tracked)
    new, resolved, unchanged, changes = compare(baseline, report.findings, current_hashes)

    # Files that Sentinel itself modified after the baseline was taken are
    # expected changes: the journal is the authoritative record of them.
    expected = _journal_paths_since(root, baseline.created_at)
    regression = regression_findings(new, resolved, changes, expected_changes=expected)
    if expected:
        report.limitations.append(
            f"{len(expected)} file(s) were changed by UNITY SENTINEL itself after the baseline "
            "and are treated as expected changes (see .sentinel/journal.jsonl)."
        )
    report.extend(regression)
    report.recompute_summary()
    report.status = report.compute_status()

    unexpected = sorted(
        {
            path
            for kind in ("added", "removed", "modified")
            for path in changes[kind]
            if path not in expected
        }
    )
    new_errors = [f for f in new if f.severity in (Severity.ERROR, Severity.CRITICAL)]
    if new_errors:
        findings_result = CheckResult.FAIL
    elif new:
        findings_result = CheckResult.WARN
    else:
        findings_result = CheckResult.PASS
    report.checks.append(
        Check(
            id="regression.new_findings",
            title="New findings since baseline",
            result=findings_result,
            details=f"{len(new)} new, {len(resolved)} resolved, {len(unchanged)} unchanged",
        )
    )
    report.checks.append(
        Check(
            id="regression.files",
            title="File changes since baseline",
            result=CheckResult.PASS if not unexpected else CheckResult.WARN,
            details=(
                f"{len(changes['added'])} added, {len(changes['removed'])} removed, "
                f"{len(changes['modified'])} modified; {len(unexpected)} unexpected"
            ),
        )
    )
    details = {
        "new": [f.to_dict() for f in new],
        "resolved": [f.to_dict() for f in resolved],
        "unchanged_count": len(unchanged),
        "file_changes": changes,
        "baseline_created_at": baseline.created_at,
    }
    report.recompute_summary()
    report.status = report.compute_status()
    return report, details
