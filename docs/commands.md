# Commands

All commands work both as `python3 scripts/sentinel.py <cmd>` and
`npx unity-sentinel <cmd>`. The npm wrapper only adds `init`, `team`, `agents`
and `update`.

Exit codes: **0** pass · **1** fail · **2** not verified · **3** fatal error.

## Global options

| Option | Applies to | Meaning |
| --- | --- | --- |
| `--project PATH` | all analysis commands | Unity project root |
| `--config PATH` | all analysis commands | JSON config merged over defaults |
| `--unity PATH` | scan / verify / plan / doctor | Unity Editor executable (optional) |
| `--json` | all | machine-readable output on stdout |
| `--out DIR` | scan / verify / plan / report | output directory (default `.sentinel/`) |
| `--verbose` | all | debug logging to stderr |

## `doctor`

```bash
npx unity-sentinel doctor
```

Reports Python, Git, dotnet and Unity Editor availability. No project needed.
`UNITY_EDITOR_PATH` is honoured for the Editor path.

## `scan`

```bash
npx unity-sentinel scan --project . 
npx unity-sentinel scan --project . --baseline
npx unity-sentinel scan --project . --json
```

Read-only. Writes `report.json` and `report.md` into `--out`.
`--baseline` additionally stores `.sentinel/baseline.json` (findings + hashes).

Report sections: status, environment, summary, findings by severity, executed
checks, skipped checks, limitations, recommendations.

## `meta-check`

```bash
npx unity-sentinel meta-check --project . --json
```

Validates `.meta` files only: missing, orphan, invalid GUID, duplicate GUID.
Exit code `1` if any error-level meta finding exists.

## `references`

```bash
npx unity-sentinel references --project . --json
```

Scans text-serialised assets for `guid:` references unknown to the local
`.meta` database. Reports the limitations (packages, binary assets, reflection,
Addressables) every time, because an unknown GUID is *not* proof of a broken
reference.

## `plan`

```bash
npx unity-sentinel plan --project . --changes .sentinel/changes.json
npx unity-sentinel plan --project . --out .sentinel/plan.json
```

* with `--changes`: validates every change, records `sha256_before`, writes a
  plan. Never writes to the project.
* without `--changes`: produces an *advisory* plan from scan findings
  (`manual_steps`), useful as a to-do list for the agent.

`changes.json` format:

```json
{
  "summary": "why this change exists",
  "changes": [
    {
      "path": "Assets/Scripts/Player.cs",
      "search": "exact text to replace (must match once)",
      "replacement": "new text",
      "reason": "human readable reason",
      "expected_sha256": "optional optimistic lock",
      "allow_protected": false
    }
  ]
}
```

## `apply`

```bash
npx unity-sentinel apply --project . --plan .sentinel/plan.json --changes .sentinel/changes.json --dry-run --show-diff
npx unity-sentinel apply --project . --plan .sentinel/plan.json --changes .sentinel/changes.json --yes
```

`--changes` is required when the plan does not embed replacements (plans produced
by `plan --changes` keep only hashes). Writes are refused without `--yes`.
See [`safety.md`](safety.md).

## `revert`

```bash
npx unity-sentinel revert --project . --dry-run
npx unity-sentinel revert --project . --run-id 20261105T232621Z
```

Reverts only files recorded in the journal whose current hash still equals the
hash Sentinel wrote. Manual edits after the apply are never overwritten.

## `verify`

```bash
npx unity-sentinel scan --project . --baseline     # once
npx unity-sentinel verify --project .
npx unity-sentinel verify --project . --update-baseline
```

Produces `verify.json` / `verify.md` with `REGRESSION_NEW_ERROR`,
`REGRESSION_NEW_WARNING`, `REGRESSION_RESOLVED`,
`REGRESSION_UNEXPECTED_FILE_CHANGE`, `REGRESSION_UNEXPECTED_FILE_ADDED`,
`REGRESSION_UNEXPECTED_FILE_REMOVED`. Files changed by Sentinel itself (per the
journal) are treated as expected.

## `report`

```bash
npx unity-sentinel report --input .sentinel/verify.json
npx unity-sentinel report --input .sentinel/report.json --format json
```

## `benchmark`

```bash
npx unity-sentinel benchmark
npx unity-sentinel benchmark --json --out benchmark/results
```

Runs the synthetic benchmark and writes `benchmark_result.json`. See
[`benchmark.md`](benchmark.md).

## npm-only commands

| Command | Purpose |
| --- | --- |
| `init [--agents ...] [--team] [--force] [--dry-run]` | install skill, adapters, toolkit |
| `team` | reinstall `.sentinel/team/` |
| `agents` | list adapters and verification status |
| `update` | refresh `.sentinel/toolkit/` from the package |

## Configuration

Default config: [`config/default.json`](../config/default.json). Override with
`--config my.json` or a `.sentinel/config.json` in the working directory.

| Key | Default | Meaning |
| --- | --- | --- |
| `scan.exclude_directories` | Library, Temp, Obj, … | never scanned |
| `scan.max_file_size_bytes` | 8 MiB | bigger files are listed, not read |
| `scan.max_files` | 200000 | hard cap, sets `truncated` |
| `scan.max_depth` | 40 | directory depth cap |
| `meta.ignore_root_level_meta` | true | stray root `*.meta` are not orphans |
| `references.scan_extensions` | scene/prefab/asset/… | which assets are scanned |
| `safety.protected_paths` | ProjectSettings, Packages | elevated confirmation |
| `report.max_evidence_length` | 200 | evidence truncation |
| `performance.hot_methods` | Update, FixedUpdate, LateUpdate, OnGUI | heuristic targets |
