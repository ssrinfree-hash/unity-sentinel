# Troubleshooting

## "does not look like a Unity project (Assets/ not found)"

Pass the folder that **contains** `Assets/`:

```bash
npx unity-sentinel scan --project /path/to/MyGame      # correct
npx unity-sentinel scan --project /path/to/MyGame/Assets  # wrong
```

## Status is `NOT VERIFIED` / exit code 2

Mandatory checks did not run — most often because Unity Editor is missing, so the
editor-side checks are `SKIPPED`. Read the *Skipped checks* section of the report.
This is intentional: the tool refuses to claim full verification.

Fix: install Unity, or pass `--unity /path/to/Unity` / set `UNITY_EDITOR_PATH`.

## "Refusing to write without explicit confirmation"

`apply` needs `--yes`. Always inspect `--dry-run --show-diff` first.

## "file changed since the plan"

The file's SHA-256 differs from the hash recorded during `plan`. Either you edited
it, a formatter did, or a Unity import ran. Re-generate the plan:

```bash
npx unity-sentinel plan --project . --changes .sentinel/changes.json
```

## "expected exactly one match for the search text, found N"

The `search` string is not unique (or absent). Add more context to the search
string. Never switch to whole-file replacement unless you really intend it.

## "protected path requires elevated confirmation"

`ProjectSettings/` and `Packages/` are protected. Add `"allow_protected": true`
to the specific change **and** review it deliberately.

## "Backup already exists and will not be overwritten"

The same `run_id` was reused (or the clock produced the same second). Use a new
run — Sentinel refuses to destroy the previous backup, because that is your only
copy of the original bytes.

## Revert says "file changed after Sentinel wrote it"

You edited the file after the apply; reverting would delete your work. Recover
from `.sentinel/backups/<run-id>/` manually if you really want the old bytes.

## `Python 3.10+ was not found`

* Windows: install Python 3.10+ and tick "Add to PATH", or set
  `UNITY_SENTINEL_PYTHON=C:\Python312\python.exe`.
* macOS/Linux: `python3 --version`; install via your package manager.
* Then run `npx unity-sentinel doctor`.

## `npx unity-sentinel` downloads a different package

`npx` resolves `unity-sentinel` from the public registry. Until the package is
published (or if the name is taken), use the GitHub form:

```bash
npx github:ssrinfree-hash/unity-sentinel init --agents all --team
```

## Scans are slow on a huge project

Tune the config:

```json
{ "scan": { "max_files": 50000, "max_depth": 20,
            "exclude_directories": ["Library","Temp","Logs","Vendor"] } }
```

Large binaries are listed in `oversized_files` instead of being read.

## `REF_UNKNOWN_GUID` for engine or package assets

Expected. GUIDs that live inside packages or Unity's built-in resources have no
project `.meta`. The finding is a warning with `medium` confidence for exactly
this reason. Confirm inside Unity before changing anything.

## Unity module does not compile

* Confirm the folder layout includes the `.asmdef` files.
* Confirm `UNITY_INCLUDE_TESTS` is defined for the tests assembly (default for
  Editor in Unity 2019.3+).
* The module was **not compiled in CI** (no Unity available); report compile
  errors as issues.

## Windows console shows mojibake

Set `PYTHONUTF8=1` (the npm wrapper does this) or run
`chcp 65001` before invoking the Python script directly.

## Nothing is found but the project feels broken

File-based checks cannot see runtime behaviour, reflection, Addressables or
binary-serialised assets. Use the Editor module and the Unity Profiler/Test
Framework. An empty report means *no known issue was detected by these checks*.
