#!/usr/bin/env python3
"""Shortcut for ``sentinel.py scan``.

Kept as a separate entry point so CI jobs and agent prompts can call a single
purpose script without remembering the sub-command name.

    python scripts/scan_project.py --project /path/to/UnityProject
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sentinel import main  # noqa: E402


def run(argv: list[str] | None = None) -> int:
    """Run ``sentinel.py scan`` with the provided arguments."""
    return main(["scan", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(run())
