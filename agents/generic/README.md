# Generic agent adapter

For agents without a dedicated integration (Aider, Continue, custom RAG agents,
in-house orchestrators).

**Install**

```bash
npx unity-sentinel init --agents generic
```

**Files installed**

| Path | Purpose |
| --- | --- |
| `.sentinel/agents/generic/SKILL.md` | Shared policy (copy of the repository `SKILL.md`) |
| `.sentinel/agents/generic/instructions.md` | This adapter |
| `.sentinel/toolkit/` | Self-contained Python toolkit used by the CLI |

Give the agent both files, then let it follow the loop in `instructions.md`.
The adapter deliberately avoids any vendor-specific syntax so it can be pasted
into a system prompt, a tool description or a RAG document.
