# OpenAI Codex

**Status:** manual wiring (client instruction mechanisms differ between Codex
versions). No automatic discovery is claimed.

**Install**

```bash
npx unity-sentinel init --agents codex
```

**Wire it up**

1. Append `.sentinel/agents/codex/AGENTS.snippet.md` to your `AGENTS.md`.
2. Or, if your Codex version supports skill folders, copy
   `.sentinel/agents/codex/SKILL.md` to `.codex/skills/unity-sentinel/SKILL.md`.
3. Or simply paste at the start of a task:
   `Read .sentinel/agents/codex/SKILL.md and follow its workflow.`

**Files**

| Path | Purpose |
| --- | --- |
| `.sentinel/agents/codex/SKILL.md` | Shared policy and workflow |
| `.sentinel/agents/codex/instructions.md` | Adapter details, sandbox notes |
| `.sentinel/agents/codex/AGENTS.snippet.md` | Ready-to-paste repository instructions |

See [`docs/agent-compatibility.md`](../../docs/agent-compatibility.md) for the
verification status of every adapter.
