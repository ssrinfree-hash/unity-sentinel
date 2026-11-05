# UNITY SENTINEL — Unity Editor module

This folder contains the **Editor-side** part of UNITY SENTINEL. It exists
because some checks are only trustworthy inside Unity: resolving prefab
overrides, detecting Missing Scripts on real hierarchies, and reading the
active render pipeline.

Everything here is Editor-only code (assembly `UnitySentinel.Editor`,
`includePlatforms: ["Editor"]`), so nothing ships in a player build.

## Installation

### Option A — copy into the project (recommended)

```
<YourUnityProject>/
  Packages/
    unity-sentinel/          <- copy the `unity/` folder here
      Editor/
      Tests/
```

Unity treats every folder below `Packages/` that contains an `.asmdef` as a
local package. Because the assemblies are marked `includePlatforms: ["Editor"]`,
**no runtime code is compiled into builds**, which is why `unity/` can be copied
as-is without a `package.json` manifest.

### Option B — copy into `Assets/`

```
<YourUnityProject>/Assets/UnitySentinel/
  Editor/
  Tests/
```

Both layouts are supported; use whichever fits your project conventions.

## Menu

| Menu item | What it does | Output |
| --- | --- | --- |
| `Tools > Unity Sentinel > Project Info (JSON)` | Collects Unity version, render pipeline, packages, build scenes | `.sentinel/unity-project-info.json` |
| `Tools > Unity Sentinel > Validate All Scenes` | Opens every scene additively, counts missing scripts, closes without saving | `.sentinel/unity-scenes-report.json` |
| `Tools > Unity Sentinel > Validate All Prefabs` | Loads every prefab read-only and counts missing scripts | `.sentinel/unity-prefabs-report.json` |
| `Tools > Unity Sentinel > Import Test Results...` | Parses an NUnit XML produced by the Unity Test Framework | `.sentinel/unity-test-results.json` |

## Batchmode

```bash
Unity -batchmode -quit \
  -projectPath /path/to/UnityProject \
  -executeMethod UnitySentinel.EditorTools.SentinelMenu.BatchScan \
  -sentinelOutput /path/to/project/.sentinel/unity-batch-report.json \
  -logFile -
```

Exit codes: `0` no errors, `1` errors found, `2` the scan itself failed.

Run the tests the same way:

```bash
Unity -batchmode -quit -projectPath /path/to/UnityProject \
  -runTests -testPlatform EditMode \
  -testResults /path/to/project/.sentinel/editmode-results.xml \
  -logFile -
```

## EditMode tests

`unity/Tests/Editor/SentinelValidatorTests.cs` covers:

* project info collection (`Application.unityVersion` round-trip);
* render pipeline detection;
* error handling for missing scene/prefab paths and empty paths;
* prefab validation on a generated prefab (created and deleted inside the test);
* NUnit result parsing, including a "failed test" case and an XXE guard.

## Honest scope

* The Editor module does **not** rewrite scenes, prefabs or `.meta` files.
* Scenes are opened **additively** and closed without saving, so the currently
  open scene setup is preserved. If Unity cannot guarantee that (for example
  during a script reload), close the Editor first.
* The minimum verified API baseline is **Unity 2021.3 LTS**. All APIs used
  (`GraphicsSettings.currentRenderPipeline`, `PackageInfo.GetAllRegisteredPackages`,
  `EditorSceneManager.OpenScene(Additive)`, `PrefabUtility.GetPrefabAssetType`)
  exist since 2019.3, but the project has only been statically reviewed — see
  [`docs/unity-integration.md`](../docs/unity-integration.md) for the exact
  verification status.
