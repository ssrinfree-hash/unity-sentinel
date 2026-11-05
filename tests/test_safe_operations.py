"""Tests for the SAFE CHANGE PROTOCOL (apply/dry-run/backup/journal/revert)."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from core.config import load_config
from core.paths import PathSecurityError
from core.safe_operations import (
    FileOperation,
    apply_operations,
    iter_journal,
    revert_entry,
    sha256_file,
)
from tests import FIXTURES


class SafeOperationsTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "Project"
        shutil.copytree(FIXTURES / "valid_project", self.root)
        self.target = self.root / "Assets" / "Scripts" / "EnemyBehaviour.cs"
        self.original = self.target.read_text(encoding="utf-8")
        self.config = load_config()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_op(self, **kwargs) -> FileOperation:
        defaults = dict(
            path="Assets/Scripts/EnemyBehaviour.cs",
            search="public Transform target;",
            replacement="public Transform target;\n        // patched by test",
            reason="test replacement",
        )
        defaults.update(kwargs)
        return FileOperation(**defaults)


class DryRunTests(SafeOperationsTestBase):
    def test_dry_run_never_writes(self) -> None:
        result = apply_operations(self.root, [self.make_op()], dry_run=True, config=self.config)
        self.assertTrue(result.dry_run)
        self.assertEqual(result.applied, ["Assets/Scripts/EnemyBehaviour.cs"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)
        self.assertFalse((self.root / ".sentinel" / "journal.jsonl").exists())
        self.assertIn("--- a/Assets/Scripts/EnemyBehaviour.cs", result.diff)

    def test_apply_without_confirmation_raises(self) -> None:
        with self.assertRaises(PermissionError):
            apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=False, config=self.config)
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_noop_change_is_skipped(self) -> None:
        result = apply_operations(
            self.root,
            [self.make_op(replacement="public Transform target;")],
            dry_run=True,
            config=self.config,
        )
        self.assertEqual(result.applied, [])
        self.assertTrue(any("no changes required" in s for s in result.skipped))


class PathSafetyTests(SafeOperationsTestBase):
    def test_path_traversal_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            victim = Path(outside) / "victim.txt"
            victim.write_text("original", encoding="utf-8")
            op = FileOperation(path="../victim.txt", replacement="pwned")
            result = apply_operations(self.root, [op], dry_run=False, confirmed=True, config=self.config)
            self.assertEqual(victim.read_text(encoding="utf-8"), "original")
            self.assertTrue(result.failed)

    def test_absolute_path_is_refused(self) -> None:
        outside = Path(tempfile.gettempdir()) / "sentinel-absolute.txt"
        outside.write_text("original", encoding="utf-8")
        op = FileOperation(path=str(outside), replacement="pwned")
        result = apply_operations(self.root, [op], dry_run=False, confirmed=True, config=self.config)
        self.assertEqual(outside.read_text(encoding="utf-8"), "original")
        self.assertTrue(result.failed)

    def test_generated_directory_is_refused(self) -> None:
        op = FileOperation(path="Library/foo.txt", replacement="x")
        result = apply_operations(self.root, [op], dry_run=True, config=self.config)
        self.assertTrue(result.failed)

    def test_protected_path_requires_flag(self) -> None:
        target = self.root / "ProjectSettings" / "ProjectVersion.txt"
        original = target.read_text(encoding="utf-8")
        op = FileOperation(path="ProjectSettings/ProjectVersion.txt", replacement="m_EditorVersion: 6.6.6\n")
        result = apply_operations(self.root, [op], dry_run=False, confirmed=True, config=self.config)
        self.assertTrue(result.failed)
        self.assertEqual(target.read_text(encoding="utf-8"), original)

        op_allowed = FileOperation(
            path="ProjectSettings/ProjectVersion.txt",
            replacement="m_EditorVersion: 2022.3.20f1\n",
            allow_protected=True,
        )
        result_allowed = apply_operations(
            self.root, [op_allowed], dry_run=True, confirmed=False, config=self.config
        )
        self.assertEqual(result_allowed.failed, [])

    @unittest.skipIf(sys.platform.startswith("win"), "symlinks need privileges on Windows")
    def test_symlink_escape_is_refused(self) -> None:
        outside_dir = Path(self._tmp.name) / "outside"
        outside_dir.mkdir()
        victim = outside_dir / "secret.txt"
        victim.write_text("original", encoding="utf-8")
        link = self.root / "Assets" / "link.txt"
        try:
            os.symlink(victim, link)
        except (OSError, NotImplementedError):  # pragma: no cover
            self.skipTest("symlinks are not supported")
        op = FileOperation(path="Assets/link.txt", replacement="pwned")
        result = apply_operations(self.root, [op], dry_run=False, confirmed=True, config=self.config)
        self.assertTrue(result.failed)
        self.assertEqual(victim.read_text(encoding="utf-8"), "original")


class ApplyTests(SafeOperationsTestBase):
    def test_apply_writes_backup_and_journal(self) -> None:
        result = apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config)
        self.assertEqual(result.applied, ["Assets/Scripts/EnemyBehaviour.cs"])
        self.assertIn("patched by test", self.target.read_text(encoding="utf-8"))

        journal = self.root / ".sentinel" / "journal.jsonl"
        self.assertTrue(journal.is_file())
        entry = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["path"], "Assets/Scripts/EnemyBehaviour.cs")
        self.assertEqual(entry["reason"], "test replacement")
        backup = self.root / entry["backup"]
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.read_text(encoding="utf-8"), self.original)

    def test_hash_mismatch_is_refused(self) -> None:
        op = self.make_op(expected_sha256="0" * 64)
        result = apply_operations(self.root, [op], dry_run=False, confirmed=True, config=self.config)
        self.assertTrue(result.failed)
        self.assertIn("changed since the plan", " ".join(result.skipped))
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_matching_hash_is_accepted(self) -> None:
        op = self.make_op(expected_sha256=sha256_file(self.target))
        result = apply_operations(self.root, [op], dry_run=True, config=self.config)
        self.assertEqual(result.failed, [])

    def test_search_must_match_exactly_once(self) -> None:
        result = apply_operations(
            self.root,
            [self.make_op(search="NotPresentAnywhere", replacement="x")],
            dry_run=True,
            config=self.config,
        )
        self.assertTrue(result.failed)
        self.assertIn("found 0", " ".join(result.skipped))

    def test_multiple_matches_are_refused(self) -> None:
        result = apply_operations(
            self.root,
            [self.make_op(search="}", replacement="")],
            dry_run=True,
            config=self.config,
        )
        self.assertTrue(result.failed)

    def test_missing_target_is_refused(self) -> None:
        op = FileOperation(path="Assets/Nope.cs", replacement="x")
        result = apply_operations(self.root, [op], dry_run=True, config=self.config)
        self.assertTrue(result.failed)

    def test_operation_without_content_is_refused(self) -> None:
        op = FileOperation(path="Assets/Scripts/EnemyBehaviour.cs")
        result = apply_operations(self.root, [op], dry_run=True, config=self.config)
        self.assertTrue(result.failed)


class RevertTests(SafeOperationsTestBase):
    def test_revert_restores_original_bytes(self) -> None:
        apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config)
        entries = iter_journal(self.root)
        self.assertEqual(len(entries), 1)
        outcome = revert_entry(self.root, entries[0])
        self.assertEqual(outcome.status, "applied")
        self.assertEqual(self.target.read_text(encoding="utf-8"), self.original)

    def test_revert_refuses_when_file_changed_after_apply(self) -> None:
        apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config)
        entries = iter_journal(self.root)
        self.target.write_text("// manual edit after sentinel\n", encoding="utf-8")
        outcome = revert_entry(self.root, entries[0])
        self.assertEqual(outcome.status, "failed")
        self.assertIn("changed after", outcome.detail)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "// manual edit after sentinel\n")

    def test_revert_refuses_when_backup_missing(self) -> None:
        apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config)
        entries = iter_journal(self.root)
        (self.root / entries[0]["backup"]).unlink()
        outcome = revert_entry(self.root, entries[0])
        self.assertEqual(outcome.status, "failed")

    def test_backup_is_never_overwritten(self) -> None:
        apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config, run_id="run1")
        (self.root / "Assets" / "Scripts" / "EnemyBehaviour.cs").write_text(self.original, encoding="utf-8")
        result = apply_operations(self.root, [self.make_op()], dry_run=False, confirmed=True, config=self.config, run_id="run1")
        self.assertTrue(result.failed)
        self.assertIn("Backup already exists", " ".join(result.skipped))


if __name__ == "__main__":
    unittest.main()
