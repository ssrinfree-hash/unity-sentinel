# Release readiness — v1.0.0

Acceptance criteria for the published release, with the evidence used to mark
each one. Statuses: **PASS**, **FAIL**, **NOT RUN**, **N/A**.

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Full `SKILL.md` present | PASS | `SKILL.md` (activation policy, 7 phases, scope limits) |
| 2 | Clear repository structure and documentation | PASS | `README.md`, `docs/` (8 guides), `python scripts/sentinel.py --help` |
| 3 | CLI starts and prints help | PASS | `python3 scripts/sentinel.py --help`; `--help` covered for every sub-command in `tests/test_cli.py::HelpTests` |
| 4 | Scan works on a synthetic Unity project | PASS | `python3 scripts/sentinel.py scan --project tests/fixtures/valid_project` → `Status: PASS`, 0 findings |
| 5 | Scan does not modify source files | PASS | `tests/test_project_scanner.py::test_scan_does_not_modify_the_project`, `tests/test_cli.py::test_scan_writes_nothing_into_the_project`, integration test |
| 6 | Generated-directory exclusions work | PASS | `tests/test_project_scanner.py::test_generated_directories_are_excluded` |
| 7 | Meta validator detects test violations | PASS | `tests/test_meta_validator.py` (missing, orphan, invalid, duplicate) |
| 8 | Reference analyzer reports its limitations | PASS | `core/reference_analyzer.py` `limitations`, `tests/test_reference_analyzer.py::test_limitations_are_declared` |
| 9 | Plan mode does not modify files | PASS | `tests/test_cli.py::PlanApplyCliTests`, `tests/integration/test_full_cycle.py` |
| 10 | Dry-run does not modify files | PASS | `tests/test_safe_operations.py::test_dry_run_never_writes` |
| 11 | Apply is protected from path traversal | PASS | `test_path_traversal_is_refused`, `test_absolute_path_is_refused`, `test_symlink_escape_is_refused` |
| 12 | Apply verifies the hash before writing | PASS | `test_hash_mismatch_is_refused`, `test_matching_hash_is_accepted` |
| 13 | Backup and journal are created | PASS | `test_apply_writes_backup_and_journal`, `test_revert_refuses_when_backup_missing` |
| 14 | Regression engine compares baseline and post-change | PASS | `tests/test_regression_engine.py`, `test_verify_flags_regressions` |
| 15 | JSON and Markdown reports are valid | PASS | `tests/test_report_generator.py`, integration test parses `report.json` and `verify.json` |
| 16 | Secrets do not reach reports | PASS | `test_evidence_is_redacted_in_report`, `test_reports_do_not_leak_secrets_or_absolute_paths` |
| 17 | Python unit tests pass | PASS | 140 tests, `python3 -m unittest discover -s tests -t .` → OK |
| 18 | Integration tests pass | PASS | `tests/integration/test_full_cycle.py` (3 tests, full cycle) |
| 19 | Unity Editor tests pass **if Unity is available** | NOT RUN | No Unity installation in the build environment. Tests exist in `unity/Tests/Editor/SentinelValidatorTests.cs`; C# was **not compiled**. Reported honestly in every report as `SKIPPED`. |
| 20 | Unity unavailability is reflected in reports | PASS | `unity.editor_checks` / `unity.tests` checks are `SKIPPED` with `requires: unity-editor`; CLI prints "Skipped checks"; benchmark reports `checks_coverage = 0.818` |
| 21 | Adapters for Codex, Claude Code and Cursor | PASS (structure) | `agents/*/README.md` + `instructions.md`, installed by `npm/lib/agents.js`; live client activation **NOT RUN** |
| 22 | Documentation contains no invented capabilities | PASS | capability table in `README.md` separates implemented / not supported; `docs/unity-integration.md` lists what was not compiled |
| 23 | GitHub Actions configured and green | PASS | `Tests` and `Lint and structure` workflows — run [#42130812020](https://github.com/ssrinfree-hash/unity-sentinel/actions/runs/42130812020): 8/8 jobs success on Linux, macOS and Windows |
| 24 | No empty modules pretending to be implemented | PASS | CI check "No empty placeholder modules"; `tests/unit` covers each core module |
| 25 | No unexplained changes to user files | PASS | Workspace contained only the downloaded specification; the repository was created in a new directory, scans are read-only, and all writes are journaled |

## Verification commands

```bash
python3 -m unittest discover -s tests -t .     # 140 tests OK
python3 scripts/sentinel.py scan --project tests/fixtures/valid_project   # PASS
python3 scripts/sentinel.py scan --project tests/fixtures/broken_meta     # exit 1
python3 benchmark/run_benchmark.py             # P=1.000 R=1.000 on 6 fixtures
node npm/test/smoke.test.js                    # 12/12 OK
npx github:ssrinfree-hash/unity-sentinel --version   # 1.0.0
```

## Known gaps (not release blockers)

1. **Unity compilation not executed.** The Editor module needs a first run inside
   a real Unity project; compile errors (if any) must be fixed there.
2. **npm package not published.** `npx unity-sentinel` resolves nothing on the
   public registry yet — the GitHub form is documented and tested:
   `npx github:ssrinfree-hash/unity-sentinel ...`. The name `unity-sentinel` is
   currently unclaimed (registry returns 404), so `npm publish` will make the short
   form work.
3. **Client activation unverified.** Skill auto-activation in Claude Code, Codex
   and Cursor was not tested against live clients.
4. **Benchmark sample is small** (6 fixtures, 14 known defects). Metrics are
   documented as synthetic demo data, not as a competitive claim.
