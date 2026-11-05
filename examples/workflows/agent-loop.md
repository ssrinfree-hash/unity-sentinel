# Agent loop — a worked example

The same loop for every agent. Commands use the npm wrapper; `python3
scripts/sentinel.py <cmd>` works identically.

## 1. Discover

```bash
npx unity-sentinel doctor
npx unity-sentinel scan --project . --baseline
```

Agent records: Unity version, render pipeline, package list, all errors and
warnings, and the environment matrix (`unity=no` means editor checks will be
skipped).

## 2. Understand

```bash
grep -rn "EnemyBehaviour" Assets/ | head -50
```

The agent finds every usage before changing anything, and notes that the prefab
`Assets/Prefabs/Enemy.prefab` serialises a reference to this component.

## 3. Plan

`.sentinel/changes.json` (see `changes.example.json`):

```bash
npx unity-sentinel plan --project . --changes .sentinel/changes.json
```

Output lists the change, its reason, its risk and the recorded `sha256_before`.
The agent shows this to the human and waits.

## 4. Apply

```bash
npx unity-sentinel apply --project . --plan .sentinel/plan.json \
  --changes .sentinel/changes.json --dry-run --show-diff
```

The diff is reviewed. After explicit approval:

```bash
npx unity-sentinel apply --project . --plan .sentinel/plan.json \
  --changes .sentinel/changes.json --yes
```

Backup + journal entries are created. Reverting is one command away.

## 5. Verify

```bash
npx unity-sentinel verify --project .
```

Expected: `0 new, 0 resolved` findings and the modified file listed. If Unity is
available, run the Editor module batch scan and import the EditMode results.

## 6. Report

```text
Status: PASS WITH WARNINGS
Changed: Assets/Scripts/EnemyBehaviour.cs (null guard)
Checks: scan.project PASS · meta.integrity PASS · references.guid PASS · regression PASS
Skipped: unity.editor_checks (no Unity Editor), unity.tests (no Unity Editor)
Limitations: scene/prefab references not validated in-editor
Next: run Tools > Unity Sentinel > Validate All Prefabs inside Unity
```
