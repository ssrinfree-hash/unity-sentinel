---
name: unity-sentinel
description: Safe, verifiable workflow for changing existing Unity projects. Use whenever a task involves Unity C# scripts, scenes, prefabs, ScriptableObjects, .meta files, GUID references, asmdef files, packages, render pipelines or Unity Test Framework results — especially before modifying them. Enforces scan → plan → confirm → apply → verify → report and refuses to declare work done without executed checks.
---

# UNITY SENTINEL — skill instructions

**Your AI Unity Engineering Guardian.**

You are working in a Unity project. Existing scenes, prefabs and assets are
serialised data: a careless edit silently breaks references that only fail at
runtime or on a device. This skill defines the *only* acceptable way to change
such a project.

> Core rule: **understand → plan → get permission → change minimally → verify →
> report honestly.** Never claim a check passed if it was not executed.

---

## 1. When to activate

Activate this skill when the user asks you to:

* read, modify or debug Unity C# scripts (`Assets/**/*.cs`);
* touch scenes, prefabs, ScriptableObjects, materials, animations;
* investigate "Missing Script", broken references, duplicated GUIDs, `.meta`
  problems, asmdef/assembly errors, package or render-pipeline issues;
* run or interpret Unity tests (EditMode/PlayMode);
* generate a project report or audit a Unity project.

Do **not** activate it for:

* creating a brand-new Unity project from scratch (no existing assets to protect);
* pure game-design questions with no file changes;
* Unity-unrelated repositories — even if they contain the word "scene".

## 2. What this skill covers — and what it does not

Covered (implemented and tested in this repository):

| Capability | Tool |
| --- | --- |
| Project root detection, Unity version, packages, render pipeline | `sentinel scan` |
| File inventory with generated-directory exclusions | `sentinel scan` |
| `.meta` integrity: missing / orphan / invalid / duplicate GUID | `sentinel meta-check` |
| Unknown GUID references in text assets | `sentinel references` |
| Assembly definition graph and cycles | `sentinel scan` |
| File-level scene/prefab structure anomalies | `sentinel scan` |
| Heuristic performance smells (clearly labelled as heuristics) | `sentinel scan` |
| Safe edits: plan, dry-run, hash lock, backup, journal, revert | `sentinel plan` / `apply` / `revert` |
| Regression detection against a baseline | `sentinel verify` |
| JSON + Markdown reports with secret redaction | `sentinel scan` / `report` |
| Editor-side scene/prefab validation and NUnit import | Unity module (`unity/`) |

**Not covered — do not pretend otherwise:**

* It is **not** a Unity Editor, a compiler, or a replacement for the Unity Test
  Framework. It cannot compile C#, execute gameplay code, or prove runtime
  behaviour.
* Scene/prefab reference resolution and prefab overrides require working inside
  Unity. Without a Unity installation these checks are `SKIPPED` — say so.
* Reflection-based, `Resources.Load`-based and Addressables references are
  invisible to the GUID scan.
* Performance findings are **heuristics**, never profiler measurements.
* An empty finding list is not proof of correctness; it means *no known issue was
  detected by these checks*.

## 3. Mandatory workflow

Follow all phases. Each phase ends with a recorded artefact (report, plan,
journal entry) — that is what makes your claims verifiable.

### PHASE 1 — DISCOVER

```bash
npx unity-sentinel doctor
npx unity-sentinel scan --project . --baseline
```

1. Confirm `Assets/`, `Packages/`, `ProjectSettings/` exist.
2. Read the Unity version from `ProjectSettings/ProjectVersion.txt` — trust only
   that file, never guess.
3. Note whether Unity Editor, Python, .NET and Git are available. The `doctor`
   command reports this.
4. Never scan `Library/`, `Temp/`, `Obj/`, `Builds/` or VCS caches.

### PHASE 2 — BASELINE

1. `scan --baseline` stores `.sentinel/baseline.json` (findings + file hashes).
2. Capture `git status --porcelain` in your notes.
3. Do not read files that look like credentials (`.env`, `*.pem`, `*.key`,
   `*credential*`); Sentinel never hashes or reports them.

### PHASE 3 — UNDERSTAND

1. Search for existing implementations before writing anything
   (`grep -rn "ClassName" Assets/`).
2. Check namespaces, asmdef boundaries and references.
3. List every call site of the API you intend to change.
4. Identify serialised fields, `UnityEvent`s and public API surface.
5. State the risk to scenes/prefabs/ScriptableObjects explicitly.

### PHASE 4 — PLAN

Write the intended edit as data, then let the tool validate it:

```json
{
  "changes": [
    {
      "path": "Assets/Scripts/EnemyBehaviour.cs",
      "search": "public Transform target;",
      "replacement": "public Transform target;\n        // null-check added",
      "reason": "avoid NullReferenceException when no target is assigned"
    }
  ]
}
```

```bash
npx unity-sentinel plan --project . --changes .sentinel/changes.json
```

`plan` validates paths, records `sha256_before` and produces
`.sentinel/plan.json`. It **never** writes to the project.

Show the user: files to change, why, the expected effect, the risks, and which
operations need elevated confirmation (`ProjectSettings/`, `Packages/`,
serialised Unity data). **Wait for an explicit "yes".**

### PHASE 5 — APPLY

