# Claude Code adapter

Claude Code supports *skills* — folders with a `SKILL.md` whose YAML frontmatter
declares `name` and `description`, plus optional supporting files that the model
reads on demand. UNITY SENTINEL is structured to match that convention.

## Installation

```bash
# inside your Unity project
npx unity-sentinel init --agents claude
```

This creates:

```
.claude/skills/unity-sentinel/
  SKILL.md          <- frontmatter + activation policy + workflow
  INSTRUCTIONS.md   <- this adapter (project-specific wiring)
.sentinel/toolkit/  <- Python toolkit used by the CLI
```

If you prefer a user-level install, copy the same folder to
`~/.claude/skills/unity-sentinel/`. Both locations follow the documented
`skills/<name>/SKILL.md` layout; verify against your Claude Code version, as
discovery paths have changed between releases.

## Activation

Claude reads the frontmatter `description` and activates the skill when a request
matches. The description in `SKILL.md` mentions Unity projects, C# scripts,
prefabs, scenes, `.meta` files, GUIDs and "safe changes" so that it is picked up
for Unity work and stays quiet for unrelated tasks.

If the skill does not activate automatically, mention it explicitly:

> Use the `unity-sentinel` skill. Scan the project first.

## Recommended prompt

```text
Read .claude/skills/unity-sentinel/SKILL.md and follow it.
Task: <your task>
Constraints: plan first, show the diff, do not touch .meta GUIDs.
```

## Subagents

`npx unity-sentinel init --team` installs `.sentinel/team/*.md`. Start one
subagent per role (scout → planner → implementer → reviewer → verifier →
reporter) and pass the role file as the subagent prompt.

## Notes and limitations

* The skill never requires network access; all checks run locally.
* Claude Code cannot execute Unity Editor APIs. Scene/prefab validation is
  delegated to `Tools > Unity Sentinel` inside the Editor, or to
  `Unity -batchmode -executeMethod UnitySentinel.EditorTools.SentinelMenu.BatchScan`.
* Frontmatter fields in `SKILL.md` are intentionally limited to `name` and
  `description`; no vendor-specific keys are mixed in.
