# Contributing to UNITY SENTINEL

Thanks for helping. The project values **verifiable** improvements over large
untested ones.

## Ground rules

1. **No unverified claims.** A PR that says "detects all missing references" will
   be asked for the fixture and the test.
2. **No new runtime dependencies** for the Python core unless there is no
   standard-library alternative, and the reason is documented.
3. **Safety first.** Any change touching `core/safe_operations.py` or
   `core/paths.py` requires new tests for the failure case, not only the happy
   path.
4. **Unity semantics are not guessed.** If a check requires the Editor API, it
   belongs in `unity/Editor`, not in a regex.

## Development setup

```bash
git clone https://github.com/ssrinfree-hash/unity-sentinel.git
cd unity-sentinel

python3 --version            # 3.10+
python3 -m unittest discover -s tests -t .
python3 scripts/sentinel.py doctor
python3 scripts/sentinel.py scan --project tests/fixtures/valid_project
python3 benchmark/run_benchmark.py
node npm/test/smoke.test.js
```

## Adding a check

1. New module in `core/` returning `list[Finding]` with stable `code`s.
2. Register it in `core/pipeline.run_analysis` and add a `Check` entry.
3. Document the check in `README.md` (status table) and `docs/commands.md`.
4. Add a synthetic fixture (extend `tests/fixtures/_build_fixtures.py`).
5. Add unit tests plus a benchmark ground-truth entry.
6. Be explicit about confidence: deterministic → `high`, structural → `medium`,
   heuristic → `low`.

## Pull requests

* One logical change per PR; keep diffs small.
* Update `CHANGELOG.md` under "Unreleased".
* All tests must pass locally; CI runs the same commands.
* Describe **how you verified** the change (commands + output), not only what it
  does.
* New agent adapters: add `agents/<name>/{README,instructions}.md` and an entry in
  `npm/lib/agents.js`, and state the verification status honestly.

## Commit messages

Conventional style is appreciated:

```
feat(meta): detect duplicate GUIDs across folders
fix(apply): refuse writes when the backup already exists
docs(skill): clarify the NOT VERIFIED status
test(paths): cover symlink escape on POSIX
```

## Reporting bugs

Use the issue template. Include:

* `python3 scripts/sentinel.py doctor` output;
* the command you ran;
* `report.json` excerpt (redact paths and tokens);
* if relevant, a minimal fixture that reproduces the problem.

**Never paste real project code, credentials or tokens into an issue.**

## Code style

* Python: type hints, docstrings for public functions, `logging` instead of
  `print` inside `core/`.
* No bare `except:`; catch specific exceptions and justify broad ones.
* Language of code and identifiers: English. Commit messages and issues: any
  language is fine.
* C#: Editor-only, `[Unity Sentinel]` log prefix, no scene/prefab saving.
