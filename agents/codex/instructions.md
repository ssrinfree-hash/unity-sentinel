# OpenAI Codex adapter

Codex clients have shipped several instruction mechanisms over time
(`AGENTS.md`, repository instructions, and most recently skill folders). Because
the exact discovery rules depend on the Codex version and the surface
(CLI, IDE extension, cloud), UNITY SENTINEL does **not** assume a single
automatic path. It installs a self-contained folder and gives you a one-line
snippet to wire it into whatever mechanism your client supports.

## Installation

```bash
npx unity-sentinel init --agents codex
```

Created files:

```
.sentinel/agents/codex/SKILL.md            <- shared policy
.sentinel/agents/codex/instructions.md     <- this adapter
.sentinel/agents/codex/AGENTS.snippet.md   <- paste into AGENTS.md (or equivalent)
.sentinel/toolkit/                         <- Python toolkit
```

## Wiring options

1. **AGENTS.md (works across Codex surfaces)** — append the content of
   `AGENTS.snippet.md` to your repository `AGENTS.md`. Codex reads repository
   instructions at task start.
2. **Skill folder (newer Codex builds)** — if your Codex version supports a
   skills directory, point it at `.sentinel/agents/codex/` or copy
   `SKILL.md` into `.codex/skills/unity-sentinel/SKILL.md`. Verify the path
   against your client's documentation; it is not guaranteed to be stable.
3. **Explicit prompt** — when in doubt, start the session with:

```text
Read .sentinel/agents/codex/SKILL.md before doing anything in this repository.
Unity project rules apply: scan -> plan -> confirm -> apply -> verify -> report.
```

## Environment notes

* Codex sandboxes may block network access. UNITY SENTINEL never needs network.
* The Python CLI must be available (`python3`); the npm wrapper falls back to
  `python` and `py -3` on Windows.
* Codex cloud runs cannot open a Unity Editor. Expect status `NOT VERIFIED` for
  scene/prefab validation there — the report states this explicitly.

## Verification status

Structure and commands were tested locally on the Python side. The Codex client
integration itself was **not** executed in this repository, so it is documented
as *manual wiring required* rather than "supported out of the box".