```bash
npx unity-sentinel apply --project . --plan .sentinel/plan.json \
  --changes .sentinel/changes.json --dry-run --show-diff
# after the diff matches the plan and the user confirmed:
npx unity-sentinel apply --project . --plan .sentinel/plan.json \
  --changes .sentinel/changes.json --yes
```

Rules enforced by the tool (and by you):

* every write target must resolve inside the project root;
* files changed since planning are refused (hash lock);
* search text must match exactly once;
* original bytes go to `.sentinel/backups/<run>/`; the run is appended to
  `.sentinel/journal.jsonl`;
* writes are atomic (temp file + `os.replace`);
* generated directories are never written;
* `ProjectSettings/` and `Packages/` need `allow_protected: true` **and**
  elevated user confirmation.

### PHASE 6 — VALIDATE

```bash
npx unity-sentinel verify --project .
```

1. Re-run every file-based check and compare with the baseline.
2. Classify each `REGRESSION_*` finding: expected (matches the plan) or
   unexpected.
3. Run the project's own tests when they exist.
4. If Unity is available:
   * `Tools > Unity Sentinel > Validate All Scenes / Prefabs`, or
   * `Unity -batchmode -quit -projectPath . -executeMethod UnitySentinel.EditorTools.SentinelMenu.BatchScan`,
   * Unity tests: `Unity -batchmode -runTests -testPlatform EditMode -testResults .sentinel/editmode-results.xml`.
5. Explicitly list checks that could **not** be executed.

### PHASE 7 — REPORT

Report structure:

```text
Status: PASS | PASS WITH WARNINGS | FAIL | NOT VERIFIED
Changed files: <path — reason>
Checks executed: <id — result>
New findings: <code — path:line>
Pre-existing findings: <code — path:line>
Skipped checks: <id — why>
Limitations: ...
Next actions: ...
```

`PASS` is allowed only when the checks that matter for the change actually ran
and passed. With no Unity Editor, scene/prefab validation is **not verified** —
say so instead of implying success.

## 4. Safe and forbidden operations

**Allowed**

* read any project file except credential-like ones;
* run `scan`, `meta-check`, `references`, `plan`, `verify`, `report`, `benchmark`;
* run `apply` with `--dry-run` at any time;
* run `apply --yes` **after** explicit user confirmation;
* run `revert` (it refuses to overwrite manual edits made after Sentinel's write).

**Forbidden**

* editing `.meta` GUIDs, or creating `.meta` files by hand;
* hand-editing scene/prefab/asset YAML;
* writing inside `Library/`, `Temp/`, `Obj/`, `Logs/`, `Builds/`, `UserSettings/`;
* `git reset --hard`, `git checkout -- .`, `git clean -fd`, force push;
* deleting assets "to clean up" without explicit instruction;
* sending project code, tokens or credentials to any external service;
* declaring success when tests did not run.

## 5. Commands and exit codes

| Command | Purpose |
| --- | --- |
| `sentinel doctor` | environment availability |
| `sentinel scan --project . [--baseline] [--json]` | read-only analysis + reports |
| `sentinel meta-check --project .` | `.meta`/GUID validation only |
| `sentinel references --project .` | unknown GUID references only |
| `sentinel plan --project . --changes file.json` | validated plan, no writes |
| `sentinel apply --project . --plan plan.json [--dry-run] [--yes]` | guarded writes |
| `sentinel revert --project . [--run-id ID]` | undo Sentinel's own changes |
| `sentinel verify --project . [--baseline path]` | regression comparison |
| `sentinel report --input report.json` | Markdown from JSON |
| `sentinel benchmark` | synthetic benchmark metrics |

Exit codes: `0` pass, `1` fail, `2` not verified, `3` fatal error.
Exit code `2` is not success — report it.

## 6. Interpreting results

| Severity / code | Meaning | Your action |
| --- | --- | --- |
| `error` / `critical` | objectively broken (invalid `.meta`, duplicated GUID, asmdef cycle, missing script) | fix or report as blocker |
| `warning` | likely problem (`REF_UNKNOWN_GUID`, orphan `.meta`, unexpected file change) | confirm in Unity, then decide |
| `info` | heuristic or informational (`PERF_*`) | mention as a hypothesis, never as a fact |
| `REGRESSION_*` | change relative to the baseline | classify as expected / unexpected |
| `SKIPPED` check | not executed (no Unity Editor) | state it in the report |

`REF_UNKNOWN_GUID` has **medium** confidence by design: the GUID may belong to a
package or engine asset. Confirm inside Unity before touching anything.

## 7. Quick reference

```bash
npx unity-sentinel init --agents all --team   # one-time setup in the project
npx unity-sentinel scan --project . --baseline
npx unity-sentinel plan --project . --changes .sentinel/changes.json
npx unity-sentinel apply --project . --plan .sentinel/plan.json --dry-run --show-diff
npx unity-sentinel apply --project . --plan .sentinel/plan.json --yes
npx unity-sentinel verify --project .
npx unity-sentinel revert --project .
```

Deep dives: [`docs/architecture.md`](docs/architecture.md),
[`docs/safety.md`](docs/safety.md), [`docs/commands.md`](docs/commands.md),
[`docs/unity-integration.md`](docs/unity-integration.md),
[`docs/agent-compatibility.md`](docs/agent-compatibility.md),
[`docs/troubleshooting.md`](docs/troubleshooting.md).
