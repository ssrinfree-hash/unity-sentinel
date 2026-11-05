# Claude Code

**Status:** skill structure follows the documented `.claude/skills/<name>/SKILL.md`
layout. Automatic activation was not verified against a live Claude Code client
in this repository — see [`docs/agent-compatibility.md`](../../docs/agent-compatibility.md).

**Install**

```bash
npx unity-sentinel init --agents claude
npx unity-sentinel init --agents claude --team   # + the six-role agent team
```

**What you get**

| Path | Purpose |
| --- | --- |
| `.claude/skills/unity-sentinel/SKILL.md` | Activation policy and the mandatory workflow |
| `.claude/skills/unity-sentinel/INSTRUCTIONS.md` | Adapter note, prompt examples, limitations |
| `.sentinel/team/` (optional) | Role prompts for subagents |

**Typical session**

```text
Read .claude/skills/unity-sentinel/SKILL.md.
Scan the project, plan the change, show me the diff, then implement it after my approval.
```
