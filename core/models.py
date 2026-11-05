"""Structured data models shared by every UNITY SENTINEL component.

The models are plain dataclasses so that the core has zero third-party
dependencies and remains easy to serialise to JSON with a stable schema.
"""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Iterable


class Severity(str, enum.Enum):
    """Severity levels used by findings and report aggregation."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


class Confidence(str, enum.Enum):
    """How certain the tool is about a finding.

    ``HIGH`` means a deterministic, verifiable fact (for example a duplicated
    GUID). ``MEDIUM`` means a strong structural signal. ``LOW`` means a
    heuristic that must not be reported as a proven defect.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Status(str, enum.Enum):
    """Overall status of a Sentinel report."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS WITH WARNINGS"
    FAIL = "FAIL"
    NOT_VERIFIED = "NOT VERIFIED"


class CheckResult(str, enum.Enum):
    """Outcome of a single executed check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIPPED = "skipped"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if is_dataclass(value):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return value


class JsonModel:
    """Mixin providing a deterministic ``to_dict`` implementation."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the model."""
        return _to_jsonable(self)


@dataclass
class Finding(JsonModel):
    """A single diagnostic result.

    ``code`` is a stable identifier (e.g. ``META_DUPLICATE_GUID``) so that
    findings can be diffed between runs and consumed by automation.
    """

    code: str
    message: str
    severity: Severity = Severity.WARNING
    path: str | None = None
    line: int | None = None
    confidence: Confidence = Confidence.HIGH
    evidence: str | None = None
    recommendation: str | None = None
    category: str = "general"

    @property
    def fingerprint(self) -> str:
        """Stable hash of the fields that define the identity of a finding."""
        raw = f"{self.code}\x00{self.path or ''}\x00{self.line or ''}\x00{self.message}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def key(self) -> str:
        """Sort key that produces deterministic report ordering."""
        return f"{99 - self.severity_order:02d}:{self.code}:{self.path or ''}:{self.line or 0}:{self.message}"

    @property
    def severity_order(self) -> int:
        return _SEVERITY_ORDER.get(self.severity, 0)


@dataclass
class Check(JsonModel):
    """A check that was executed (or deliberately skipped) during a run."""

    id: str
    title: str
    result: CheckResult = CheckResult.SKIPPED
    details: str | None = None
    requires: str | None = None  # e.g. "unity-editor"

    @property
    def ok(self) -> bool:
        return self.result in (CheckResult.PASS, CheckResult.WARN, CheckResult.SKIPPED)


@dataclass
class UnityProjectInfo(JsonModel):
    """Information detected about a Unity project."""

    root: str = ""
    is_unity_project: bool = False
    unity_version: str | None = None
    unity_version_source: str | None = None
    render_pipeline: str = "unknown"
    render_pipeline_confidence: Confidence = Confidence.LOW
    render_pipeline_evidence: str | None = None
    packages: list[str] = field(default_factory=list)
    packages_lock_present: bool = False
    manifest_present: bool = False
    manifest_parse_error: str | None = None
    scripting_backend: str | None = None
    platforms: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class FileEntry(JsonModel):
    """A scanned file inside the Unity project."""

    path: str  # POSIX-style path relative to the project root
    size: int
    extension: str


@dataclass
class ScanSummary(JsonModel):
    """Aggregate result of a project scan."""

    root: str = ""
    project: UnityProjectInfo = field(default_factory=UnityProjectInfo)
    total_files: int = 0
    total_bytes: int = 0
    extension_counts: dict[str, int] = field(default_factory=dict)
    scripts: list[str] = field(default_factory=list)
    assembly_definitions: list[str] = field(default_factory=list)
    assembly_references: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)
    prefabs: list[str] = field(default_factory=list)
    scriptable_objects: list[str] = field(default_factory=list)
    meta_files: list[str] = field(default_factory=list)
    skipped_directories: list[str] = field(default_factory=list)
    oversized_files: list[str] = field(default_factory=list)
    unreadable_files: list[str] = field(default_factory=list)
    truncated: bool = False
    duration_ms: int = 0

    def file_hashes(self) -> dict[str, str]:
        """Placeholder kept for API symmetry; hashing lives in RegressionEngine."""
        return {}


@dataclass
class EnvironmentInfo(JsonModel):
    """Availability of external tools relevant for verification."""

    python_version: str = ""
    python_executable: str = ""
    git_available: bool = False
    git_version: str | None = None
    dotnet_available: bool = False
    dotnet_version: str | None = None
    unity_editor_available: bool = False
    unity_editor_path: str | None = None
    unity_editor_version: str | None = None
    os_name: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class ReportMeta(JsonModel):
    """Metadata that identifies a report and makes it reproducible."""

    tool: str = ""
    version: str = ""
    schema_version: str = ""
    mode: str = "scan"
    generated_at: str = ""
    duration_ms: int = 0
    project_root: str | None = None
    unity_version: str | None = None
    environment: EnvironmentInfo = field(default_factory=EnvironmentInfo)


@dataclass
class Report(JsonModel):
    """Full machine-readable report."""

    meta: ReportMeta = field(default_factory=ReportMeta)
    status: Status = Status.NOT_VERIFIED
    summary: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    skipped_checks: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: f.key())

    def recompute_summary(self) -> None:
        counts = {s.value: 0 for s in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        counts["total"] = len(self.findings)
        self.summary = counts

    def compute_status(self) -> Status:
        """Derive the report status from findings and executed checks.

        PASS requires that mandatory checks actually ran and passed. If a
        mandatory check was skipped (for example because Unity is missing) the
        report downgrades to ``NOT VERIFIED`` instead of pretending success.
        """
        if any(f.severity in (Severity.ERROR, Severity.CRITICAL) for f in self.findings):
            return Status.FAIL
        mandatory = [c for c in self.checks if c.requires is None]
        if not mandatory:
            return Status.NOT_VERIFIED
        if any(c.result == CheckResult.FAIL for c in mandatory):
            return Status.FAIL
        if self.skipped_checks:
            return Status.NOT_VERIFIED
        if any(c.result == CheckResult.WARN for c in mandatory) or any(
            f.severity == Severity.WARNING for f in self.findings
        ):
            return Status.PASS_WITH_WARNINGS
        return Status.PASS


@dataclass
class PlannedFileChange(JsonModel):
    """A single file change described by a plan."""

    path: str
    reason: str
    expected_effect: str = ""
    risk: str = "low"
    requires_confirmation: bool = False
    sha256_before: str | None = None
    operation: str = "replace"


@dataclass
class Plan(JsonModel):
    """A plan produced in ``plan`` mode; never modifies the project."""

    schema_version: str = "1.0"
    created_at: str = ""
    project_root: str = ""
    requested_by: str = "cli"
    summary: str = ""
    changes: list[PlannedFileChange] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    requires_confirmation: bool = True


@dataclass
class ApplyResult(JsonModel):
    """Outcome of an apply operation."""

    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    journal_path: str | None = None
    backup_dir: str | None = None
    diff: str | None = None
    dry_run: bool = False


@dataclass
class Baseline(JsonModel):
    """Snapshot of a project used to compare pre/post change state."""

    created_at: str = ""
    mode: str = "scan"
    project_root: str = ""
    status: str = ""
    findings: list[Finding] = field(default_factory=list)
    file_hashes: dict[str, str] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
