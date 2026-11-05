# Unity integration

Some checks are only trustworthy inside Unity. The Editor module implements them
with the official APIs and writes JSON that the Python report consumes.

## What runs where

| Check | File-based (Python) | Editor module (C#) |
| --- | --- | --- |
| `.meta` / GUID integrity | ✅ authoritative | – |
| asmdef graph and cycles | ✅ authoritative | – |
| Scene structure (documents, duplicate fileIDs) | ✅ structural | ✅ authoritative |
| Missing MonoBehaviour scripts in a scene | ⚠️ only `m_Script: {fileID: 0}` | ✅ real component check |
| Prefab overrides / variants | ❌ | ✅ `PrefabUtility` |
| Serialised reference resolution | ❌ | ✅ `AssetDatabase` |
| Render pipeline | ⚠️ from manifest / GraphicsSettings | ✅ `GraphicsSettings.currentRenderPipeline` |
| Package list | ⚠️ from `manifest.json` | ✅ `PackageInfo.GetAllRegisteredPackages` |
| Unity EditMode/PlayMode tests | ❌ | ✅ via NUnit XML import |

## Installation

Copy `unity/Editor` and `unity/Tests` into:

* `Packages/unity-sentinel/` (local package; Editor-only asmdef), or
* `Assets/UnitySentinel/`.

`UnitySentinel.Editor.asmdef` declares `"includePlatforms": ["Editor"]`, so the
code never enters a player build. `UnitySentinel.Tests.asmdef` requires
`UNITY_INCLUDE_TESTS` and references `UnityEngine.TestRunner` /
`UnityEditor.TestRunner` plus `nunit.framework.dll`.

## Menu

`Tools > Unity Sentinel`:

* **Project Info (JSON)** → `.sentinel/unity-project-info.json`
* **Validate All Scenes** → `.sentinel/unity-scenes-report.json`
* **Validate All Prefabs** → `.sentinel/unity-prefabs-report.json`
* **Import Test Results...** → parses a Unity NUnit XML into
  `.sentinel/unity-test-results.json`

## Batchmode

```bash
Unity -batchmode -quit \
  -projectPath /path/to/UnityProject \
  -executeMethod UnitySentinel.EditorTools.SentinelMenu.BatchScan \
  -sentinelOutput /path/to/UnityProject/.sentinel/unity-batch-report.json \
  -logFile -
```

Exit codes: `0` clean, `1` issues found, `2` the scan failed.

Tests:

```bash
Unity -batchmode -quit -projectPath /path/to/UnityProject \
  -runTests -testPlatform EditMode \
  -testResults /path/to/UnityProject/.sentinel/editmode-results.xml \
  -logFile -
```

Then import the result:

```bash
# inside Unity: Tools > Unity Sentinel > Import Test Results...
# or programmatically:
Unity -batchmode -quit -projectPath . \
  -executeMethod UnitySentinel.EditorTools.SentinelTestRunner.ImportAndWrite \
  -sentinelResults .sentinel/editmode-results.xml
```

(The `ImportAndWrite` method takes an argument; wire it through your own
`-executeMethod` wrapper if you prefer a single command.)

## Safety in the Editor

* Scenes are opened **additively** and closed **without saving**.
* Prefabs are loaded read-only; nothing is written back.
* No `AssetDatabase` import, refresh or delete calls are used.
* `EditorApplication.Exit(code)` is only used in the batchmode entry point.
* All log messages are prefixed with `[Unity Sentinel]`.

## Verification status — read this before trusting the module

| Item | Status |
| --- | --- |
| C# source review | done |
| Compilation inside Unity | **NOT RUN** — no Unity installation in the build environment |
| Editor EditMode tests | **NOT RUN** — same reason |
| API baseline | Unity 2021.3 LTS (APIs exist since 2019.3) |

Consequences:

* Treat the first run in your project as a smoke test; report any compile error
  as an issue.
* `sentinel scan` reports the editor-side checks as `SKIPPED` with
  `requires: unity-editor`, and the report status cannot be `PASS` on the basis
  of those checks.
* Nothing in the Python toolkit pretends the Editor module ran.
