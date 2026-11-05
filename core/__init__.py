"""UNITY SENTINEL core package.

The core has no third-party dependencies and performs only file-based,
read-only analysis (writes are isolated in :mod:`core.safe_operations`).
"""

from .version import TOOL_NAME, TOOL_TAGLINE, TOOL_TITLE, __version__

__all__ = ["TOOL_NAME", "TOOL_TITLE", "TOOL_TAGLINE", "__version__"]
