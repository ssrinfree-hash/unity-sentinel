# Agent compatibility

UNITY SENTINEL keeps **one** source of policy (`SKILL.md`) and thin adapters per
client. No logic is duplicated across adapters.

## Status matrix

| Client | Install command | Integration mechanism | Status |
| --- | --- | --- | --- |
| Claude Code | `npx unity-sentinel init --agents claude` | `.claude/skills/unity-sentinel/SKILL.md` (frontmatter: `name`, `description`) | Structure matches the documented skills layout. **Automatic activation not verified** against a live client. |
| OpenAI Codex | `npx unity-sentinel init --agents codex` | `AGENTS.md` snippet + `.sentinel/agents/codex/SKILL.md` | **Manual wiring.** Codex instruction mechanisms differ by version; the snippet is stable, the discovery path is not claimed. |
| Cursor | `npx unity-sentinel init --agents cursor` | `.cursor/rules/unity-sentinel.mdc` with `globs` + `alwaysApply: false` | Rule format matches Cursor's documented MDC frontmatter. Live verification not performed. |
| Generic agent | `npx unity-sentinel init --agents generic` | `.sentinel/agents/generic/{SKILL.md,instructions.md}` | **Universal**, no vendor syntax. Tested by construction (plain Markdown + CLI). |
| Agent team (6 roles) | `npx unity-sentinel init --team` | `.sentinel/team/*.md` + `team.json` | Vendor-neutral role prompts; usable with subagents in any client. |

Nothing in the table claims "works out of the box" without evidence. If your
client version changes its convention, update the adapter rather than the policy.

## Shared contract

Every adapter must point the agent at the same loop:

```
doctor → scan --baseline → plan (approval) → apply --dry-run → apply --yes → verify → report
```

and at the same prohibitions: no GUID edits, no hand-edited scene YAML, no
destructive git commands, no claims of unexecuted checks.

## Why frontmatter is minimal

`SKILL.md` uses only `name` and `description`. Vendor-specific fields
(`allowed-tools`, `model`, `globs`, …) are not mixed into the shared file because
each client interprets unknown keys differently — some reject them.

## Testing an adapter

1. `npx unity-sentinel init --agents <name>` in a scratch Unity project.
2. Confirm the files listed in the adapter README exist.
3. Ask the client: *"What should you do before modifying a Unity scene?"*
4. A working integration answers with the scan → plan → confirm → apply → verify
   flow and mentions `.sentinel/SKILL.md`.

Record the client version and the outcome when you report an integration issue.
