#!/usr/bin/env python3
"""Synthetic benchmark harness.

The benchmark runs UNITY SENTINEL over a set of *artificial* Unity projects with
a known ground truth and reports precision, recall, F1, false positives, false
negatives, check coverage and runtime.

It is explicitly labelled as DEMO/SYNTHETIC DATA: the sample is small and must
not be presented as proof of superiority over other tools.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import load_config  # noqa: E402
from core.models import CheckResult, Finding, Status  # noqa: E402
from core.pipeline import build_scan_report  # noqa: E402
from core.version import __version__  # noqa: E402


def _load_ground_truth(bench_dir: Path) -> dict:
    path = bench_dir / "ground_truth" / "ground_truth.json"
    if not path.is_file():
        raise FileNotFoundError(f"Ground truth not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_benchmark(bench_dir: Path, out_dir: Path | None = None) -> dict:
    """Run every fixture, compare with ground truth and compute metrics."""
    started = time.monotonic()
    truth = _load_ground_truth(bench_dir)
    fixtures_root = (REPO_ROOT / truth.get("fixtures_dir", "tests/fixtures")).resolve()
    config = load_config()

    results: list[dict] = []
    tp = fp = fn = 0
    detected_total = 0
    expected_total = 0
    checks_executed = 0
    checks_total = 0

    for name, spec in sorted(truth["fixtures"].items()):
        project = fixtures_root / name
        expected = set(spec.get("expected", []))
        expected_total += len(expected)

        if not project.is_dir():
            results.append(
                {
                    "fixture": name,
                    "status": "NOT RUN",
                    "reason": "fixture project missing; run tests/fixtures/_build_fixtures.py",
                }
            )
            fn += len(expected)
            continue

        try:
            report, _scan = build_scan_report(project, config=config, mode="scan")
        except Exception as exc:  # noqa: BLE001 - benchmark must survive one bad fixture
            results.append({"fixture": name, "status": "ERROR", "reason": str(exc)})
            fn += len(expected)
            continue

        detected = {f.code for f in report.findings if f.code not in {"REF_TRUNCATED"}}
        detected_total += len(detected)
        matched = sorted(expected & detected)
        missed = sorted(expected - detected)
        spurious = sorted(detected - expected)

        tp += len(matched)
        fn += len(missed)
        fp += len(spurious)

        executed = [c for c in report.checks if c.result != CheckResult.SKIPPED]
        checks_executed += len(executed)
        checks_total += len(report.checks)

        results.append(
            {
                "fixture": name,
                "status": report.status.value,
                "expected": sorted(expected),
                "detected": sorted(detected),
                "true_positives": matched,
                "false_negatives": missed,
                "false_positives": spurious,
                "duration_ms": report.meta.duration_ms,
            }
        )

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    duration_ms = int((time.monotonic() - started) * 1000)

    payload = {
        "data_kind": "DEMO / SYNTHETIC DATA — artificial fixtures, small sample",
        "tool": "unity-sentinel",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "fixtures": len(truth["fixtures"]),
            "expected": expected_total,
            "detected": detected_total,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "checks_executed": checks_executed,
            "checks_total": checks_total,
            "checks_coverage": round(checks_executed / checks_total, 4) if checks_total else 0.0,
            "duration_ms": duration_ms,
        },
        "unity_editor_available": False,
        "notes": [
            "Synthetic fixtures only; no real or third-party Unity content is used.",
            "Performance findings are heuristics and are scored as detected findings here.",
            "Editor-only checks (scene/prefab reference validation, Unity tests) cannot run "
            "without a Unity installation and are therefore excluded from coverage.",
        ],
        "fixtures": results,
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / "benchmark_result.json"
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        payload["output_path"] = str(output_path)

    return payload


def main() -> int:
    """CLI entry point for the benchmark."""
    bench_dir = Path(__file__).resolve().parent
    result = run_benchmark(bench_dir, out_dir=bench_dir / "results")
    metrics = result["metrics"]
    print("UNITY SENTINEL — synthetic benchmark (DEMO DATA)")
    for key in ("expected", "detected", "true_positives", "false_positives", "false_negatives"):
        print(f"  {key:<17}{metrics[key]}")
    for key in ("precision", "recall", "f1", "checks_coverage"):
        print(f"  {key:<17}{metrics[key]:.3f}")
    print(f"  runtime          {metrics['duration_ms']} ms")
    if result.get("output_path"):
        print(f"  output           {result['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
