#!/usr/bin/env python3
"""Deterministically (re)build the synthetic Unity fixtures used by the tests.

Run from the repository root::

    python tests/fixtures/_build_fixtures.py

Every fixture is artificial and contains no third-party or commercial assets.
GUIDs are hard-coded so the fixtures are stable across regenerations.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent

PROJECT_VERSION = """m_EditorVersion: 2022.3.20f1
m_EditorVersionWithRevision: 2022.3.20f1 (61c2feb0970d)
"""

MANIFEST = {
    "dependencies": {
        "com.unity.render-pipelines.universal": "14.0.9",
        "com.unity.test-framework": "1.1.33",
        "com.unity.ide.rider": "3.0.27",
        "com.unity.ugui": "1.0.0",
        "com.unity.modules.animation": "1.0.0",
        "com.unity.modules.physics": "1.0.0",
    }
}

PROJECT_SETTINGS = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!129 &1
PlayerSettings:
  m_ObjectHideFlags: 0
  companyName: SentinelFixtures
  productName: FixtureProject
  scriptingBackend:
    Standalone: 0
    Android: 1
  apiCompatibilityLevel: 6
"""

GRAPHICS_SETTINGS = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!30 &1
GraphicsSettings:
  m_ObjectHideFlags: 0
  m_SRPDefaultSettings: {}
"""


def meta(guid: str, importer: str = "DefaultImporter") -> str:
    return f"""fileFormatVersion: 2
guid: {guid}
{importer}:
  externalObjects: {{}}
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def folder_meta(guid: str) -> str:
    return f"""fileFormatVersion: 2
guid: {guid}
folderAsset: yes
DefaultImporter:
  externalObjects: {{}}
  userData:
  assetBundleName:
  assetBundleVariant:
"""


def mono_meta(guid: str) -> str:
    return f"""fileFormatVersion: 2
guid: {guid}
MonoImporter:
  externalObjects: {{}}
  serializedVersion: 2
  defaultReferences: []
  executionOrder: 0
  icon: {{instanceID: 0}}
  userData:
  assetBundleName:
  assetBundleVariant:
"""


SCENE_TEMPLATE = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!29 &1
OcclusionCullingSettings:
  m_ObjectHideFlags: 0
--- !u!1 &100000
GameObject:
  m_ObjectHideFlags: 0
  m_Name: Main Camera
  m_Component:
  - component: {{fileID: 100001}}
  - component: {{fileID: 100002}}
--- !u!4 &100001
Transform:
  m_ObjectHideFlags: 0
  m_GameObject: {{fileID: 100000}}
--- !u!114 &100002
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_GameObject: {{fileID: 100000}}
  m_Script: {{fileID: 11500000, guid: {script_guid}, type: 3}}
--- !u!114 &100003
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_GameObject: {{fileID: 100000}}
  m_Script: {{fileID: 11500000, guid: {missing_guid}, type: 3}}
"""

PREFAB_TEMPLATE = """%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!1 &100
GameObject:
  m_ObjectHideFlags: 0
  m_Name: Enemy
  m_Component:
  - component: {{fileID: 101}}
--- !u!4 &101
Transform:
  m_ObjectHideFlags: 0
  m_GameObject: {{fileID: 100}}
--- !u!114 &102
MonoBehaviour:
  m_ObjectHideFlags: 0
  m_GameObject: {{fileID: 100}}
  m_Script: {{fileID: 11500000, guid: {script_guid}, type: 3}}
"""

PLAYER_CS = """using UnityEngine;

namespace FixtureGame.Player
{
    public class PlayerController : MonoBehaviour
    {
        [SerializeField] private float speed = 5f;

        private void Awake()
        {
            Debug.Log("Player ready");
        }

        private void Update()
        {
            transform.Translate(Vector3.forward * (speed * Time.deltaTime));
        }
    }
}
"""

ENEMY_CS = """using UnityEngine;

namespace FixtureGame.Enemies
{
    public class EnemyBehaviour : MonoBehaviour
    {
        public Transform target;
    }
}
"""

SUSPICIOUS_CS = """using System.IO;
using System.Linq;
using System.Collections.Generic;
using UnityEngine;

public class HotPathSample : MonoBehaviour
{
    private void Update()
    {
        var target = FindObjectOfType<HotPathSample>();
        var rb = GetComponent<Rigidbody>();
        string label = "value: " + target + " at " + Time.time;
        var visible = FindObjectsOfType<HotPathSample>().Where(x => x != null).ToList();
        Debug.Log(label + visible.Count);
    }

