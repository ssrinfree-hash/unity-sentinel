"""Tests for the GUID reference analyzer."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.meta_validator import build_meta_index
from core.reference_analyzer import DEFAULT_REFERENCE_EXTENSIONS, scan_references
from tests import FIXTURES


class ReferenceAnalyzerTests(unittest.TestCase):
    def test_unknown_guid_is_reported_as_warning(self) -> None:
        root = FIXTURES / "missing_reference"
        index = build_meta_index(root)
        ref_index, findings = scan_references(root, index.known_guids)
        self.assertGreaterEqual(ref_index.scanned_files, 1)
        codes = {f.code for f in findings}
        self.assertIn("REF_UNKNOWN_GUID", codes)
        unknown = [f for f in findings if f.code == "REF_UNKNOWN_GUID"]
        self.assertTrue(all(f.severity.value == "warning" for f in unknown))
        self.assertTrue(all(f.confidence.value == "medium" for f in unknown))

    def test_known_guids_are_not_reported(self) -> None:
        root = FIXTURES / "valid_project"
        index = build_meta_index(root)
        _, findings = scan_references(root, index.known_guids)
        self.assertEqual(findings, [])

    def test_limitations_are_declared(self) -> None:
        root = FIXTURES / "valid_project"
        index = build_meta_index(root)
        ref_index, _ = scan_references(root, index.known_guids)
        self.assertTrue(ref_index.limitations)

    def test_zero_fileid_reference_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Project"
            (root / "Assets").mkdir(parents=True)
            (root / "Assets.meta").write_text("fileFormatVersion: 2\nguid: " + "1" * 32, encoding="utf-8")
            scene = root / "Assets" / "Empty.unity"
            scene.write_text(
                "%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n"
                "--- !u!1 &1\nGameObject:\n  m_Component: []\n"
                "--- !u!114 &2\nMonoBehaviour:\n  m_Script: {fileID: 0}\n",
                encoding="utf-8",
            )
            ref_index, findings = scan_references(root, set())
            self.assertEqual(findings, [])
            self.assertEqual(ref_index.unknown_guids, {})

    def test_extension_filter_respected(self) -> None:
        root = FIXTURES / "missing_reference"
        index = build_meta_index(root)
        ref_index, _ = scan_references(root, index.known_guids, extensions=(".prefab",))
        self.assertNotIn(".unity", {Path(p).suffix for p in ref_index.unknown_guids.values() for p in p})
        self.assertIn(".unity", DEFAULT_REFERENCE_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
