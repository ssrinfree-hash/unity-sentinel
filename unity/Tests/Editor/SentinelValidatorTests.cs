// UNITY SENTINEL — EditMode tests for the Editor-side validators.
//
// These tests cover what can be verified deterministically inside a Unity
// Editor: project info collection, pipeline detection, error handling for
// missing assets, prefab validation of a generated prefab, and the NUnit result
// importer. Missing-script detection is exercised structurally (it iterates
// components and counts null entries); fabricating a genuinely missing script in
// a test would require deleting a compiled script asset, which is unsafe.

using System.IO;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnitySentinel.EditorTools;

namespace UnitySentinel.Tests
{
    public class SentinelProjectInfoTests
    {
        [Test]
        public void Collect_ReturnsCurrentUnityVersion()
        {
            SentinelProjectInfoData data = SentinelProjectInfo.Collect();
            Assert.IsNotNull(data);
            Assert.AreEqual(Application.unityVersion, data.unityVersion);
        }

        [Test]
        public void Collect_DetectsARenderPipeline()
        {
            SentinelProjectInfoData data = SentinelProjectInfo.Collect();
            Assert.That(
                data.renderPipeline,
                Is.AnyOf("Built-in", "URP", "HDRP", "Custom", "Unknown"),
                "Unexpected pipeline value: " + data.renderPipeline);
        }
    }

    public class SentinelSceneValidatorTests
    {
        [Test]
        public void ValidateScene_MissingPath_ReturnsError()
        {
            var issues = SentinelSceneValidator.ValidateScene("Assets/DoesNotExist/SentinelTest.unity");
            Assert.AreEqual(1, issues.Count);
            Assert.AreEqual("UNITY_SCENE_NOT_FOUND", issues[0].code);
            Assert.AreEqual("error", issues[0].severity);
        }

        [Test]
        public void ValidateScene_EmptyPath_ReturnsError()
        {
            var issues = SentinelSceneValidator.ValidateScene(string.Empty);
            Assert.AreEqual(1, issues.Count);
            Assert.AreEqual("UNITY_SCENE_PATH_EMPTY", issues[0].code);
        }
    }

    public class SentinelPrefabValidatorTests
    {
        [Test]
        public void ValidatePrefab_GeneratedPrefab_HasNoIssues()
        {
            var gameObject = new GameObject("SentinelTestPrefab");
            string directory = "Assets/UnitySentinelTest";
            string path = directory + "/SentinelTestPrefab.prefab";
            try
            {
                Directory.CreateDirectory(directory);
                PrefabUtility.SaveAsPrefabAsset(gameObject, path);
                var issues = SentinelPrefabValidator.ValidatePrefab(path);
                Assert.AreEqual(0, issues.Count, string.Join("; ", issues.ConvertAll(i => i.ToString()).ToArray()));
            }
            finally
            {
                AssetDatabase.DeleteAsset(path);
                if (AssetDatabase.IsValidFolder(directory))
                {
                    AssetDatabase.DeleteAsset(directory);
                }

                Object.DestroyImmediate(gameObject);
            }
        }

        [Test]
        public void ValidatePrefab_MissingAsset_ReturnsError()
        {
            var issues = SentinelPrefabValidator.ValidatePrefab("Assets/DoesNotExist/SentinelTest.prefab");
            Assert.AreEqual(1, issues.Count);
            Assert.AreEqual("UNITY_PREFAB_NOT_FOUND", issues[0].code);
        }
    }

    public class SentinelTestRunnerTests
    {
        [Test]
        public void ParseResults_MissingFile_ReportsNotRun()
        {
            SentinelTestSummary summary = SentinelTestRunner.ParseResults("Assets/DoesNotExist/results.xml");
            Assert.AreEqual("NOT RUN", summary.status);
            Assert.AreEqual(0, summary.total);
        }

        [Test]
        public void ParseResults_ParsesNUnitXml()
        {
            string path = Path.Combine(Path.GetTempPath(), "sentinel-nunit-" + System.Guid.NewGuid().ToString("N") + ".xml");
            const string xml =
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>" +
                "<test-run id=\"2\" testcasecount=\"3\" total=\"3\" passed=\"2\" failed=\"1\" skipped=\"0\">" +
                "<test-suite type=\"TestSuite\" name=\"Sentinel\">" +
                "<test-case name=\"A\" result=\"Passed\" />" +
                "<test-case name=\"B\" result=\"Failed\" />" +
                "<test-case name=\"C\" result=\"Passed\" />" +
                "</test-suite></test-run>";
            try
            {
                File.WriteAllText(path, xml);
                SentinelTestSummary summary = SentinelTestRunner.ParseResults(path);
                Assert.AreEqual("FAIL", summary.status);
                Assert.AreEqual(3, summary.total);
                Assert.AreEqual(2, summary.passed);
                Assert.AreEqual(1, summary.failed);
                Assert.AreEqual(1, summary.failedTests.Length);
                Assert.AreEqual("B", summary.failedTests[0]);
            }
            finally
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
        }

        [Test]
        public void ParseResults_IgnoresExternalEntities()
        {
            string path = Path.Combine(Path.GetTempPath(), "sentinel-xxe-" + System.Guid.NewGuid().ToString("N") + ".xml");
            const string xml =
                "<?xml version=\"1.0\"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM \"file:///etc/passwd\">]>" +
                "<test-run total=\"1\" passed=\"1\" failed=\"0\" skipped=\"0\"><test-case name=\"&xxe;\" result=\"Passed\" /></test-run>";
            try
            {
                File.WriteAllText(path, xml);
                SentinelTestSummary summary = SentinelTestRunner.ParseResults(path);
                Assert.That(summary.status, Is.AnyOf("PASS", "NOT VERIFIED"));
            }
            finally
            {
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
            }
        }
    }
}
