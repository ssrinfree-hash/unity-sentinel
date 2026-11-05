// UNITY SENTINEL — Editor-side prefab validator.
//
// Loads prefabs read-only with AssetDatabase.LoadAssetAtPath, inspects them for
// missing MonoBehaviour scripts and for missing prefab assets. Prefabs are
// never modified or saved.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace UnitySentinel.EditorTools
{
    /// <summary>Validates prefab assets through the Unity Editor API.</summary>
    public static class SentinelPrefabValidator
    {
        private const string LogPrefix = "[Unity Sentinel]";

        /// <summary>Validate a single prefab by asset path.</summary>
        public static List<SentinelIssue> ValidatePrefab(string prefabPath)
        {
            var issues = new List<SentinelIssue>();
            if (string.IsNullOrEmpty(prefabPath))
            {
                issues.Add(new SentinelIssue(
                    "UNITY_PREFAB_PATH_EMPTY",
                    "error",
                    "Prefab path is empty.",
                    prefabPath,
                    null,
                    "Pass a valid Assets/.../*.prefab path."));
                return issues;
            }

            if (!File.Exists(prefabPath))
            {
                issues.Add(new SentinelIssue(
                    "UNITY_PREFAB_NOT_FOUND",
                    "error",
                    "Prefab file does not exist.",
                    prefabPath,
                    null,
                    "Check that the prefab was not deleted or moved outside the project."));
                return issues;
            }

            GameObject prefab = AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if (prefab == null)
            {
                issues.Add(new SentinelIssue(
                    "UNITY_PREFAB_LOAD_FAILED",
                    "error",
                    "Prefab could not be loaded by the AssetDatabase.",
                    prefabPath,
                    null,
                    "Reimport the prefab in Unity and check for import errors."));
                return issues;
            }

            PrefabAssetType assetType = PrefabUtility.GetPrefabAssetType(prefab);
            if (assetType == PrefabAssetType.MissingAsset || assetType == PrefabAssetType.NotAPrefab)
            {
                issues.Add(new SentinelIssue(
                    "PREFAB_BROKEN_ROOT",
                    "error",
                    "Prefab root is missing or the asset is not a prefab (" + assetType + ").",
                    prefabPath,
                    null,
                    "Restore the prefab from version control."));
            }

            Transform[] transforms;
            try
            {
                transforms = prefab.GetComponentsInChildren<Transform>(true);
            }
            catch (Exception exception)
            {
                issues.Add(new SentinelIssue(
                    "UNITY_PREFAB_INSPECT_FAILED",
                    "warning",
                    "Prefab hierarchy could not be inspected: " + exception.Message,
                    prefabPath,
                    null,
                    "Open the prefab in the Editor and check for import problems."));
                return issues;
            }

            foreach (Transform transform in transforms)
            {
                int missing = 0;
                foreach (Component component in transform.gameObject.GetComponents<Component>())
                {
                    if (component == null)
                    {
                        missing++;
                    }
                }

                if (missing > 0)
                {
                    issues.Add(new SentinelIssue(
                        "PREFAB_MISSING_SCRIPT",
                        "error",
                        "Prefab object has " + missing + " missing script component(s).",
                        prefabPath,
                        transform.name,
                        "Restore the script (check git history for its .meta GUID) or remove the empty component."));
                }
            }

            return issues;
        }

        /// <summary>Validate every prefab in the project.</summary>
        public static List<SentinelIssue> ValidateAllPrefabs()
        {
            var issues = new List<SentinelIssue>();
            string[] guids = AssetDatabase.FindAssets("t:Prefab");
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path))
                {
                    continue;
                }

                issues.AddRange(ValidatePrefab(path));
            }

            Debug.Log(LogPrefix + " Validated " + guids.Length + " prefab(s); issues: " + issues.Count + ".");
            return issues;
        }
    }
}
