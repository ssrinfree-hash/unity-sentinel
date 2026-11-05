"""Unit tests for the line-oriented Unity YAML helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.unity_yaml import read_unity_yaml
from tests import FIXTURES

SCENE = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100
GameObject:
  m_ObjectHideFlags: 0
  m_Name: Root
--- !u!4 &101
Transform:
  m_GameObject: {fileID: 100}
--- !u!114 &102
MonoBehaviour:
  m_Script: {fileID: 0}
"""

DUPLICATE = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100
GameObject:
  m_Name: A
--- !u!1 &100
GameObject:
  m_Name: B
"""


class UnityYamlTests(unittest.TestCase):
    def _parse(self, content: str, *, binary: bool = False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "Asset.unity"
        if binary:
            path.write_bytes(b"\x00\x01binary")
        else:
            path.write_text(content, encoding="utf-8")
        return read_unity_yaml(path)

    def test_documents_and_class_counts(self) -> None:
        info = self._parse(SCENE)
        self.assertTrue(info.is_text)
        self.assertTrue(info.has_unity_header)
        self.assertEqual(len(info.documents), 3)
        self.assertEqual(info.class_counts["1"], 1)
        self.assertEqual(info.documents[0].file_id, "100")
        self.assertEqual(info.documents[1].line, 7)

    def test_missing_script_detection(self) -> None:
        info = self._parse(SCENE)
        self.assertEqual(len(info.missing_script_lines), 1)

    def test_duplicate_file_ids(self) -> None:
        info = self._parse(DUPLICATE)
        self.assertEqual(info.duplicate_file_ids, ["100"])

    def test_binary_file_is_flagged(self) -> None:
        info = self._parse("", binary=True)
        self.assertFalse(info.is_text)

    def test_no_documents(self) -> None:
        info = self._parse("just some text\n")
        self.assertIsNotNone(info.parse_error)

    def test_unity_asset_missing_script(self) -> None:
        info = read_unity_yaml(FIXTURES / "valid_project" / "Assets" / "Scenes" / "Main.unity")
        self.assertTrue(info.is_text)
        self.assertEqual(info.missing_script_lines, [])


if __name__ == "__main__":
    unittest.main()
