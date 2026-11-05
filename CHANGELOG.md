# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11-06

First public release.

### Added

* **Skill** — `SKILL.md` with the mandatory seven-phase workflow
  (discover → baseline → understand → plan → apply → validate → report) and an
  explicit list of what the tool cannot do.
* **Python core (stdlib only)** — project detector, read-only scanner, `.meta`
  validator, GUID reference analyzer, assembly dependency graph with cycle
  detection, file-level scene/prefab validators, heuristic performance inspector,
  regression engine, report generator with secret redaction.
* **SAFE CHANGE PROTOCOL** — plan / dry-run / hash-locked apply / atomic writes /
  backups under `.sentinel/backups/` / JSONL journal / guarded revert.
* **CLI** — `doctor`, `scan`, `meta-check`, `references`, `plan`, `apply`,
  `revert`, `verify`, `report`, `benchmark`, `version` with documented exit codes
  (0 pass, 1 fail, 2 not verified, 3 fatal).
* **npm wrapper** — `init` (skill + adapters + toolkit), `team` (six agent roles),
  `agents`, `update`, and transparent proxying of the verification commands.
* **Agent adapters** — Claude Code, OpenAI Codex, Cursor and a generic adapter,
  all sharing the single policy file.
* **Unity Editor module (C#)** — project info, additive scene validation,
  read-only prefab validation, NUnit result import, menu items and a batchmode
  entry point with meaningful exit codes, plus EditMode tests.
* **Tests** — 139 unit/integration tests and six synthetic Unity fixtures
  (`valid_project`, `broken_meta`, `duplicate_guid`, `missing_reference`,
  `suspicious_scripts`, `malformed_project_settings`).
* **Benchmark** — synthetic benchmark with ground truth and
  precision/recall/F1/coverage metrics.
* **Documentation** — architecture, safety, commands, Unity integration, agent
  compatibility, troubleshooting, benchmark, installation.
* **CI** — GitHub Actions for tests, lint/compile checks and repository structure.

### Known limitations at release

* The Unity C# module was statically reviewed but **not compiled** — no Unity
  installation was available. Editor-side checks are reported as `SKIPPED`.
* The npm package is not published to the public registry; use the GitHub install
  form.
* Client-side automatic activation of the skill (Claude Code / Codex / Cursor) was
  not verified against live clients.

[1.0.0]: https://github.com/ssrinfree-hash/unity-sentinel/releases/tag/v1.0.0
