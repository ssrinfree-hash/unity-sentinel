"""Unit tests for project detection heuristics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.models import Confidence
from core.project_detector import (
    detect_project,
    detect_render_pipeline,
    read_manifest,
    read_unity_version,
)
from tests import FIXTURES


class DetectProjectTests(unittest.TestCase):
    def test_valid_project_facts(self) -> None:
        info = detect_project(FIXTURES / "valid_project")
        self.assertTrue(info.is_unity_project)
        self.assertEqual(info.unity_version, "2022.3.20f1")
        self.assertEqual(info.render_pipeline, "URP")
        self.assertEqual(info.render_pipeline_confidence, Confidence.HIGH)
        self.assertIn("com.unity.render-pipelines.universal", info.packages)
        self.assertTrue(info.manifest_present)
        self.assertTrue(info.packages_lock_present)
        self.assertIsNone(info.manifest_parse_error)

    def test_malformed_manifest_is_reported_without_crashing(self) -> None:
        info = detect_project(FIXTURES / "malformed_project_settings")
        self.assertIsNotNone(info.manifest_parse_error)
        self.assertEqual(info.packages, [])
        self.assertIsNone(info.unity_version)
        self.assertIn("ProjectVersion.txt", " ".join(info.notes))
        self.assertEqual(info.render_pipeline, "unknown")

    def test_missing_version_file_never_guesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Project"
            (root / "Assets").mkdir(parents=True)
            info = detect_project(root)
            self.assertIsNone(info.unity_version)
            self.assertIsNone(info.unity_version_source)


class ReadHelpersTests(unittest.TestCase):
    def test_read_unity_version_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            version, source = read_unity_version(Path(tmp))
            self.assertIsNone(version)
            self.assertIsNone(source)

    def test_read_unity_version_malformed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ProjectSettings").mkdir()
            (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
                "no version here\n", encoding="utf-8"
            )
            version, source = read_unity_version(root)
            self.assertIsNone(version)
            self.assertEqual(source, "ProjectSettings/ProjectVersion.txt")

    def test_read_manifest_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Packages").mkdir()
            (root / "Packages" / "manifest.json").write_text("{", encoding="utf-8")
            manifest, error = read_manifest(root)
            self.assertIsNone(manifest)
            self.assertIn("not valid JSON", error or "")

    def test_read_manifest_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest, error = read_manifest(Path(tmp))
            self.assertIsNone(manifest)
            self.assertIsNone(error)


class RenderPipelineTests(unittest.TestCase):
    def test_hdrp_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, confidence, evidence = detect_render_pipeline(
                Path(tmp), {"dependencies": {"com.unity.render-pipelines.high-definition": "17.0.0"}}
            )
            self.assertEqual(pipeline, "HDRP")
            self.assertEqual(confidence, Confidence.HIGH)
            self.assertIn("high-definition", evidence or "")

    def test_unknown_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, confidence, evidence = detect_render_pipeline(Path(tmp), None)
            self.assertEqual(pipeline, "unknown")
            self.assertEqual(confidence, Confidence.LOW)
            self.assertIsNone(evidence)

    def test_builtin_from_manifest_and_graphics_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ProjectSettings").mkdir()
            (root / "ProjectSettings" / "GraphicsSettings.asset").write_text(
                "m_SRPDefaultSettings: {}\n", encoding="utf-8"
            )
            manifest = json.loads('{"dependencies": {"com.unity.ugui": "1.0.0"}}')
            pipeline, confidence, _ = detect_render_pipeline(root, manifest)
            self.assertEqual(pipeline, "Built-in")
            self.assertEqual(confidence, Confidence.LOW)


if __name__ == "__main__":
    unittest.main()
