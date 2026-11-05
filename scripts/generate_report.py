#!/usr/bin/env python3
"""Shortcut for ``sentinel.py report`` (JSON -> Markdown).

    python scripts/generate_report.py --input .sentinel/report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sentinel import main  # noqa: E402


def run(argv: list[str] | None = None) -> int:
    """Run ``sentinel.py report`` with the provided arguments."""
    return main(["report", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(run())