    public void LoadConfig()
    {
        var text = File.ReadAllText("config.txt");
        Debug.Log(text);
    }
}
"""

GUID = {
    "assets_folder": "11111111111111111111111111111111",
    "scripts_folder": "22222222222222222222222222222222",
    "scenes_folder": "33333333333333333333333333333333",
    "prefabs_folder": "44444444444444444444444444444444",
    "player_cs": "55555555555555555555555555555555",
    "enemy_cs": "66666666666666666666666666666666",
    "suspicious_cs": "77777777777777777777777777777777",
    "scene": "88888888888888888888888888888888",
    "prefab": "99999999999999999999999999999999",
    "missing_guid": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "asmdef": "dddddddddddddddddddddddddddddddd",
    "broken_ref_scene": "cccccccccccccccccccccccccccccccc",
    "ghost": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
}


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_valid_project(base: Path) -> None:
    write(base / "ProjectSettings/ProjectVersion.txt", PROJECT_VERSION)
    write(base / "ProjectSettings/ProjectSettings.asset", PROJECT_SETTINGS)
    write(base / "ProjectSettings/GraphicsSettings.asset", GRAPHICS_SETTINGS)
    write(base / "Packages/manifest.json", json.dumps(MANIFEST, indent=2) + "\n")
    write(base / "Packages/packages-lock.json", json.dumps({"dependencies": {}}, indent=2) + "\n")

    write(base / "Assets.meta", folder_meta(GUID["assets_folder"]))
    write(base / "Assets/Scripts.meta", folder_meta(GUID["scripts_folder"]))
    write(base / "Assets/Scenes.meta", folder_meta(GUID["scenes_folder"]))
    write(base / "Assets/Prefabs.meta", folder_meta(GUID["prefabs_folder"]))

    write(base / "Assets/Scripts/PlayerController.cs", PLAYER_CS)
    write(base / "Assets/Scripts/PlayerController.cs.meta", mono_meta(GUID["player_cs"]))
    write(base / "Assets/Scripts/EnemyBehaviour.cs", ENEMY_CS)
    write(base / "Assets/Scripts/EnemyBehaviour.cs.meta", mono_meta(GUID["enemy_cs"]))

    write(
        base / "Assets/Scenes/Main.unity",
        SCENE_TEMPLATE.format(
            script_guid=GUID["player_cs"],
            missing_guid=GUID["player_cs"],
        ),
    )
    write(base / "Assets/Scenes/Main.unity.meta", meta(GUID["scene"]))

    write(
        base / "Assets/Prefabs/Enemy.prefab",
        PREFAB_TEMPLATE.format(script_guid=GUID["enemy_cs"]),
    )
    write(base / "Assets/Prefabs/Enemy.prefab.meta", meta(GUID["prefab"]))

    write(
        base / "Assets/Scripts/FixtureGame.asmdef",
        json.dumps(
            {
                "name": "FixtureGame",
                "rootNamespace": "FixtureGame",
                "references": [],
                "includePlatforms": [],
                "excludePlatforms": [],
                "allowUnsafeCode": False,
                "overrideReferences": False,
                "precompiledReferences": [],
                "autoReferenced": True,
                "defineConstraints": [],
                "versionDefines": [],
                "noEngineReferences": False,
            },
            indent=4,
        )
        + "\n",
    )
    write(base / "Assets/Scripts/FixtureGame.asmdef.meta", meta(GUID["asmdef"], "AssemblyDefinitionImporter"))

    # Generated folders must be ignored by the scanner.
    write(base / "Library/ScriptAssemblies/FixtureGame.dll", "not really a dll")
    write(base / "Temp/UnityLockfile", "")
    write(base / "Logs/Package.log", "log")


def make_broken_meta(base: Path) -> None:
    make_valid_project(base)
    # asset without .meta
    write(base / "Assets/Scripts/OrphanAsset.cs", "// no meta next to me\n")
    # .meta without asset
    write(base / "Assets/Scripts/Ghost.cs.meta", mono_meta(GUID["ghost"]))
    # invalid .meta (no guid)
    write(base / "Assets/Scripts/BrokenMeta.cs", "// invalid meta follows\n")
    write(base / "Assets/Scripts/BrokenMeta.cs.meta", "fileFormatVersion: 2\nMonoImporter:\n  userData:\n")


def make_duplicate_guid(base: Path) -> None:
    make_valid_project(base)
    write(base / "Assets/Scripts/Duplicate.cs", "// duplicate guid\n")
    write(base / "Assets/Scripts/Duplicate.cs.meta", mono_meta(GUID["player_cs"]))


def make_missing_reference(base: Path) -> None:
    make_valid_project(base)
    write(
        base / "Assets/Scenes/BrokenRef.unity",
        SCENE_TEMPLATE.format(
            script_guid=GUID["player_cs"],
            missing_guid=GUID["missing_guid"],
        ),
    )
    write(base / "Assets/Scenes/BrokenRef.unity.meta", meta(GUID["broken_ref_scene"]))


def make_suspicious_scripts(base: Path) -> None:
    make_valid_project(base)
    write(base / "Assets/Scripts/HotPathSample.cs", SUSPICIOUS_CS)
    write(base / "Assets/Scripts/HotPathSample.cs.meta", mono_meta(GUID["suspicious_cs"]))


def make_malformed_settings(base: Path) -> None:
    make_valid_project(base)
    write(base / "Packages/manifest.json", "{ this is not json,")
    write(base / "ProjectSettings/ProjectVersion.txt", "some random text without a version\n")
    write(
        base / "Assets/Scripts/A.asmdef",
        json.dumps({"name": "A", "references": ["B"]}, indent=4) + "\n",
    )
    write(
        base / "Assets/Scripts/B.asmdef",
        json.dumps({"name": "B", "references": ["A"]}, indent=4) + "\n",
    )


BUILDERS = {
    "valid_project": make_valid_project,
    "broken_meta": make_broken_meta,
    "duplicate_guid": make_duplicate_guid,
    "missing_reference": make_missing_reference,
    "suspicious_scripts": make_suspicious_scripts,
    "malformed_project_settings": make_malformed_settings,
}


def main() -> None:
    for name, builder in BUILDERS.items():
        target = HERE / name
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        builder(target)
        print(f"built {name}")


if __name__ == "__main__":
    main()
