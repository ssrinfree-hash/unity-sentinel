"""Tests for report generation, redaction and status computation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.models import (
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
from core.report_generator import (
    REDACTED,
    build_report,
    redact_text,
    sanitise_paths,
    save_reports,
    to_json,
    to_markdown,
)


# Tokens are assembled at runtime so this repository never contains a real
# credential-shaped string (the CI secret scanner forbids it).
FAKE_GITHUB_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
FAKE_AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"


def make_meta() -> ReportMeta:
    return ReportMeta(
        tool="unity-sentinel",
        version="1.0.0",
        mode="scan",
        generated_at="2026-01-01T00:00:00+00:00",
        environment=EnvironmentInfo(python_version="3.13.0"),
    )


class RedactionTests(unittest.TestCase):
    def test_github_token_is_redacted(self) -> None:
        self.assertNotIn(FAKE_GITHUB_TOKEN, redact_text(f"token={FAKE_GITHUB_TOKEN} leaked") or "")

    def test_aws_key_is_redacted(self) -> None:
        self.assertIn(REDACTED, redact_text(FAKE_AWS_KEY) or "")

    def test_password_assignment_is_redacted(self) -> None:
        result = redact_text('password = "hunter2"') or ""
        self.assertIn(REDACTED, result)
        self.assertNotIn("hunter2", result)

    def test_private_key_block_is_redacted(self) -> None:
        text = "-----BEGIN RSA PRIVATE " + "KEY-----\nMIIE\n-----END RSA PRIVATE " + "KEY-----"
        self.assertNotIn("MIIE", redact_text(text) or "")

    def test_long_text_is_truncated(self) -> None:
        result = redact_text("a" * 500, max_length=100) or ""
        self.assertLessEqual(len(result), 100)
        self.assertTrue(result.endswith("..."))

    def test_absolute_paths_are_sanitised(self) -> None:
        self.assertNotIn("/home/user", sanitise_paths("/home/user/project/Assets/A.cs") or "")
        self.assertNotIn("C:\\Users", sanitise_paths(r"C:\Users\dev\project\Assets\A.cs") or "")


class BuildReportTests(unittest.TestCase):
    def test_report_is_json_serialisable(self) -> None:
        finding = Finding(code="META_MISSING", message="no meta", path="Assets/A.cs")
        report = build_report(
            meta=make_meta(),
            findings=[finding],
            checks=[Check(id="meta.integrity", title="Meta", result=CheckResult.WARN)],
        )
        payload = json.loads(to_json(report))
        self.assertEqual(payload["findings"][0]["code"], "META_MISSING")
        self.assertEqual(payload["meta"]["tool"], "unity-sentinel")
        self.assertIn("schema_version", payload["meta"])

    def test_evidence_is_redacted_in_report(self) -> None:
        finding = Finding(
            code="X",
            message="found token",
            severity=Severity.WARNING,
            evidence=FAKE_GITHUB_TOKEN,
        )
        report = build_report(meta=make_meta(), findings=[finding], checks=[])
        self.assertNotIn(FAKE_GITHUB_TOKEN, report.findings[0].evidence or "")
        self.assertNotIn(FAKE_GITHUB_TOKEN, to_json(report))

    def test_findings_are_sorted_by_severity(self) -> None:
        findings = [
            Finding(code="I", message="info", severity=Severity.INFO),
            Finding(code="E", message="error", severity=Severity.ERROR),
            Finding(code="W", message="warn", severity=Severity.WARNING),
        ]
        report = build_report(meta=make_meta(), findings=findings, checks=[])
        codes = [f.code for f in report.sorted_findings()]
        self.assertEqual(codes, ["E", "W", "I"])


class StatusTests(unittest.TestCase):
    def _report(self, findings, checks) -> Report:
        return build_report(meta=make_meta(), findings=findings, checks=checks)

    def test_pass(self) -> None:
        report = self._report([], [Check(id="a", title="A", result=CheckResult.PASS)])
        self.assertEqual(report.status, Status.PASS)

    def test_pass_with_warnings(self) -> None:
        report = self._report(
            [Finding(code="W", message="w", severity=Severity.WARNING)],
            [Check(id="a", title="A", result=CheckResult.PASS)],
        )
        self.assertEqual(report.status, Status.PASS_WITH_WARNINGS)

    def test_fail_on_error(self) -> None:
        report = self._report(
            [Finding(code="E", message="e", severity=Severity.ERROR)],
            [Check(id="a", title="A", result=CheckResult.PASS)],
        )
        self.assertEqual(report.status, Status.FAIL)

    def test_fail_on_failed_mandatory_check(self) -> None:
        report = self._report([], [Check(id="a", title="A", result=CheckResult.FAIL)])
        self.assertEqual(report.status, Status.FAIL)

    def test_not_verified_without_mandatory_checks(self) -> None:
        report = self._report([], [])
        self.assertEqual(report.status, Status.NOT_VERIFIED)

    def test_not_verified_when_checks_skipped(self) -> None:
        report = build_report(
            meta=make_meta(),
            findings=[],
            checks=[Check(id="a", title="A", result=CheckResult.PASS)],
            skipped_checks=["unity.validation: Unity Editor unavailable"],
        )
        self.assertEqual(report.status, Status.NOT_VERIFIED)


class MarkdownTests(unittest.TestCase):
    def test_markdown_contains_required_sections(self) -> None:
        finding = Finding(
            code="META_MISSING",
            message="no meta",
            path="Assets/A.cs",
            recommendation="Commit the .meta file.",
        )
        report = build_report(
            meta=make_meta(),
            findings=[finding],
            checks=[
                Check(id="meta.integrity", title="Meta", result=CheckResult.WARN),
                Check(
                    id="unity.tests",
                    title="Unity tests",
                    result=CheckResult.SKIPPED,
                    requires="unity-editor",
                ),
            ],
            limitations=["Unity Editor unavailable"],
            recommendations=["Review warnings"],
        )
        markdown = to_markdown(report)
        for section in ("# UNITY SENTINEL — Report", "## Environment", "## Summary", "## Warnings", "## Checks", "## Limitations", "## Recommendations"):
            self.assertIn(section, markdown)
        self.assertIn("not available", markdown)
        self.assertIn("META_MISSING", markdown)

    def test_save_reports_writes_both_files(self) -> None:
        report = build_report(meta=make_meta(), findings=[], checks=[])
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = save_reports(report, Path(tmp))
            self.assertTrue(json_path.is_file())
            self.assertTrue(md_path.is_file())
            json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("# UNITY SENTINEL", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
