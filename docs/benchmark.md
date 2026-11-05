# Benchmark

The benchmark answers a narrow, honest question: *on a set of artificial Unity
projects with known defects, does UNITY SENTINEL detect the known defects without
inventing new ones?*

It does **not** prove superiority over any other tool, and it does not measure
detection on real projects.

## Run it

```bash
python3 benchmark/run_benchmark.py
npx unity-sentinel benchmark --json
```

Output: `benchmark/results/benchmark_result.json`.

## Data

* Fixtures: `tests/fixtures/*` — generated deterministically by
  `tests/fixtures/_build_fixtures.py`.
* Ground truth: `benchmark/ground_truth/ground_truth.json`.
* All fixtures are artificial; no third-party or commercial assets are used.

| Fixture | Known defects |
| --- | --- |
| `valid_project` | none (control case) |
| `broken_meta` | asset without `.meta`, orphan `.meta`, `.meta` without guid |
| `duplicate_guid` | two `.meta` files sharing one GUID |
| `missing_reference` | scene referencing an unknown GUID |
| `suspicious_scripts` | Find\*/GetComponent/string/LINQ in `Update`, synchronous I/O |
| `malformed_project_settings` | invalid `manifest.json`, unreadable `ProjectVersion.txt`, asmdef cycle, asmdefs without `.meta` |

## Metrics

| Metric | Definition |
| --- | --- |
| precision | true positives / (true positives + false positives) |
| recall | true positives / (true positives + false negatives) |
| F1 | harmonic mean of precision and recall |
| false positives | detected codes not present in ground truth |
| false negatives | expected codes not detected |
| checks coverage | executed checks / total checks |
| runtime | wall-clock time of the whole benchmark |

Scoring is per finding **code** per fixture, not per occurrence.

## Reference result (this repository, synthetic data)

```
fixtures            6
expected            14
detected            14
true positives      14
false positives      0
false negatives      0
precision        1.000
recall           1.000
f1               1.000
checks coverage  0.818
runtime           ~40 ms
```

**Read this correctly.** A 100 % score on six hand-made fixtures with 14 known
defects means the rules work on the cases they were written for. It says nothing
about recall on a 500k-line production project. The 0.818 coverage is the honest
part: the missing 18 % are the editor-side checks that require a Unity
installation.

## Comparing agents or versions

1. Run the benchmark with a fixed tool version:
   `git checkout <tag> && python3 benchmark/run_benchmark.py --out results/<tag>`.
2. Compare `benchmark_result.json` files field by field.
3. When comparing **agents**, keep the fixture set and the tool version identical;
   only the agent's decisions may differ.
4. Report sample size next to every metric. With 6 fixtures, one false negative
   moves recall by 7 percentage points.

## Adding a fixture

1. Extend `tests/fixtures/_build_fixtures.py` with a deterministic builder.
2. Add the expected codes to `ground_truth/ground_truth.json`.
3. Add unit tests for the new defect in `tests/`.
4. Re-run `python3 benchmark/run_benchmark.py` and update this document only with
   real numbers.
