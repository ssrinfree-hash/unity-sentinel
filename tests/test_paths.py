"""Tests for the path-security layer."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from core.paths import (
    DEFAULT_EXCLUDED_DIRECTORIES,
    PathSecurityError,
    check_no_symlink_escape,
    ensure_within_root,
    is_excluded_relative,
    is_safe_to_write,
    is_secret_like,
    looks_like_unity_project,
    resolve_project_root,
    to_report_path,
)


class ResolveProjectRootTests(unittest.TestCase):
    def test_missing_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                resolve_project_root(Path(tmp) / "nope")

    def test_file_instead_of_directory_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "file.txt"
            file_path.write_text("x", encoding="utf-8")
            with self.assertRaises(NotADirectoryError):
                resolve_project_root(file_path)

    def test_unicode_and_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Проект Unity с пробелами"
            project.mkdir()
            self.assertEqual(resolve_project_root(project), project.resolve())


class LooksLikeUnityProjectTests(unittest.TestCase):
    def test_empty_directory_is_not_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(looks_like_unity_project(Path(tmp)))

    def test_assets_only_is_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Assets").mkdir()
            self.assertTrue(looks_like_unity_project(Path(tmp)))


class ContainmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "Assets").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_relative_target_inside_root(self) -> None:
        safe = ensure_within_root(self.root, "Assets/Player.cs")
        self.assertEqual(safe.relative, "Assets/Player.cs")

    def test_parent_traversal_rejected(self) -> None:
        with self.assertRaises(PathSecurityError):
            ensure_within_root(self.root, "../outside.txt")

    def test_deep_traversal_rejected(self) -> None:
        with self.assertRaises(PathSecurityError):
            ensure_within_root(self.root, "Assets/../../etc/passwd")

    def test_absolute_outside_root_rejected(self) -> None:
        outside = Path(tempfile.gettempdir()) / "sentinel-outside.txt"
        with self.assertRaises(PathSecurityError):
            ensure_within_root(self.root, outside)

    def test_project_root_itself_rejected(self) -> None:
        with self.assertRaises(PathSecurityError):
            ensure_within_root(self.root, ".")

    def test_must_exist(self) -> None:
        with self.assertRaises(FileNotFoundError):
            ensure_within_root(self.root, "Assets/Missing.cs", must_exist=True)

    @unittest.skipIf(sys.platform.startswith("win"), "symlinks need privileges on Windows")
    def test_symlink_escape_rejected(self) -> None:
        outside_dir = Path(self._tmp.name).parent  # /tmp
        link = self.root / "Assets" / "escape"
        try:
            os.symlink(outside_dir, link, target_is_directory=True)
        except (OSError, NotImplementedError):  # pragma: no cover
            self.skipTest("symlinks are not supported in this environment")
        with self.assertRaises(PathSecurityError):
            check_no_symlink_escape(self.root, link / "sentinel-escape.txt")
        with self.assertRaises(PathSecurityError):
            ensure_within_root(self.root, "Assets/escape/passwd")

    def test_generated_directory_write_rejected(self) -> None:
        with self.assertRaises(PathSecurityError):
            is_safe_to_write(self.root, "Library/ScriptAssemblies/Foo.dll")


class ExclusionTests(unittest.TestCase):
    def test_generated_directories_are_excluded(self) -> None:
        for directory in ("Library", "Temp", "Obj", "Logs", "Builds"):
            self.assertTrue(is_excluded_relative(f"{directory}/Some/File.txt"))
            self.assertIn(directory, DEFAULT_EXCLUDED_DIRECTORIES)

    def test_assets_path_is_not_excluded(self) -> None:
        self.assertFalse(is_excluded_relative("Assets/Scripts/Player.cs"))

    def test_prefix_similarity_is_not_excluded(self) -> None:
        self.assertFalse(is_excluded_relative("Assets/LibraryHelper/Script.cs"))


class SecretDetectionTests(unittest.TestCase):
    def test_secret_like_names(self) -> None:
        for name in (".env", "id_rsa", "server.pem", "keystore.keystore", "credentials.json"):
            self.assertTrue(is_secret_like(name), name)

    def test_normal_names(self) -> None:
        for name in ("Player.cs", "manifest.json", "Main.unity"):
            self.assertFalse(is_secret_like(name), name)


class ReportPathTests(unittest.TestCase):
    def test_relative_path_for_inside_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "Assets").mkdir()
            target = root / "Assets" / "A.cs"
            target.write_text("x", encoding="utf-8")
            self.assertEqual(to_report_path(root, target), "Assets/A.cs")

    def test_absolute_path_never_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            outside = Path(tempfile.gettempdir()) / "elsewhere.cs"
            self.assertEqual(to_report_path(root, outside), "elsewhere.cs")


if __name__ == "__main__":
    unittest.main()
