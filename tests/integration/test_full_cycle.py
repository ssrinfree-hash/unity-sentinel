"""End-to-end integration test: scan -> plan -> dry-run -> apply -> verify -> report.

Everything runs against a temporary copy of a synthetic fixture project; the
real fixtures and the user's projects are never touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import sentinel
from tests import FIXTURES


def run_cli(*argv: str) -> tuple[int, str]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        code = sentinel.main(list(argv))
    return code, stdout.getvalue()


class FullCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.project = self.base / "UnityProject"
        shutil.copytree(FIXTURES / "valid_project", self.project)
        self.target = self.project / "Assets" / "Scripts" / "PlayerController.cs"
        self.original = self.target.read_text(encoding="utf-8")
        self.changes = self.base / "changes.json"
        self.changes.write_text(
            json.dumps(
                {
                    "summary": "guard speed value",
                    "changes": [
                        {
                            "path": "Assets/Scripts/PlayerController.cs",
                            "search": "private void Update()",
                            "replacement": "private void OnValidate()\n        {\n            if (speed < 0f) speed = 0f;\n        }\n\n        private void Update()",
                            "reason": "clamp negative speed",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_full_cycle(self) -> None:
        out_dir = self.base / "reports"

        # 1. Baseline scan
        code, out = run_cli("scan", "--project", str(self.project), "--out", str(out_dir), "--baseline")
        self.assertEqual(code, 0, out)
        baseline = self.project / ".sentinel" / "baseline.json"
        self.assertTrue(baseline.is_file())
        report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["findings"], [])

        # 2. Plan (must not modify anything)
        plan_path = self.base / "plan.json"
        code, _ = run_cli("plan", "--project", str(self.project), "--changes", str(self.changes), "--out", str(plan_path))
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

        # 3. Dry-run (still no modification)
        code, out = run_cli(
            "apply", "--project", str(self.project), "--plan", str(plan_path),
            "--changes", str(self.changes), "--dry-run", "--show-diff",
        )
        self.assertEqual(code, 0)
        self.assertIn("OnValidate", out)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

        # 4. Apply for real
        code, _ = run_cli(
            "apply", "--project", str(self.project), "--plan", str(plan_path),
            "--changes", str(self.changes), "--yes",
        )
        self.assertEqual(code, 0)
        self.assertIn("OnValidate", self.target.read_text(encoding="utf-8"))

        # 5. Verify against the baseline
        code, out = run_cli("verify", "--project", str(self.project), "--out", str(out_dir))
        self.assertEqual(code, 0, out)
        verify = json.loads((out_dir / "verify.json").read_text(encoding="utf-8"))
        self.assertEqual(verify["status"], "PASS")
        regressions = [f for f in verify["findings"] if f["code"].startswith("REGRESSION_")]
        self.assertTrue(
            all(f["code"] == "REGRESSION_UNEXPECTED_FILE_CHANGE" for f in regressions),
            regressions,
        )

        # 6. Report regeneration from JSON
        code, out = run_cli("report", "--input", str(out_dir / "verify.json"), "--out", str(out_dir))
        self.assertEqual(code, 0)
        self.assertTrue((out_dir / "verify.md").is_file())

        # 7. Revert returns the file to its original bytes
        code, _ = run_cli("revert", "--project", str(self.project))
        self.assertEqual(code, 0)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_scan_is_read_only_and_reports_are_valid(self) -> None:
        before = {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        out_dir = self.base / "reports"
        code, _ = run_cli("scan", "--project", str(self.project), "--out", str(out_dir))
        self.assertEqual(code, 0)
        after = {p: p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

        payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
        for key in ("meta", "status", "summary", "findings", "checks", "limitations", "recommendations"):
            self.assertIn(key, payload)
        markdown = (out_dir / "report.md").read_text(encoding="utf-8")
        self.assertIn("# UNITY SENTINEL — Report", markdown)

    def test_reports_do_not_leak_secrets_or_absolute_paths(self) -> None:
        secret_file = self.project / "Assets" / "credentials.env"
        fake_token = "ghp_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
        secret_file.write_text("GITHUB_TOKEN=" + fake_token + "\n", encoding="utf-8")
        out_dir = self.base / "reports"
        code, _ = run_cli("scan", "--project", str(self.project), "--out", str(out_dir), "--json")
        self.assertEqual(code, 0)
        blob = (out_dir / "report.json").read_text(encoding="utf-8") + (out_dir / "report.md").read_text(encoding="utf-8")
        self.assertNotIn(fake_token, blob)
        self.assertNotIn(str(self.base), blob)

    def test_verify_flags_regressions(self) -> None:
        out_dir = self.base / "reports"
        run_cli("scan", "--project", str(self.project), "--out", str(out_dir), "--baseline")
        (self.project / "Assets" / "Scripts" / "PlayerController.cs.meta").unlink()
        code, out = run_cli("verify", "--project", str(self.project), "--out", str(out_dir))
        self.assertEqual(code, 0)  # warnings only
        verify = json.loads((out_dir / "verify.json").read_text(encoding="utf-8"))
        codes = {f["code"] for f in verify["findings"]}
        self.assertIn("REGRESSION_NEW_WARNING", codes)
        self.assertIn("REGRESSION_UNEXPECTED_FILE_REMOVED", codes)


if __name__ == "__main__":
    unittest.main()
