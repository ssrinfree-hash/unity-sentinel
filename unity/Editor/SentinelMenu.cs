// UNITY SENTINEL — Editor menu and batchmode entry points.
//
// Menu: Tools > Unity Sentinel
//   - Project Info (JSON)          -> .sentinel/unity-project-info.json
//   - Validate All Scenes          -> .sentinel/unity-scenes-report.json
//   - Validate All Prefabs         -> .sentinel/unity-prefabs-report.json
//   - Import Test Results...       -> .sentinel/unity-test-results.json
//
// Batchmode:
//   Unity -batchmode -quit -projectPath <path> \
//         -executeMethod UnitySentinel.EditorTools.SentinelMenu.BatchScan \
//         -sentinelOutput <output.json>
//
// The batch entry point exits with code 0 when no errors were found, 1 when at
// least one error was found and 2 when the scan itself failed. It never saves
// scenes or prefabs.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace UnitySentinel.EditorTools
{
    /// <summary>Menu items and batchmode entry points.</summary>
    public static class SentinelMenu
    {
        private const string LogPrefix = "[Unity Sentinel]";
        private const string MenuRoot = "Tools/Unity Sentinel/";

        [MenuItem(MenuRoot + "Project Info (JSON)", false, 1)]
        public static void WriteProjectInfo()
        {
            SentinelProjectInfoData data = SentinelProjectInfo.Collect();
            string path = SentinelProjectInfo.WriteToProject(data);
            EditorUtility.DisplayDialog(
                "Unity Sentinel",
                "Project information written to:\n" + path,
                "OK");
        }

        [MenuItem(MenuRoot + "Validate All Scenes", false, 20)]
        public static void ValidateAllScenes()
        {
            List<SentinelIssue> issues = SentinelSceneValidator.ValidateAllScenes();
            string path = WriteValidationReport("scenes", issues, CountScenes());
            int errors = CountErrors(issues);
            EditorUtility.DisplayDialog(
                "Unity Sentinel",
                "Scenes validated. Issues: " + issues.Count + " (errors: " + errors + ").\n" + path,
                "OK");
        }

        [MenuItem(MenuRoot + "Validate All Prefabs", false, 21)]
        public static void ValidateAllPrefabs()
        {
            List<SentinelIssue> issues = SentinelPrefabValidator.ValidateAllPrefabs();
            string path = WriteValidationReport("prefabs", issues, AssetDatabase.FindAssets("t:Prefab").Length);
            int errors = CountErrors(issues);
            EditorUtility.DisplayDialog(
                "Unity Sentinel",
                "Prefabs validated. Issues: " + issues.Count + " (errors: " + errors + ").\n" + path,
                "OK");
        }

        [MenuItem(MenuRoot + "Import Test Results...", false, 40)]
        public static void ImportTestResults()
        {
            string path = EditorUtility.OpenFilePanel("Select NUnit XML results", ProjectRoot(), "xml");
            if (string.IsNullOrEmpty(path))
            {
                return;
            }

            SentinelTestSummary summary = SentinelTestRunner.ParseResults(path);
            string output = SentinelTestRunner.ImportAndWrite(path);
            EditorUtility.DisplayDialog(
                "Unity Sentinel",
                "Status: " + summary.status +
                "\nTotal: " + summary.total + ", passed: " + summary.passed +
                ", failed: " + summary.failed + ", skipped: " + summary.skipped +
                "\n" + output,
                "OK");
        }

        /// <summary>Batchmode entry point used by the CLI.</summary>
        public static void BatchScan()
        {
            string outputArgument = GetArgument("-sentinelOutput");
            string outputPath = string.IsNullOrEmpty(outputArgument)
                ? Path.Combine(ProjectRoot(), ".sentinel", "unity-batch-report.json")
                : outputArgument;

            try
            {
                var issues = new List<SentinelIssue>();
                issues.AddRange(SentinelSceneValidator.ValidateAllScenes());
                issues.AddRange(SentinelPrefabValidator.ValidateAllPrefabs());

                SentinelValidationReport report = BuildReport("batch", issues, CountScenes() + AssetDatabase.FindAssets("t:Prefab").Length);
                WriteJson(outputPath, report);

                int errors = CountErrors(issues);
                Debug.Log(LogPrefix + " Batch scan finished: " + issues.Count + " issue(s), " + errors + " error(s). Output: " + outputPath);
                EditorApplication.Exit(errors > 0 ? 1 : 0);
            }
            catch (Exception exception)
            {
                Debug.LogError(LogPrefix + " Batch scan failed: " + exception);
                EditorApplication.Exit(2);
            }
        }

        private static SentinelValidationReport BuildReport(string kind, List<SentinelIssue> issues, int assetCount)
        {
            return new SentinelValidationReport
            {
                generatedAt = DateTime.UtcNow.ToString("o"),
                unityVersion = Application.unityVersion,
                kind = kind,
                assetCount = assetCount,
                issueCount = issues.Count,
                issues = issues.ToArray(),
            };
        }

        private static string WriteValidationReport(string kind, List<SentinelIssue> issues, int assetCount)
        {
            string directory = Path.Combine(ProjectRoot(), ".sentinel");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "unity-" + kind + "-report.json");
            WriteJson(path, BuildReport(kind, issues, assetCount));
            return path;
        }

        private static void WriteJson(string path, SentinelValidationReport report)
        {
            string directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(directory))
            {
                Directory.CreateDirectory(directory);
            }

            File.WriteAllText(path, JsonUtility.ToJson(report, true));
        }

        private static int CountErrors(List<SentinelIssue> issues)
        {
            int errors = 0;
            foreach (SentinelIssue issue in issues)
            {
                if (issue.severity == "error" || issue.severity == "critical")
                {
                    errors++;
                }
            }

            return errors;
        }

        private static int CountScenes()
        {
            return AssetDatabase.FindAssets("t:Scene").Length;
        }

        private static string ProjectRoot()
        {
            return Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
        }

        private static string GetArgument(string name)
        {
            string[] arguments = Environment.GetCommandLineArgs();
            for (int index = 0; index < arguments.Length - 1; index++)
            {
                if (arguments[index] == name)
                {
                    return arguments[index + 1];
                }
            }

            return null;
        }
    }
}
