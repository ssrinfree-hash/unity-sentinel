# Cursor

**Status:** project rule in the documented `.cursor/rules/*.mdc` format.
Scoping (`globs`, `alwaysApply`) was written to match Cursor's documented MDC
frontmatter; live-client verification was not performed in this repository.

**Install**

```bash
npx unity-sentinel init --agents cursor
```

**Files**

| Path | Purpose |
| --- | --- |
| `.cursor/rules/unity-sentinel.mdc` | Rule with frontmatter + shared policy |
| `.sentinel/toolkit/` | Python toolkit used by `npx unity-sentinel ...` |

**Use**

Type `@unity-sentinel` in chat, or mention "Unity project" and a `.cs`,
`.unity` or `.prefab` file so the globs attach the rule.
