# SAFE CHANGE PROTOCOL

Unity projects are graphs of serialised references. A single "harmless" text
edit can break a GUID, detach a prefab override, or produce Missing Scripts that
only appear on a device build. The protocol below makes every write reversible,
inspectable and testable.

## Modes

| Mode | Command | Writes to project | Purpose |
| --- | --- | --- | --- |
| `scan` | `sentinel scan` | no | full read-only analysis |
| `plan` | `sentinel plan --changes file.json` | no | validate a change set, record hashes |
| `apply --dry-run` | `sentinel apply --dry-run` | no | show the unified diff |
| `apply --yes` | `sentinel apply --yes` | yes, guarded | write with backup + journal |
| `verify` | `sentinel verify` | baseline only | regression comparison |
| `report` | `sentinel report --input report.json` | report files | re-render Markdown |
| `revert` | `sentinel revert` | yes, guarded | undo Sentinel's own writes |

## Guarantees and how they are enforced

| Guarantee | Implementation | Test |
| --- | --- | --- |
| Target must be inside the project root | `paths.ensure_within_root` (resolved paths) | `tests/test_paths.py`, `tests/test_safe_operations.py` |
| No symlink escape | `paths.check_no_symlink_escape` | `test_symlink_escape_rejected`, `test_symlink_escape_is_refused` |
| Generated directories are never written | `paths.is_safe_to_write` + config excludes | `test_generated_directory_write_rejected` |
| Protected paths need elevated confirmation | `safety.protected_paths` + `allow_protected` | `test_protected_path_requires_flag` |
| File must not change between plan and apply | SHA-256 lock (`expected_sha256`) | `test_hash_mismatch_is_refused` |
| Replacement must match exactly once | occurrence check | `test_search_must_match_exactly_once`, `test_multiple_matches_are_refused` |
| Backup is written before any write | `.sentinel/backups/<run>/<path>` with `O_EXCL` | `test_apply_writes_backup_and_journal`, `test_backup_is_never_overwritten` |
| Writes are atomic | temp file + `os.replace` + `fsync` | covered indirectly by every apply test |
| Every apply is journaled | `.sentinel/journal.jsonl` | `test_apply_writes_backup_and_journal` |
| Revert never destroys manual work | revert requires current hash == `sha256_after` | `test_revert_refuses_when_file_changed_after_apply` |
| Dry-run writes nothing | `apply_operations(dry_run=True)` | `test_dry_run_never_writes`, integration test |
| No secrets in reports | `report_generator.redact_text` + secret-file heuristic | `test_evidence_is_redacted_in_report`, integration test |

## What is never touched

* `.meta` **GUIDs** — rewriting a GUID silently breaks every reference to the
  asset. Sentinel reports problems instead of "fixing" them.
* Scene, prefab and asset YAML — parsed structurally, never rewritten.
* `Library/`, `Temp/`, `Obj/`, `Logs/`, `Builds/`, `UserSettings/` and VCS
  metadata.
* Files that look like credentials (`.env`, `*.pem`, `*.key`, `*credential*`) —
  not read for content, not hashed, never copied into reports.

## Elevated-risk operations

`ProjectSettings/` and `Packages/` are protected by default. To change them a
plan entry must explicitly set `"allow_protected": true`, and the plan must be
reviewed by a human. This is deliberate friction: a wrong package version or
scripting-backend setting can break the whole project.

Scenes, prefabs and other serialised assets should be edited **inside Unity**,
not by text replacement. If a plan includes such files, Sentinel will apply text
changes only if the search string matches exactly once — but the editor-side
module or the Unity Editor itself is the safer route.

## Recovery

```bash
# what did Sentinel change?
cat .sentinel/journal.jsonl

# undo the last run (refuses if you edited the file afterwards)
npx unity-sentinel revert --project .

# undo a specific run
npx unity-sentinel revert --project . --run-id 20261105T232621Z
```

Backups live in `.sentinel/backups/<run-id>/<original relative path>` and are
never overwritten. They are ignored by git via `.sentinel/.gitignore`.
