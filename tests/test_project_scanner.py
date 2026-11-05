"""Tests for the read-only project scanner."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from core.config import load_config
from core.project_scanner import scan_project
from tests import FIXTURES


def tree_hashes(root: Path) -> dict[str, str]:
    """Hash every file under ``root`` to prove a scan does not write."""
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


class ScanValidProjectTests(unittest.TestCase):
    def test_detects_project_shape(self) -> None:
        summary = scan_project(FIXTURES / "valid_project")
        self.assertTrue(summary.project.is_unity_project)
        self.assertEqual(summary.project.unity_version, "2022.3.20f1")
        self.assertEqual(summary.project.render_pipeline, "URP")
        self.assertIn("Assets/Scripts/PlayerController.cs", summary.scripts)
        self.assertIn("Assets/Scenes/Main.unity", summary.scenes)
        self.assertIn("Assets/Prefabs/Enemy.prefab", summary.prefabs)
        self.assertIn("Assets/Scripts/FixtureGame.asmdef", summary.assembly_definitions)
        self.assertTrue(summary.meta_files)
        self.assertTrue(summary.project.packages_lock_present)

    def test_generated_directories_are_excluded(self) -> None:
        summary = scan_project(FIXTURES / "valid_project")
        self.assertIn("Library", summary.skipped_directories)
        all_paths = (
            summary.scripts
            + summary.scenes
            + summary.prefabs
            + summary.meta_files
            + summary.oversized_files
            + summary.unreadable_files
        )
        for path in all_paths:
            self.assertFalse(path.startswith(("Library/", "Temp/", "Logs/")), path)

    def test_scan_does_not_modify_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            before = tree_hashes(project)
            scan_project(project)
            after = tree_hashes(project)
            self.assertEqual(before, after)

    def test_extension_counts_and_totals(self) -> None:
        summary = scan_project(FIXTURES / "valid_project")
        self.assertGreater(summary.total_files, 0)
        self.assertGreater(summary.total_bytes, 0)
        self.assertIn(".cs", summary.extension_counts)


class ScanEdgeCaseTests(unittest.TestCase):
    def test_empty_directory_is_reported_as_not_unity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = scan_project(tmp)
            self.assertFalse(summary.project.is_unity_project)
            self.assertEqual(summary.total_files, 0)

    def test_unicode_and_spaces_in_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Мой Проект С Пробелами"
            shutil.copytree(FIXTURES / "valid_project", project)
            summary = scan_project(project)
            self.assertTrue(summary.project.is_unity_project)
            self.assertIn("Assets/Scripts/PlayerController.cs", summary.scripts)

    def test_oversized_file_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            big = project / "Assets" / "Big.bin"
            big.write_bytes(b"0" * (1024 * 1024))
            config = load_config()
            config.data["scan"]["max_file_size_bytes"] = 1024
            summary = scan_project(project, config=config)
            self.assertIn("Assets/Big.bin", summary.oversized_files)

    def test_file_limit_sets_truncated_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            config = load_config()
            config.data["scan"]["max_files"] = 2
            summary = scan_project(project, config=config)
            self.assertTrue(summary.truncated)

    @unittest.skipIf(sys.platform.startswith("win") or os.geteuid() == 0, "needs non-root POSIX permissions")
    def test_unreadable_file_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "valid_project", project)
            blocked = project / "Assets" / "Blocked.cs"
            blocked.write_text("class Blocked {}", encoding="utf-8")
            os.chmod(blocked, 0o000)
            try:
                summary = scan_project(project)
            finally:
                os.chmod(blocked, 0o644)
            self.assertGreater(summary.total_files, 0)

    def test_missing_project_settings_is_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            (project / "Assets").mkdir(parents=True)
            (project / "Assets" / "A.cs").write_text("class A {}", encoding="utf-8")
            summary = scan_project(project)
            self.assertTrue(summary.project.is_unity_project)
            self.assertIsNone(summary.project.unity_version)


if __name__ == "__main__":
    unittest.main()
