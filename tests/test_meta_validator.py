"""Tests for the .meta validator."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from core.meta_validator import build_meta_index, read_guid, validate_meta
from tests import FIXTURES


class MetaValidatorTests(unittest.TestCase):
    def test_valid_project_has_no_meta_findings(self) -> None:
        _, findings = validate_meta(FIXTURES / "valid_project")
        codes = [f.code for f in findings]
        self.assertEqual(codes, [], f"unexpected findings: {codes}")

    def test_missing_meta_detected(self) -> None:
        _, findings = validate_meta(FIXTURES / "broken_meta")
        self.assertIn("META_MISSING", {f.code for f in findings})
        missing = [f for f in findings if f.code == "META_MISSING"]
        self.assertTrue(any(f.path.endswith("OrphanAsset.cs") for f in missing))

    def test_orphan_meta_detected(self) -> None:
        _, findings = validate_meta(FIXTURES / "broken_meta")
        orphans = [f for f in findings if f.code == "META_ORPHAN"]
        self.assertTrue(any(f.path.endswith("Ghost.cs.meta") for f in orphans))

    def test_invalid_meta_detected(self) -> None:
        _, findings = validate_meta(FIXTURES / "broken_meta")
        invalid = [f for f in findings if f.code == "META_INVALID"]
        self.assertTrue(invalid)
        self.assertEqual(invalid[0].severity.value, "error")

    def test_duplicate_guid_detected(self) -> None:
        index, findings = validate_meta(FIXTURES / "duplicate_guid")
        duplicates = [f for f in findings if f.code == "META_DUPLICATE_GUID"]
        self.assertEqual(len(duplicates), 1)
        self.assertIn("55555555555555555555555555555555", duplicates[0].message)
        self.assertEqual(len(index.guids["55555555555555555555555555555555"]), 2)

    def test_guid_format_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Project"
            (root / "Assets").mkdir(parents=True)
            asset = root / "Assets" / "A.cs"
            asset.write_text("class A {}", encoding="utf-8")
            (root / "Assets" / "A.cs.meta").write_text(
                "fileFormatVersion: 2\nguid: NOT-A-GUID\n", encoding="utf-8"
            )
            index, findings = validate_meta(root)
            self.assertIn("Assets/A.cs.meta", index.invalid)
            self.assertIn("META_INVALID", {f.code for f in findings})

    def test_read_guid(self) -> None:
        guid = read_guid(FIXTURES / "valid_project" / "Assets" / "Scripts" / "PlayerController.cs.meta")
        self.assertEqual(guid, "55555555555555555555555555555555")

    def test_read_guid_on_garbage_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "X.meta"
            path.write_text("nothing to see here", encoding="utf-8")
            self.assertIsNone(read_guid(path))

    def test_folder_meta_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Project"
            (root / "Assets" / "Scripts").mkdir(parents=True)
            (root / "Assets.meta").write_text("fileFormatVersion: 2\nguid: " + "1" * 32, encoding="utf-8")
            index = build_meta_index(root)
            self.assertIn("Assets/Scripts", index.missing)

    def test_missing_assets_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index, findings = validate_meta(Path(tmp))
            self.assertEqual(findings, [])
            self.assertEqual(index.path_to_guid, {})

    def test_validator_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "Project"
            shutil.copytree(FIXTURES / "broken_meta", project)
            before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
            validate_meta(project)
            after = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
