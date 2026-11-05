"""Unit tests for the dependency analyzer and the performance inspector."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core.dependency_analyzer import find_assembly_cycles, load_assembly_definitions
from core.performance_inspector import inspect_script
from tests import FIXTURES


class AssemblyGraphTests(unittest.TestCase):
    def test_valid_fixture_has_no_cycles(self) -> None:
        definitions, findings = load_assembly_definitions(FIXTURES / "valid_project")
        self.assertIn("FixtureGame", definitions)
        self.assertEqual(find_assembly_cycles(definitions), [])
        self.assertEqual([f for f in findings if f.severity.value == "error"], [])

    def test_cycle_is_detected(self) -> None:
        definitions, _ = load_assembly_definitions(FIXTURES / "malformed_project_settings")
        cycles = find_assembly_cycles(definitions)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].code, "ASM_CYCLE")
        self.assertEqual(cycles[0].severity.value, "error")
        self.assertIn("A -> B -> A", cycles[0].message)

    def test_invalid_asmdef_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Assets").mkdir()
            (root / "Assets" / "Broken.asmdef").write_text("{ nope", encoding="utf-8")
            definitions, findings = load_assembly_definitions(root)
            self.assertEqual(definitions, {})
            self.assertEqual(findings[0].code, "ASMDEF_INVALID")

    def test_project_inside_a_temp_named_folder_is_not_skipped(self) -> None:
        """Regression: Windows temp dirs live under ...\Temp, so the generated-
        directory filter must look at paths relative to the project only."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Temp" / "UnityProject"
            shutil.copytree(FIXTURES / "valid_project", root)
            definitions, _ = load_assembly_definitions(root)
            self.assertIn("FixtureGame", definitions)

    def test_duplicate_assembly_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Assets").mkdir()
            for name in ("One.asmdef", "Two.asmdef"):
                (root / "Assets" / name).write_text(json.dumps({"name": "Same"}), encoding="utf-8")
            _, findings = load_assembly_definitions(root)
            self.assertIn("ASMDEF_DUPLICATE_NAME", {f.code for f in findings})


HOT_SCRIPT = """
using UnityEngine;

public class Hot : MonoBehaviour
{
    private void Update()
    {
        var x = FindObjectOfType<Hot>();
        var body = GetComponent<Rigidbody>();
        Debug.Log("a" + x + body);
    }
}
"""


class PerformanceInspectorTests(unittest.TestCase):
    def _inspect(self, content: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "Hot.cs"
        path.write_text(content, encoding="utf-8")
        return inspect_script(path)

    def test_heuristics_are_info_and_low_confidence(self) -> None:
        findings = self._inspect(HOT_SCRIPT)
        codes = {f.code for f in findings}
        self.assertIn("PERF_FIND_IN_HOT_PATH", codes)
        self.assertIn("PERF_GETCOMPONENT_IN_HOT_PATH", codes)
        self.assertIn("PERF_STRING_ALLOC_IN_HOT_PATH", codes)
        for finding in findings:
            self.assertEqual(finding.severity.value, "info")
            self.assertEqual(finding.confidence.value, "low")
            self.assertIn("heuristic", finding.message)

    def test_clean_update_has_no_findings(self) -> None:
        clean = """
using UnityEngine;
public class Clean : MonoBehaviour
{
    private Rigidbody cached;
    private void Awake() { cached = GetComponent<Rigidbody>(); }
    private void Update() { cached.AddForce(Vector3.up); }
}
"""
        self.assertEqual(self._inspect(clean), [])

    def test_real_fixture_matches_expected_codes(self) -> None:
        path = FIXTURES / "suspicious_scripts" / "Assets" / "Scripts" / "HotPathSample.cs"
        codes = {f.code for f in inspect_script(path, FIXTURES / "suspicious_scripts")}
        self.assertTrue(
            {
                "PERF_FIND_IN_HOT_PATH",
                "PERF_GETCOMPONENT_IN_HOT_PATH",
                "PERF_STRING_ALLOC_IN_HOT_PATH",
                "PERF_LINQ_IN_HOT_PATH",
                "PERF_SYNC_IO",
            }.issubset(codes),
            codes,
        )

    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(inspect_script(Path("/does/not/exist.cs")), [])


if __name__ == "__main__":
    unittest.main()
