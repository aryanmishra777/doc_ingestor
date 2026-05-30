"""The pipeline's default logger.

The crawl emits human-readable progress to stderr (stdout is reserved for piped Markdown
output). Every public pipeline function accepts an optional ``logger`` callback and falls
back to :func:`stderr_logger`, which keeps logging injectable for tests and embedders.
"""
from __future__ import annotations

import sys


def stderr_logger(message: str) -> None:
    """Write one progress line to stderr."""
    print(message, file=sys.stderr)


__all__ = ["stderr_logger"]
