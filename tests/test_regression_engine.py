"""Tests for the regression engine."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.models import Check, CheckResult, Confidence, Finding, Severity, Status
from core.regression_engine import (
    compare,
    create_baseline,
    hash_project_files,
    load_baseline,
    regression_findings,
    save_baseline,
)
from tests import FIXTURES


class BaselineTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        finding = Finding(
            code="META_MISSING",
            message="Asset has no .meta file",
            severity=Severity.WARNING,
            path="Assets/A.cs",
            confidence=Confidence.HIGH,
        )
        check = Check(id="meta.integrity", title="Meta", result=CheckResult.WARN)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = create_baseline(
                root,
                findings=[finding],
                checks=[check],
                status=Status.PASS_WITH_WARNINGS,
                relative_paths=[],
            )
            path = root / "baseline.json"
            save_baseline(baseline, path)
            loaded = load_baseline(path)
            self.assertEqual(loaded.status, "PASS WITH WARNINGS")
            self.assertEqual(loaded.findings[0].code, "META_MISSING")
            self.assertEqual(loaded.checks[0].id, "meta.integrity")

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{ nope", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baseline(path)

    def test_not_a_baseline_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.json"
            path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baseline(path)


class CompareTests(unittest.TestCase):
    def _baseline(self, findings, hashes) -> object:
        return type(
            "B",
            (),
            {"findings": findings, "file_hashes": hashes, "created_at": "", "status": ""},
        )()

    def test_new_and_resolved_findings(self) -> None:
        old = Finding(code="A", message="old", severity=Severity.WARNING, path="Assets/A.cs")
        gone = Finding(code="B", message="gone", severity=Severity.WARNING, path="Assets/B.cs")
        baseline = self._baseline([old, gone], {})
        new, resolved, unchanged, changes = compare(baseline, [old], {})
        self.assertEqual([f.code for f in resolved], ["B"])
        self.assertEqual([f.code for f in unchanged], ["A"])
        self.assertEqual(new, [])
        self.assertEqual(changes, {"added": [], "removed": [], "modified": []})

    def test_file_change_detection(self) -> None:
        baseline = self._baseline([], {"Assets/A.cs": "1", "Assets/B.cs": "2", "Assets/C.cs": "3"})
        new, resolved, unchanged, changes = compare(
            baseline, [], {"Assets/A.cs": "1", "Assets/B.cs": "x", "Assets/D.cs": "4"}
        )
        self.assertEqual(changes["modified"], ["Assets/B.cs"])
        self.assertEqual(changes["added"], ["Assets/D.cs"])
        self.assertEqual(changes["removed"], ["Assets/C.cs"])

    def test_new_error_becomes_critical_regression(self) -> None:
        finding = Finding(code="X", message="boom", severity=Severity.ERROR, path="Assets/X.cs")
        regressions = regression_findings([finding], [], {})
        self.assertEqual(regressions[0].code, "REGRESSION_NEW_ERROR")
        self.assertEqual(regressions[0].severity, Severity.CRITICAL)

    def test_expected_file_change_is_not_reported(self) -> None:
        regressions = regression_findings([], [], {"added": [], "removed": [], "modified": ["Assets/A.cs"]}, expected_changes=["Assets/A.cs"])
        self.assertEqual(regressions, [])

    def test_unexpected_file_change_is_warning(self) -> None:
        regressions = regression_findings([], [], {"added": [], "removed": [], "modified": ["Assets/A.cs"]})
        self.assertEqual(regressions[0].code, "REGRESSION_UNEXPECTED_FILE_CHANGE")
        self.assertEqual(regressions[0].severity, Severity.WARNING)


class HashTests(unittest.TestCase):
    def test_hashes_are_stable_and_ignore_secrets(self) -> None:
        root = FIXTURES / "valid_project"
        hashes_a = hash_project_files(root)
        hashes_b = hash_project_files(root)
        self.assertEqual(hashes_a, hashes_b)
        self.assertIn("Assets/Scripts/PlayerController.cs", hashes_a)

    def test_secret_files_are_not_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Assets").mkdir()
            secret = root / "Assets" / "credentials.txt"
            secret.write_text("token=abc", encoding="utf-8")
            normal = root / "Assets" / "A.cs"
            normal.write_text("class A {}", encoding="utf-8")
            hashes = hash_project_files(root)
            self.assertIn("Assets/A.cs", hashes)
            self.assertNotIn("Assets/credentials.txt", hashes)


if __name__ == "__main__":
    unittest.main()
