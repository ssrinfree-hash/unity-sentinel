# Cursor adapter

Cursor reads project rules from `.cursor/rules/*.mdc` (MDC = Markdown with a
small frontmatter block). Rules can be scoped with `globs` and applied
automatically or on demand with `alwaysApply`.

## Installation

```bash
npx unity-sentinel init --agents cursor
```

Creates:

```
.cursor/rules/unity-sentinel.mdc
```

The rule uses:

```yaml
---
description: UNITY SENTINEL — safe Unity change protocol
globs: ["Assets/**/*.cs", "Assets/**/*.unity", "Assets/**/*.prefab"]
alwaysApply: false
---
```

`alwaysApply: false` keeps the rule out of unrelated conversations; it is
attached when a Unity asset is in context, or when you reference it with
`@unity-sentinel`.

## Prompt that works well

```text
@unity-sentinel Create a null-safe guard for EnemyBehaviour.target.
Follow the protocol: scan, plan, show the diff, then apply after my approval.
```

## Limitations

* Cursor does not execute Unity Editor APIs; scene/prefab validation must run in
  the Editor (`Tools > Unity Sentinel`) or in batchmode.
* Cursor's rule format and discovery folder may change between versions. If
  `.cursor/rules/` is not picked up by your build, check Cursor's documentation —
  UNITY SENTINEL does not claim support for undocumented locations.
* Terminal-based checks require Python 3.10+ on the machine running Cursor.
