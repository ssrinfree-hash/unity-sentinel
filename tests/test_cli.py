"""CLI tests: exit codes, JSON output, help for every command."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import sentinel
from tests import FIXTURES, REPO_ROOT


def run_cli(*argv: str) -> tuple[int, str, str]:
    """Run the CLI in-process and capture stdout/stderr."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = sentinel.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class HelpTests(unittest.TestCase):
    def test_main_help(self) -> None:
        code, out, _ = run_cli("--help")
        self.assertEqual(code, 0)
        for command in ("scan", "plan", "verify", "report", "meta-check", "references", "apply", "doctor", "benchmark"):
            self.assertIn(command, out)

    def test_subcommand_help(self) -> None:
        for command in (
            "scan",
            "plan",
            "apply",
            "verify",
            "report",
            "meta-check",
            "references",
            "revert",
            "doctor",
            "benchmark",
            "version",
        ):
            code, out, _ = run_cli(command, "--help")
            self.assertEqual(code, 0, command)
            self.assertIn("usage", out.lower(), command)


class ScanCliTests(unittest.TestCase):
    def test_scan_valid_project_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli("scan", "--project", str(FIXTURES / "valid_project"), "--out", tmp)
            self.assertEqual(code, sentinel.EXIT_OK)
            self.assertIn("Status: PASS", out)
            self.assertTrue((Path(tmp) / "report.json").is_file())
            self.assertTrue((Path(tmp) / "report.md").is_file())

    def test_scan_broken_meta_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli("scan", "--project", str(FIXTURES / "broken_meta"), "--out", tmp, "--json")
            self.assertEqual(code, sentinel.EXIT_FAIL)
            payload = json.loads(out)
            self.assertEqual(payload["status"], "FAIL")
            self.assertIn("META_INVALID", {f["code"] for f in payload["findings"]})

    def test_scan_missing_project_exits_fatal(self) -> None:
        code, out, _ = run_cli("scan", "--project", "/definitely/not/here")
        self.assertEqual(code, sentinel.EXIT_FATAL)
        self.assertIn("error:", out)

    def test_scan_non_unity_directory_exits_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = run_cli("scan", "--project", tmp)
            self.assertEqual(code, sentinel.EXIT_FATAL)
            self.assertIn("does not look like a Unity project", out)

    def test_scan_unicode_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Юнити Проект"
            shutil.copytree(FIXTURES / "valid_project", project)
            code, out, _ = run_cli("scan", "--project", str(project), "--out", str(Path(tmp) / "out"))
            self.assertEqual(code, sentinel.EXIT_OK)
            self.assertIn("PASS", out)

    def test_scan_writes_nothing_into_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))
            run_cli("scan", "--project", str(project), "--out", str(Path(tmp) / "out"))
            after = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))
            self.assertEqual(before, after)


class OtherCommandTests(unittest.TestCase):
    def test_meta_check_json(self) -> None:
        code, out, _ = run_cli("meta-check", "--project", str(FIXTURES / "duplicate_guid"), "--json")
        self.assertEqual(code, sentinel.EXIT_FAIL)
        payload = json.loads(out)
        self.assertIn("known_guids", payload)
        self.assertTrue(payload["findings"])

    def test_references_command(self) -> None:
        code, out, _ = run_cli("references", "--project", str(FIXTURES / "missing_reference"), "--json")
        self.assertEqual(code, sentinel.EXIT_OK)
        payload = json.loads(out)
        self.assertGreaterEqual(payload["scanned_files"], 1)
        self.assertTrue(payload["unknown_guids"])
        self.assertTrue(payload["limitations"])

    def test_doctor(self) -> None:
        code, out, _ = run_cli("doctor", "--json")
        self.assertEqual(code, sentinel.EXIT_OK)
        payload = json.loads(out)
        self.assertIn("python_version", payload)
        self.assertIn("unity_editor_available", payload)

    def test_version(self) -> None:
        code, out, _ = run_cli("version")
        self.assertEqual(code, sentinel.EXIT_OK)
        self.assertIn("unity-sentinel", out)

    def test_report_command_renders_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_cli("scan", "--project", str(FIXTURES / "broken_meta"), "--out", tmp)
            code, out, _ = run_cli("report", "--input", str(Path(tmp) / "report.json"), "--out", tmp)
            self.assertEqual(code, sentinel.EXIT_OK)
            self.assertIn("# UNITY SENTINEL — Report", out)
            self.assertTrue((Path(tmp) / "report.md").is_file())

    def test_report_missing_file(self) -> None:
        code, out, _ = run_cli("report", "--input", "/nope/report.json")
        self.assertEqual(code, sentinel.EXIT_FATAL)

    def test_verify_without_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            code, out, _ = run_cli("verify", "--project", str(project))
            self.assertEqual(code, sentinel.EXIT_FATAL)
            self.assertIn("Baseline not found", out)


class PlanApplyCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "Project"
        shutil.copytree(FIXTURES / "valid_project", self.project)
        self.target = self.project / "Assets" / "Scripts" / "EnemyBehaviour.cs"
        self.original = self.target.read_text(encoding="utf-8")
        self.changes = Path(self._tmp.name) / "changes.json"
        self.changes.write_text(
            json.dumps(
                {
                    "changes": [
                        {
                            "path": "Assets/Scripts/EnemyBehaviour.cs",
                            "search": "public Transform target;",
                            "replacement": "public Transform target;\n        // sentinel test",
                            "reason": "cli test",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_plan_then_dry_run_then_apply(self) -> None:
        out_dir = Path(self._tmp.name) / "sentinel"
        code, out, _ = run_cli(
            "plan", "--project", str(self.project), "--changes", str(self.changes), "--out", str(out_dir / "plan.json")
        )
        self.assertEqual(code, sentinel.EXIT_OK)
        plan = json.loads((out_dir / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["changes"][0]["path"], "Assets/Scripts/EnemyBehaviour.cs")
        self.assertIsNotNone(plan["changes"][0]["sha256_before"])

        code, out, _ = run_cli(
            "apply", "--project", str(self.project), "--plan", str(out_dir / "plan.json"),
            "--changes", str(self.changes), "--dry-run", "--show-diff",
        )
        self.assertEqual(code, sentinel.EXIT_OK)
        self.assertIn("DRY-RUN", out)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

        code, out, _ = run_cli(
            "apply", "--project", str(self.project), "--plan", str(out_dir / "plan.json"),
            "--changes", str(self.changes), "--yes",
        )
        self.assertEqual(code, sentinel.EXIT_OK)
        self.assertIn("sentinel test", self.target.read_text(encoding="utf-8"))
        self.assertTrue((self.project / ".sentinel" / "journal.jsonl").is_file())

        code, out, _ = run_cli("revert", "--project", str(self.project))
        self.assertEqual(code, sentinel.EXIT_OK)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_plan_without_changes_produces_advisory_plan(self) -> None:
        code, out, _ = run_cli("plan", "--project", str(FIXTURES / "broken_meta"), "--out", str(Path(self._tmp.name) / "p.json"))
        self.assertEqual(code, sentinel.EXIT_OK)
        plan = json.loads((Path(self._tmp.name) / "p.json").read_text(encoding="utf-8"))
        self.assertTrue(plan["manual_steps"])

    def test_apply_refuses_tampered_file(self) -> None:
        out_dir = Path(self._tmp.name) / "sentinel"
        run_cli("plan", "--project", str(self.project), "--changes", str(self.changes), "--out", str(out_dir / "plan.json"))
        self.target.write_text(self.original + "\n// user edit\n", encoding="utf-8")
        code, out, _ = run_cli(
            "apply", "--project", str(self.project), "--plan", str(out_dir / "plan.json"),
            "--changes", str(self.changes), "--yes",
        )
        self.assertEqual(code, sentinel.EXIT_FAIL)
        self.assertIn("changed since the plan", out)


class SubprocessTests(unittest.TestCase):
    def test_entrypoint_runs_as_a_script(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sentinel.py"), "version"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("unity-sentinel", result.stdout)


if __name__ == "__main__":
    unittest.main()
