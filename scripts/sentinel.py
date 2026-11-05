#!/usr/bin/env python3
"""UNITY SENTINEL command line interface.

Usage examples::

    python scripts/sentinel.py scan --project /path/to/unity-project
    python scripts/sentinel.py plan --project . --changes changes.json
    python scripts/sentinel.py apply --project . --plan .sentinel/plan.json --show-diff
    python scripts/sentinel.py apply --project . --plan .sentinel/plan.json --yes
    python scripts/sentinel.py verify --project .
    python scripts/sentinel.py report --input .sentinel/report.json

Exit codes
----------
0  PASS or PASS WITH WARNINGS
1  FAIL (errors/critical findings or failed mandatory checks)
2  NOT VERIFIED (mandatory checks could not be executed, e.g. no Unity Editor)
3  fatal usage/environment error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import load_config  # noqa: E402
from core.models import (  # noqa: E402
    CheckResult,
    Confidence,
    Finding,
    Plan,
    PlannedFileChange,
    Severity,
    Status,
)
from core.paths import PathSecurityError, resolve_project_root  # noqa: E402
from core.pipeline import (  # noqa: E402
    BASELINE_RELATIVE_PATH,
    build_scan_report,
    compare_with_baseline,
    detect_environment,
    write_baseline,
)
from core.report_generator import (  # noqa: E402
    load_report_json,
    save_reports,
    to_markdown,
)
from core.safe_operations import (  # noqa: E402
    FileOperation,
    apply_operations,
    iter_journal,
    revert_entry,
    sha256_file,
)
from core.version import REPORT_SCHEMA_VERSION, TOOL_NAME, TOOL_TAGLINE, __version__  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOT_VERIFIED = 2
EXIT_FATAL = 3

LOG = logging.getLogger("unity_sentinel.cli")

DEFAULT_OUT_DIR = ".sentinel"


class CliError(Exception):
    """Raised for user-facing fatal errors (exit code 3)."""


def configure_logging(verbose: bool) -> None:
    """Configure stdlib logging; the CLI itself prints via ``emit``."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def emit(message: str = "") -> None:
    """Print a line to stdout (UTF-8 safe on Windows consoles)."""
    try:
        print(message)
    except UnicodeEncodeError:  # pragma: no cover - legacy Windows console
        print(message.encode("ascii", errors="replace").decode("ascii"))


def status_to_exit_code(status: Status) -> int:
    """Map a report status to the documented exit code."""
    if status in (Status.PASS, Status.PASS_WITH_WARNINGS):
        return EXIT_OK
    if status == Status.FAIL:
        return EXIT_FAIL
    return EXIT_NOT_VERIFIED


def _load_config(args: argparse.Namespace):
    return load_config(getattr(args, "config", None))


def _out_dir(project_root: Path | None, out: str | None) -> Path:
    if out:
        return Path(out).expanduser().resolve()
    if project_root is None:
        return Path.cwd() / DEFAULT_OUT_DIR
    return project_root / DEFAULT_OUT_DIR


