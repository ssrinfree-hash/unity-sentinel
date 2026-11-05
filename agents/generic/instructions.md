# Generic agent adapter

Use this adapter with any assistant that can read files and run shell commands.
It contains no platform-specific frontmatter — the shared policy lives in
[`SKILL.md`](../../SKILL.md).

## Minimum viable loop

1. **Read** `SKILL.md` (or `.sentinel/SKILL.md` after `npx unity-sentinel init`).
2. **Discover**: run `npx unity-sentinel doctor` and
   `npx unity-sentinel scan --project . --baseline`.
3. **Understand**: open the files named in the report before changing anything.
4. **Plan**: write `.sentinel/changes.json` and run
   `npx unity-sentinel plan --project . --changes .sentinel/changes.json`.
   Show the plan to the user and wait for an explicit "yes".
5. **Apply**: `npx unity-sentinel apply --project . --plan .sentinel/plan.json --yes`
   (always run `--dry-run --show-diff` first).
6. **Verify**: `npx unity-sentinel verify --project .`.
7. **Report**: summarise changed files, executed checks, skipped checks and the
   final status (`PASS` / `PASS WITH WARNINGS` / `FAIL` / `NOT VERIFIED`).

## Non-negotiable rules

* Never claim a check ran if it did not run.
* Never edit `.meta` GUIDs, scene YAML or prefab YAML by hand.
* Never run `git reset --hard`, `git checkout -- .`, `git clean -fd` or force-push.
* Never touch `Library/`, `Temp/`, `Obj/`, `Logs/`, `Builds/`.
* Treat `ProjectSettings/` and `Packages/` changes as elevated-risk operations.

## Exit codes

`0` pass · `1` fail · `2` not verified · `3` fatal error.

An agent must stop and report on `1` or `3`, and must state clearly when the
result is `2` (for example because Unity Editor is unavailable).
