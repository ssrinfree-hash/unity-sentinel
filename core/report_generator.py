"""Report generation: stable JSON plus a human-readable Markdown summary.

Security rules enforced here:

* findings never embed the contents of credential-like files;
* token-shaped strings (``ghp_...``, ``AKIA...``, private keys, passwords) are
  redacted from every text field before it reaches a report;
* absolute user paths are replaced with root-relative paths.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Report, Severity, Status
from .version import REPORT_SCHEMA_VERSION, TOOL_NAME, __version__

LOGGER = logging.getLogger("unity_sentinel.report")

REDACTED = "[REDACTED]"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b"),
    re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
)

_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+|/(?:home|Users|root)/[^\s\"']+)")


def redact_text(value: str | None, max_length: int = 200) -> str | None:
    """Remove credentials from a string and truncate it."""
    if value is None:
        return None
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            result = pattern.sub(lambda m: f"{m.group(1)}: {REDACTED}", result)
        else:
            result = pattern.sub(REDACTED, result)
    if len(result) > max_length:
        result = result[: max_length - 3] + "..."
    return result


def sanitise_paths(value: str | None) -> str | None:
    """Replace absolute user paths with a placeholder."""
    if value is None:
        return None
    return _ABSOLUTE_PATH_RE.sub("<absolute-path>", value)


def build_report(
    *,
    meta,
    findings: list,
    checks: list,
    changed_files: list[str] | None = None,
    skipped_checks: list[str] | None = None,
    limitations: list[str] | None = None,
    recommendations: list[str] | None = None,
    max_evidence_length: int = 200,
) -> Report:
    """Assemble a :class:`Report`, redacting every free-text field."""
    report = Report(meta=meta)
    report.meta.schema_version = REPORT_SCHEMA_VERSION
    report.meta.tool = TOOL_NAME
    report.meta.version = __version__
    if not report.meta.generated_at:
        report.meta.generated_at = datetime.now(timezone.utc).isoformat()

    for finding in findings:
        finding.message = sanitise_paths(redact_text(finding.message, 400)) or ""
        finding.evidence = sanitise_paths(redact_text(finding.evidence, max_evidence_length))
        finding.recommendation = sanitise_paths(redact_text(finding.recommendation, 400))
        finding.path = sanitise_paths(redact_text(finding.path, 400))
        report.add(finding)

    report.checks = list(checks)
    report.changed_files = [sanitise_paths(p) or p for p in (changed_files or [])]
    report.skipped_checks = [sanitise_paths(s) or s for s in (skipped_checks or [])]
    report.limitations = [sanitise_paths(l) or l for l in (limitations or [])]
    report.recommendations = [sanitise_paths(r) or r for r in (recommendations or [])]
    report.recompute_summary()
    report.status = report.compute_status()
    return report


def to_json(report: Report) -> str:
    """Serialise a report with a stable key order."""
    data = report.to_dict()
    data["findings"] = [f.to_dict() for f in report.sorted_findings()]
    data["status"] = report.status.value
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)


def _status_badge(status: Status) -> str:
    return {
        Status.PASS: "**PASS**",
        Status.PASS_WITH_WARNINGS: "**PASS WITH WARNINGS**",
        Status.FAIL: "**FAIL**",
        Status.NOT_VERIFIED: "**NOT VERIFIED**",
    }[status]


def _group(findings: list, severity: Severity) -> list:
    return [f for f in findings if f.severity == severity]


def to_markdown(report: Report) -> str:
    """Render a report as Markdown."""
    lines: list[str] = []
    meta = report.meta
    lines.append("# UNITY SENTINEL — Report")
    lines.append("")
    lines.append(f"- **Status:** {_status_badge(report.status)}")
    lines.append(f"- **Mode:** `{meta.mode}`")
    lines.append(f"- **Tool:** `{meta.tool}` v{meta.version} (schema {meta.schema_version})")
    lines.append(f"- **Generated:** {meta.generated_at}")
    if meta.project_root:
        lines.append(f"- **Project root:** `{meta.project_root}`")
    if meta.unity_version:
        lines.append(f"- **Unity version:** `{meta.unity_version}`")
    lines.append(f"- **Duration:** {meta.duration_ms} ms")
    lines.append("")

    env = meta.environment
    lines.append("## Environment")
    lines.append("")
    lines.append(f"| Component | Status |")
    lines.append(f"| --- | --- |")
    lines.append(f"| Python | {env.python_version or 'unknown'} |")
    lines.append(f"| Git | {env.git_version if env.git_available else 'not available'} |")
    lines.append(f"| dotnet | {env.dotnet_version if env.dotnet_available else 'not available'} |")
    if env.unity_editor_available:
        lines.append(f"| Unity Editor | {env.unity_editor_version or env.unity_editor_path} |")
    else:
        lines.append("| Unity Editor | **not available** — editor-side checks were skipped |")
    lines.append("")

    summary = report.summary
    lines.append("## Summary")
    lines.append("")
    lines.append("| Critical | Error | Warning | Info | Total |")
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(
        f"| {summary.get('critical', 0)} | {summary.get('error', 0)} | "
        f"{summary.get('warning', 0)} | {summary.get('info', 0)} | {summary.get('total', 0)} |"
    )
    lines.append("")

    if report.changed_files:
        lines.append("## Changed files")
        lines.append("")
        for path in report.changed_files:
            lines.append(f"- `{path}`")
        lines.append("")

    for severity, title in (
        (Severity.CRITICAL, "Critical"),
        (Severity.ERROR, "Errors"),
        (Severity.WARNING, "Warnings"),
        (Severity.INFO, "Info / heuristics"),
    ):
        group = _group(report.sorted_findings(), severity)
        if not group:
            continue
        lines.append(f"## {title} ({len(group)})")
        lines.append("")
        for finding in group:
            location = finding.path or "(project)"
            if finding.line:
                location += f":{finding.line}"
            lines.append(f"- `{finding.code}` — {finding.message}")
            lines.append(f"  - location: `{location}`")
            lines.append(f"  - confidence: {finding.confidence.value}")
            if finding.evidence:
                lines.append(f"  - evidence: `{finding.evidence}`")
            if finding.recommendation:
                lines.append(f"  - recommendation: {finding.recommendation}")
        lines.append("")

    if report.checks:
        lines.append("## Checks")
        lines.append("")
        lines.append("| Check | Result | Details |")
        lines.append("| --- | --- | --- |")
        for check in report.checks:
            details = (check.details or "").replace("|", "\\|")
            lines.append(f"| `{check.id}` | {check.result.value} | {details} |")
        lines.append("")

    if report.skipped_checks:
        lines.append("## Skipped checks")
        lines.append("")
        for item in report.skipped_checks:
            lines.append(f"- {item}")
        lines.append("")

    if report.limitations:
        lines.append("## Limitations")
        lines.append("")
        for item in report.limitations:
            lines.append(f"- {item}")
        lines.append("")

    if report.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for item in report.recommendations:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_UNITY SENTINEL performs measurable checks; an empty finding list is not "
        "proof that the project is free of defects. Editor-side validation requires "
        "a Unity installation._"
    )
    lines.append("")
    return "\n".join(lines)


def save_reports(report: Report, output_dir: Path, *, json_name: str = "report.json", md_name: str = "report.md") -> tuple[Path, Path]:
    """Write JSON and Markdown reports into ``output_dir``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / json_name
    md_path = output_dir / md_name
    json_path.write_text(to_json(report), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, md_path


def load_report_json(path: Path) -> dict:
    """Load ``report.json`` (used by ``sentinel.py report``)."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Report is not valid JSON: {exc}") from exc
