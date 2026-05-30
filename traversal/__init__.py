"""Crawl traversal: the BFS frontier and URL relevance rules.

Public API: :class:`LinkTraversalFrontier`. The module name is preserved so
``from traversal import LinkTraversalFrontier`` keeps working.
"""
from __future__ import annotations

from traversal.frontier import LinkTraversalFrontier

__all__ = ["LinkTraversalFrontier"]
