## Summary

<!-- What does this PR change, and why? -->

## Type of change

- [ ] New check / capability
- [ ] Safety fix (apply / paths / revert)
- [ ] Bug fix
- [ ] Agent adapter or skill wording
- [ ] Documentation
- [ ] Refactor (no behaviour change)

## Verification

<!-- Commands you actually ran and their results. Do not claim checks you did not run. -->

```bash
python3 -m unittest discover -s tests -t .
python3 scripts/sentinel.py scan --project tests/fixtures/valid_project
python3 benchmark/run_benchmark.py
```

- [ ] Unit + integration tests pass locally
- [ ] New behaviour is covered by a test
- [ ] Benchmark ground truth updated (if a new finding code was added)
- [ ] `CHANGELOG.md` updated
- [ ] No secrets, tokens or absolute user paths added
- [ ] Documentation status labels (implemented / experimental / planned /
      unsupported) are accurate

## Risk and rollback

<!-- What can break? How is it reverted? -->

## Notes for reviewers

<!-- Anything subtle: path handling, symlinks, Unity API version, Windows specifics. -->
