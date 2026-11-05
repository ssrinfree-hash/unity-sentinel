// UNITY SENTINEL — Editor-side scene validator.
//
// Opens scenes *additively* so the currently open scene setup is preserved,
// inspects them for missing MonoBehaviour scripts, and closes them again.
// Scenes are never saved and never marked dirty by this code.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UnitySentinel.EditorTools
{
    /// <summary>Validates scenes through the Unity Editor API.</summary>
    public static class SentinelSceneValidator
    {
        private const string LogPrefix = "[Unity Sentinel]";

        /// <summary>Validate a single scene by asset path.</summary>
        public static List<SentinelIssue> ValidateScene(string scenePath)
        {
            var issues = new List<SentinelIssue>();
            if (string.IsNullOrEmpty(scenePath))
            {
                issues.Add(new SentinelIssue(
                    "UNITY_SCENE_PATH_EMPTY",
                    "error",
                    "Scene path is empty.",
                    scenePath,
                    null,
                    "Pass a valid Assets/.../*.unity path."));
                return issues;
            }

            if (!File.Exists(scenePath))
            {
                issues.Add(new SentinelIssue(
                    "UNITY_SCENE_NOT_FOUND",
                    "error",
                    "Scene file does not exist.",
                    scenePath,
                    null,
                    "Check that the scene was not deleted or moved outside the project."));
                return issues;
            }

            Scene scene = default(Scene);
            bool opened = false;
            try
            {
                scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Additive);
                opened = scene.IsValid();
            }
            catch (Exception exception)
            {
                issues.Add(new SentinelIssue(
                    "UNITY_SCENE_OPEN_FAILED",
                    "error",
                    "Scene could not be opened: " + exception.Message,
                    scenePath,
                    null,
                    "Open the scene manually in the Editor to inspect the error."));
                return issues;
            }

            try
            {
                if (!opened)
                {
                    issues.Add(new SentinelIssue(
                        "UNITY_SCENE_INVALID",
                        "error",
                        "Scene handle is invalid after opening.",
                        scenePath,
                        null,
                        "Verify the scene asset with the Unity Editor."));
                    return issues;
                }

                foreach (GameObject root in scene.GetRootGameObjects())
                {
                    issues.AddRange(InspectHierarchy(root, scenePath));
                }
            }
            finally
            {
                if (opened)
                {
                    // closeWithoutSaving: the validator never writes scenes.
                    EditorSceneManager.CloseScene(scene, true);
                }
            }

            return issues;
        }

        /// <summary>Validate every scene asset in the project.</summary>
        public static List<SentinelIssue> ValidateAllScenes()
        {
            var issues = new List<SentinelIssue>();
            string[] guids = AssetDatabase.FindAssets("t:Scene");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path))
                {
                    continue;
                }

                issues.AddRange(ValidateScene(path));
            }

            Debug.Log(LogPrefix + " Validated " + guids.Length + " scene(s); issues: " + issues.Count + ".");
            return issues;
        }

        private static IEnumerable<SentinelIssue> InspectHierarchy(GameObject root, string scenePath)
        {
            var issues = new List<SentinelIssue>();
            Transform[] transforms = root.GetComponentsInChildren<Transform>(true);
            foreach (Transform transform in transforms)
            {
                GameObject gameObject = transform.gameObject;
                Component[] components = gameObject.GetComponents<Component>();
                int missing = 0;
                foreach (Component component in components)
                {
                    if (component == null)
                    {
                        missing++;
                    }
                }

                if (missing > 0)
                {
                    issues.Add(new SentinelIssue(
                        "SCENE_MISSING_SCRIPT",
                        "error",
                        "GameObject has " + missing + " missing script component(s).",
                        scenePath,
                        GetObjectPath(transform),
                        "Restore the script (check git history for its .meta GUID) or remove the empty component."));
                }
            }

            return issues;
        }

        private static string GetObjectPath(Transform transform)
        {
            var parts = new List<string>();
            Transform current = transform;
            while (current != null)
            {
                parts.Insert(0, current.name);
                current = current.parent;
            }

            return string.Join("/", parts.ToArray());
        }
    }
}