def _print_report_summary(report) -> None:
    emit(f"UNITY SENTINEL v{report.meta.version} — mode: {report.meta.mode}")
    emit(f"Status: {report.status.value}")
    summary = report.summary
    emit(
        f"Findings: {summary.get('total', 0)} "
        f"(critical {summary.get('critical', 0)}, error {summary.get('error', 0)}, "
        f"warning {summary.get('warning', 0)}, info {summary.get('info', 0)})"
    )
    if report.meta.unity_version:
        emit(f"Unity: {report.meta.unity_version}")
    else:
        emit("Unity: unknown (ProjectSettings/ProjectVersion.txt missing)")
    env = report.meta.environment
    emit(
        "Environment: "
        f"python {env.python_version}, git={'yes' if env.git_available else 'no'}, "
        f"dotnet={'yes' if env.dotnet_available else 'no'}, "
        f"unity={'yes' if env.unity_editor_available else 'no'}"
    )
    for finding in report.sorted_findings()[:20]:
        location = finding.path or "(project)"
        if finding.line:
            location += f":{finding.line}"
        emit(f"  [{finding.severity.value.upper()}] {finding.code} {location} — {finding.message}")
    if len(report.findings) > 20:
        emit(f"  ... {len(report.findings) - 20} more finding(s) in the report file")
    skipped = [c for c in report.checks if c.result == CheckResult.SKIPPED]
    if skipped:
        emit(f"Skipped checks: {', '.join(c.id for c in skipped)}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> int:
    """Inspect the project without modifying anything."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    try:
        report, _scan = build_scan_report(root, config=cfg, mode="scan", unity_path=args.unity)
    except ValueError as exc:
        raise CliError(str(exc)) from exc

    out_dir = _out_dir(root, args.out)
    json_path, md_path = save_reports(report, out_dir)

    if args.baseline:
        baseline_path = write_baseline(root, report, _scan, config=cfg, mode="scan")
        emit(f"Baseline saved: {baseline_path.relative_to(root).as_posix()}")

    if args.json:
        emit(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_report_summary(report)
        emit(f"Report: {json_path}")
        emit(f"        {md_path}")

    return status_to_exit_code(report.status)


def cmd_meta_check(args: argparse.Namespace) -> int:
    """Validate .meta files only."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    from core.meta_validator import validate_meta

    index, findings = validate_meta(root, config=cfg)
    payload = {
        "meta_files": sum(len(v) for v in index.guids.values()),
        "known_guids": len(index.guids),
        "missing": index.missing,
        "orphan": index.orphan,
        "invalid": index.invalid,
        "findings": [f.to_dict() for f in findings],
    }
    if args.json:
        emit(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        emit(f"Meta files indexed: {len(index.path_to_guid)} assets with GUIDs")
        emit(f"Missing .meta: {len(index.missing)}")
        emit(f"Orphan .meta: {len(index.orphan)}")
        emit(f"Invalid .meta: {len(index.invalid)}")
        for finding in findings:
            location = finding.path or "(project)"
            emit(f"  [{finding.severity.value.upper()}] {finding.code} {location} — {finding.message}")
    has_errors = any(f.severity in (Severity.ERROR, Severity.CRITICAL) for f in findings)
    return EXIT_FAIL if has_errors else EXIT_OK


def cmd_references(args: argparse.Namespace) -> int:
    """Scan text assets for GUID references unknown to the .meta database."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    from core.meta_validator import build_meta_index
    from core.reference_analyzer import scan_references

    index = build_meta_index(root)
    ref_index, findings = scan_references(
        root,
        index.known_guids,
        extensions=tuple(cfg.get("references.scan_extensions", ())),
        max_file_size=int(cfg.get("references.max_file_size_bytes", 16 * 1024 * 1024)),
    )
    payload = {
        "scanned_files": ref_index.scanned_files,
        "skipped_files": ref_index.skipped_files,
        "total_references": ref_index.total_references,
        "unknown_guids": {guid: files for guid, files in sorted(ref_index.unknown_guids.items())},
        "limitations": ref_index.limitations,
        "findings": [f.to_dict() for f in findings],
    }
    if args.json:
        emit(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        emit(f"Scanned assets: {ref_index.scanned_files} (skipped {ref_index.skipped_files})")
        emit(f"References found: {ref_index.total_references}")
        emit(f"Unknown GUIDs: {len(ref_index.unknown_guids)}")
        for limitation in ref_index.limitations:
            emit(f"  limitation: {limitation}")
    has_errors = any(f.severity in (Severity.ERROR, Severity.CRITICAL) for f in findings)
    return EXIT_FAIL if has_errors else EXIT_OK


def _load_changes_file(path: Path) -> list[FileOperation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"Cannot read changes file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"Changes file is not valid JSON: {exc}") from exc

    items = data.get("changes") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise CliError("Changes file must be a JSON array or an object with a 'changes' array")

    operations: list[FileOperation] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict) or "path" not in item:
            raise CliError(f"Change #{idx} must be an object with a 'path' field")
        operations.append(
            FileOperation(
                path=str(item["path"]),
                search=item.get("search"),
                replacement=item.get("replacement"),
                expected_sha256=item.get("expected_sha256"),
                reason=str(item.get("reason", "")),
                allow_protected=bool(item.get("allow_protected", False)),
            )
        )
    return operations


def cmd_plan(args: argparse.Namespace) -> int:
    """Produce a plan; never modifies the project."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    plan = Plan(
        created_at=datetime.now(timezone.utc).isoformat(),
        project_root=".",
        requested_by="cli",
    )

    if args.changes:
        operations = _load_changes_file(Path(args.changes).expanduser())
        # Validate everything exactly like apply would, in dry-run mode.
        validation = apply_operations(root, operations, dry_run=True, confirmed=False, config=cfg)
        failed = set(validation.failed)
        for op in operations:
            try:
                target = (root / op.path).resolve()
                rel = target.relative_to(root.resolve()).as_posix()
            except ValueError:
                failed.add(op.path)
                rel = op.path
            sha = None
            if (root / op.path).is_file():
                sha = sha256_file((root / op.path).resolve())
            risky = rel.split("/", 1)[0] in set(cfg.get("safety.protected_paths", []))
            plan.changes.append(
                PlannedFileChange(
                    path=rel,
                    reason=op.reason or "declared change",
                    expected_effect="exact text replacement" if op.search else "file replacement",
                    risk="high" if risky else "low",
                    requires_confirmation=True,
                    sha256_before=sha,
                    operation="replace",
                )
            )
        plan.summary = (
            f"{len(plan.changes)} change(s) planned; {len(validation.skipped)} skipped, "
            f"{len(failed)} invalid."
        )
        plan.risks = sorted({s for s in validation.skipped})
        plan.manual_steps = [
            "Review the plan and the dry-run diff.",
            "Run apply with --show-diff, then with --yes to write changes.",
            "Run verify against the baseline to detect regressions.",
        ]
    else:
        report, _scan = build_scan_report(root, config=cfg, mode="plan", unity_path=args.unity)
        actionable = [
            f
            for f in report.findings
            if f.severity in (Severity.CRITICAL, Severity.ERROR, Severity.WARNING)
        ]
        plan.summary = (
            "Advisory plan generated from scan findings: "
            f"{len(actionable)} item(s) require attention before changing code."
        )
        for finding in actionable:
            plan.manual_steps.append(
                f"[{finding.code}] {finding.path or '(project)'}"
                + (f":{finding.line}" if finding.line else "")
                + f" — {finding.recommendation or finding.message}"
            )
        plan.requires_confirmation = False

    out = Path(args.out).expanduser() if args.out else root / DEFAULT_OUT_DIR / "plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        emit(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))
    else:
        emit(f"Plan written: {out}")
        emit(plan.summary)
        for change in plan.changes:
            emit(f"  - {change.path} (risk: {change.risk}) — {change.reason}")
        for step in plan.manual_steps:
            emit(f"  * {step}")
    return EXIT_OK


def cmd_apply(args: argparse.Namespace) -> int:
    """Apply a plan through the SAFE CHANGE PROTOCOL."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    plan_path = Path(args.plan).expanduser().resolve()
    if not plan_path.is_file():
        raise CliError(f"Plan not found: {plan_path}")

    try:
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"Plan is not valid JSON: {exc}") from exc

    changes_ops: dict[str, FileOperation] = {}
    if args.changes:
        for op in _load_changes_file(Path(args.changes).expanduser()):
            changes_ops[op.path.replace(os.sep, "/")] = op

    operations: list[FileOperation] = []
    for item in plan_data.get("changes", []):
        rel = str(item.get("path", "")).replace(os.sep, "/")
        source = changes_ops.get(rel)
        search = item.get("search", source.search if source else None)
        replacement = item.get("replacement", source.replacement if source else None)
        operations.append(
            FileOperation(
                path=rel,
                search=search,
                replacement=replacement,
                expected_sha256=item.get("sha256_before"),
                reason=str(item.get("reason", source.reason if source else "")),
                allow_protected=bool(item.get("allow_protected", False)),
            )
        )

    if not operations and changes_ops:
        operations = list(changes_ops.values())

    if not operations:
        raise CliError(
            "The plan contains no applicable operations. If the plan was generated without "
            "embedded replacements, pass the same --changes file used to create it."
        )

    dry_run = bool(args.dry_run or args.show_diff) and not args.yes
    result = apply_operations(
        root,
        operations,
        dry_run=dry_run,
        confirmed=bool(args.yes),
        config=cfg,
    )

    if result.diff:
        emit("--- diff ---")
        emit(result.diff)

    if args.json:
        emit(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        prefix = "DRY-RUN (no files written)" if result.dry_run else "APPLY"
        emit(f"{prefix}: {len(result.applied)} applied, {len(result.skipped)} skipped, {len(result.failed)} failed")
        for item in result.skipped:
            emit(f"  skipped: {item}")
        if result.backup_dir:
            emit(f"Backups: {result.backup_dir}")
        if result.journal_path:
            emit(f"Journal: {result.journal_path}")
        if result.dry_run:
            emit("Re-run with --yes to write these changes.")

    if result.failed:
        return EXIT_FAIL
    return EXIT_OK


def cmd_revert(args: argparse.Namespace) -> int:
    """Revert changes made by Sentinel (only if files still match)."""
    _load_config(args)
    root = resolve_project_root(args.project)
    entries = iter_journal(root)
    if not entries:
        emit("Journal is empty; nothing to revert.")
        return EXIT_OK

    run_id = args.run_id or entries[-1].get("run_id")
    targets = [e.get("run_id") for e in entries if e.get("run_id") == run_id]
    candidates = [
        e for e in entries if e.get("run_id") == run_id and e.get("action") != "revert"
    ]
    if not candidates:
        emit(f"No applied operations found for run {run_id}.")
        return EXIT_OK

    failed = 0
    for entry in candidates:
        if args.dry_run:
            emit(f"would revert: {entry.get('path')}")
            continue
        outcome = revert_entry(root, entry)
        emit(f"{outcome.status}: {outcome.path} — {outcome.detail}")
        if outcome.status == "failed":
            failed += 1
    return EXIT_FAIL if failed else EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-run checks and compare against a baseline."""
    cfg = _load_config(args)
    root = resolve_project_root(args.project)
    baseline_path = Path(args.baseline).expanduser() if args.baseline else root / BASELINE_RELATIVE_PATH
    if not baseline_path.is_file():
        raise CliError(
            f"Baseline not found: {baseline_path}. Run `scan --baseline` first to create one."
        )

    report, details = compare_with_baseline(root, baseline_path, cfg)
    out_dir = _out_dir(root, args.out)
    json_path, md_path = save_reports(report, out_dir, json_name="verify.json", md_name="verify.md")

    if args.json:
        emit(json.dumps({"report": report.to_dict(), "regression": details}, indent=2, ensure_ascii=False))
    else:
        _print_report_summary(report)
        emit(
            f"Regression: {len(details['new'])} new, {len(details['resolved'])} resolved, "
            f"{details['unchanged_count']} unchanged"
        )
        changes = details["file_changes"]
        emit(
            f"Files: {len(changes['added'])} added, {len(changes['removed'])} removed, "
            f"{len(changes['modified'])} modified"
        )
        emit(f"Report: {json_path}")
        emit(f"        {md_path}")

    if args.update_baseline:
        from core.pipeline import BASELINE_RELATIVE_PATH as _BP

        report2, scan2 = build_scan_report(root, config=cfg, mode="scan", unity_path=args.unity)
        write_baseline(root, report2, scan2, config=cfg, mode="scan")
        emit(f"Baseline updated: {_BP.as_posix()}")

    return status_to_exit_code(report.status)


def cmd_report(args: argparse.Namespace) -> int:
    """Re-render an existing report (Markdown from JSON)."""
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise CliError(f"Report not found: {input_path}")
    try:
        data = load_report_json(input_path)
    except ValueError as exc:
        raise CliError(str(exc)) from exc

    if args.format == "json":
        emit(json.dumps(data, indent=2, ensure_ascii=False))
        return EXIT_OK

    from core.models import Report, ReportMeta, Check, CheckResult, EnvironmentInfo

    meta_data = data.get("meta", {})
    env_data = meta_data.get("environment", {})
    meta = ReportMeta(
        tool=meta_data.get("tool", TOOL_NAME),
        version=meta_data.get("version", __version__),
        schema_version=meta_data.get("schema_version", REPORT_SCHEMA_VERSION),
        mode=meta_data.get("mode", "scan"),
        generated_at=meta_data.get("generated_at", ""),
        duration_ms=int(meta_data.get("duration_ms", 0)),
        project_root=meta_data.get("project_root"),
        unity_version=meta_data.get("unity_version"),
        environment=EnvironmentInfo(
            python_version=env_data.get("python_version", ""),
            python_executable=env_data.get("python_executable", ""),
            git_available=bool(env_data.get("git_available", False)),
            git_version=env_data.get("git_version"),
            dotnet_available=bool(env_data.get("dotnet_available", False)),
            dotnet_version=env_data.get("dotnet_version"),
            unity_editor_available=bool(env_data.get("unity_editor_available", False)),
            unity_editor_path=env_data.get("unity_editor_path"),
            unity_editor_version=env_data.get("unity_editor_version"),
            os_name=env_data.get("os_name", ""),
            notes=list(env_data.get("notes", [])),
        ),
    )
    report = Report(
        meta=meta,
        status=Status(data.get("status", Status.NOT_VERIFIED.value)),
        summary=dict(data.get("summary", {})),
        findings=[
            Finding(
                code=f.get("code", "UNKNOWN"),
                message=f.get("message", ""),
                severity=Severity(f.get("severity", "warning")),
                path=f.get("path"),
                line=f.get("line"),
                confidence=Confidence(f.get("confidence", "medium")),
                evidence=f.get("evidence"),
                recommendation=f.get("recommendation"),
                category=f.get("category", "general"),
            )
            for f in data.get("findings", [])
        ],
        checks=[
            Check(
                id=c.get("id", "unknown"),
                title=c.get("title", ""),
                result=CheckResult(c.get("result", "skipped")),
                details=c.get("details"),
                requires=c.get("requires"),
            )
            for c in data.get("checks", [])
        ],
        changed_files=list(data.get("changed_files", [])),
        skipped_checks=list(data.get("skipped_checks", [])),
        limitations=list(data.get("limitations", [])),
        recommendations=list(data.get("recommendations", [])),
    )
    markdown = to_markdown(report)
    out_dir = _out_dir(None, args.out or str(input_path.parent))
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / (input_path.stem + ".md")
    md_path.write_text(markdown, encoding="utf-8")
    emit(markdown)
    emit(f"\nMarkdown written: {md_path}")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    """Show environment availability (no project required)."""
    env = detect_environment(args.unity)
    payload = env.to_dict()
    if args.json:
        emit(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK
    emit(f"UNITY SENTINEL v{__version__} environment check")
    emit(f"  OS:            {env.os_name}")
    emit(f"  Python:        {env.python_version} ({env.python_executable})")
    emit(f"  Git:           {env.git_version or 'not available'}")
    emit(f"  dotnet:        {env.dotnet_version or 'not available'}")
    emit(f"  Unity Editor:  {env.unity_editor_version or env.unity_editor_path or 'not detected'}")
    for note in env.notes:
        emit(f"  note: {note}")
    emit("")
    emit("File-based checks work without Unity. Editor-side checks need UNITY_EDITOR_PATH.")
    return EXIT_OK


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run the synthetic benchmark and print precision/recall metrics."""
    bench_dir = Path(args.fixtures).expanduser().resolve() if args.fixtures else REPO_ROOT / "benchmark"
    if not bench_dir.is_dir():
        raise CliError(f"Benchmark directory not found: {bench_dir}")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from benchmark.run_benchmark import run_benchmark
    except ImportError as exc:  # pragma: no cover
        raise CliError(f"Cannot import benchmark harness: {exc}") from exc

    result = run_benchmark(bench_dir, out_dir=Path(args.out).expanduser() if args.out else None)
    if args.json:
        emit(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        metrics = result["metrics"]
        emit("UNITY SENTINEL — synthetic benchmark (DEMO DATA, generated fixtures)")
        emit(f"  expected findings: {metrics['expected']}")
        emit(f"  detected:          {metrics['detected']}")
        emit(f"  true positives:    {metrics['true_positives']}")
        emit(f"  false positives:   {metrics['false_positives']}")
        emit(f"  false negatives:   {metrics['false_negatives']}")
        emit(f"  precision:         {metrics['precision']:.3f}")
        emit(f"  recall:            {metrics['recall']:.3f}")
        emit(f"  F1:                {metrics['f1']:.3f}")
        emit(f"  runtime:           {metrics['duration_ms']} ms")
        if result.get("output_path"):
            emit(f"  output:            {result['output_path']}")
    return EXIT_OK


def cmd_version(_: argparse.Namespace) -> int:
    """Print tool and schema versions."""
    emit(f"{TOOL_NAME} v{__version__} — {TOOL_TAGLINE}")
    emit(f"report schema: {REPORT_SCHEMA_VERSION}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Create the full argument parser."""
    parser = argparse.ArgumentParser(
        prog="sentinel",
        description=f"UNITY SENTINEL v{__version__} — {TOOL_TAGLINE}",
        epilog="Exit codes: 0 pass, 1 fail, 2 not verified, 3 fatal error.",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", required=True, help="path to the Unity project root")
        p.add_argument("--config", help="path to a JSON configuration file")
        p.add_argument("--unity", help="path to the Unity Editor executable (optional)")
        p.add_argument("--json", action="store_true", help="machine-readable JSON on stdout")
        p.add_argument("--out", help=f"output directory (default: <project>/{DEFAULT_OUT_DIR})")

    p_scan = sub.add_parser("scan", help="read-only project analysis")
    add_common(p_scan)
    p_scan.add_argument("--baseline", action="store_true", help="save a baseline after scanning")
    p_scan.set_defaults(func=cmd_scan)

    p_meta = sub.add_parser("meta-check", help="validate .meta files and GUIDs")
    add_common(p_meta)
    p_meta.set_defaults(func=cmd_meta_check)

    p_refs = sub.add_parser("references", help="scan assets for unknown GUID references")
    add_common(p_refs)
    p_refs.set_defaults(func=cmd_references)

    p_plan = sub.add_parser("plan", help="produce a plan (never modifies the project)")
    add_common(p_plan)
    p_plan.add_argument("--changes", help="JSON file describing intended changes")
    p_plan.set_defaults(func=cmd_plan)

    p_apply = sub.add_parser("apply", help="apply a plan via the SAFE CHANGE PROTOCOL")
    add_common(p_apply)
    p_apply.add_argument("--plan", required=True, help="plan JSON produced by `plan`")
    p_apply.add_argument("--changes", help="changes JSON (needed if the plan has no replacements)")
    p_apply.add_argument("--dry-run", action="store_true", help="show the diff without writing")
    p_apply.add_argument("--show-diff", action="store_true", help="print the unified diff")
    p_apply.add_argument("--yes", action="store_true", help="explicitly confirm writes")
    p_apply.set_defaults(func=cmd_apply)

    p_revert = sub.add_parser("revert", help="revert Sentinel-applied changes from the journal")
    p_revert.add_argument("--project", required=True, help="path to the Unity project root")
    p_revert.add_argument("--config", help="path to a JSON configuration file")
    p_revert.add_argument("--run-id", help="journal run id (default: the latest run)")
    p_revert.add_argument("--dry-run", action="store_true", help="only list what would be reverted")
    p_revert.set_defaults(func=cmd_revert)

    p_verify = sub.add_parser("verify", help="re-run checks and compare with the baseline")
    add_common(p_verify)
    p_verify.add_argument("--baseline", help=f"baseline path (default: {BASELINE_RELATIVE_PATH.as_posix()})")
    p_verify.add_argument("--update-baseline", action="store_true", help="refresh the baseline afterwards")
    p_verify.set_defaults(func=cmd_verify)

    p_report = sub.add_parser("report", help="re-render a report.json as Markdown")
    p_report.add_argument("--input", required=True, help="path to report.json")
    p_report.add_argument("--format", choices=["md", "json"], default="md")
    p_report.add_argument("--out", help="output directory for the Markdown file")
    p_report.set_defaults(func=cmd_report)

    p_doctor = sub.add_parser("doctor", help="check the local environment")
    p_doctor.add_argument("--unity", help="path to the Unity Editor executable")
    p_doctor.add_argument("--json", action="store_true", help="machine-readable output")
    p_doctor.set_defaults(func=cmd_doctor)

    p_bench = sub.add_parser("benchmark", help="run the synthetic benchmark")
    p_bench.add_argument("--fixtures", help="benchmark directory (default: ./benchmark)")
    p_bench.add_argument("--out", help="directory for benchmark results")
    p_bench.add_argument("--json", action="store_true", help="machine-readable output")
    p_bench.set_defaults(func=cmd_benchmark)

    p_version = sub.add_parser("version", help="print version information")
    p_version.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse handles --help and usage errors
        return EXIT_OK if exc.code == 0 else EXIT_FATAL
    configure_logging(getattr(args, "verbose", False))

    try:
        return int(args.func(args))
    except CliError as exc:
        emit(f"error: {exc}")
        return EXIT_FATAL
    except PathSecurityError as exc:
        emit(f"error: {exc}")
        return EXIT_FATAL
    except (FileNotFoundError, NotADirectoryError) as exc:
        emit(f"error: {exc}")
        return EXIT_FATAL
    except KeyboardInterrupt:  # pragma: no cover
        emit("interrupted")
        return EXIT_FATAL


if __name__ == "__main__":
    sys.exit(main())
