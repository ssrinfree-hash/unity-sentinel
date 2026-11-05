// UNITY SENTINEL — Editor-side project information collector.
// This file belongs to the Editor assembly (see UnitySentinel.Editor.asmdef) and
// never ships with a player build.
//
// Verified API baseline: Unity 2021.3 LTS. All APIs used here exist since
// Unity 2019.3; no newer API is referenced.

using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor.PackageManager;
using UnityEngine;
using UnityEngine.Rendering;

namespace UnitySentinel.EditorTools
{
    /// <summary>Serialisable project information payload (JsonUtility compatible).</summary>
    [Serializable]
    public class SentinelProjectInfoData
    {
        public string generatedAt;
        public string projectRoot;
        public string unityVersion;
        public string renderPipeline = "Unknown";
        public string renderPipelineAsset;
        public string[] packages = new string[0];
        public string[] buildScenes = new string[0];
        public string[] notes = new string[0];
    }

    /// <summary>Collects facts about the open Unity project.</summary>
    public static class SentinelProjectInfo
    {
        private const string LogPrefix = "[Unity Sentinel]";

        /// <summary>Gather project information without modifying the project.</summary>
        public static SentinelProjectInfoData Collect()
        {
            var notes = new List<string>();
            var info = new SentinelProjectInfoData
            {
                generatedAt = DateTime.UtcNow.ToString("o"),
                projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath,
                unityVersion = Application.unityVersion,
            };

            try
            {
                RenderPipelineAsset pipeline = GraphicsSettings.currentRenderPipeline;
                if (pipeline == null)
                {
                    info.renderPipeline = "Built-in";
                }
                else
                {
                    string typeName = pipeline.GetType().Name;
                    if (typeName.IndexOf("Universal", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        info.renderPipeline = "URP";
                    }
                    else if (typeName.IndexOf("HD", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        info.renderPipeline = "HDRP";
                    }
                    else
                    {
                        info.renderPipeline = "Custom";
                        notes.Add("A custom RenderPipelineAsset is assigned to GraphicsSettings.");
                    }

                    info.renderPipelineAsset = typeName;
                }
            }
            catch (Exception exception)
            {
                notes.Add("Render pipeline detection failed: " + exception.Message);
            }

            try
            {
                PackageInfo[] registered = PackageInfo.GetAllRegisteredPackages();
                var names = new List<string>(registered.Length);
                foreach (PackageInfo package in registered)
                {
                    names.Add(package.name + "@" + package.version);
                }

                names.Sort(StringComparer.Ordinal);
                info.packages = names.ToArray();
            }
            catch (Exception exception)
            {
                notes.Add("Package enumeration failed: " + exception.Message);
            }

            try
            {
                var scenes = new List<string>();
                foreach (EditorBuildSettingsScene scene in EditorBuildSettings.scenes)
                {
                    scenes.Add(scene.path);
                }

                info.buildScenes = scenes.ToArray();
            }
            catch (Exception exception)
            {
                notes.Add("Build settings could not be read: " + exception.Message);
            }

            if (string.IsNullOrEmpty(Application.unityVersion))
            {
                notes.Add("Application.unityVersion returned an empty string.");
            }

            info.notes = notes.ToArray();
            Debug.Log(LogPrefix + " Project information collected for Unity " + info.unityVersion + ".");
            return info;
        }

        /// <summary>Write the payload as JSON into the project's .sentinel folder.</summary>
        public static string WriteToProject(SentinelProjectInfoData data)
        {
            string root = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            string directory = Path.Combine(root, ".sentinel");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "unity-project-info.json");
            File.WriteAllText(path, JsonUtility.ToJson(data, true));
            Debug.Log(LogPrefix + " Wrote " + path);
            return path;
        }
    }
}
