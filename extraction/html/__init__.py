"""The structure-aware HTML extraction strategy.

Bundles the composed :class:`DocumentationHTMLParser` and the :func:`is_sparse_content`
predicate. The orchestrator in :mod:`extraction.document` drives these (normal parse →
``capture_all`` re-parse → trafilatura fallback).
"""
from __future__ import annotations

from extraction.html.parser import DocumentationHTMLParser
from extraction.html.sparse import is_sparse_content

__all__ = ["DocumentationHTMLParser", "is_sparse_content"]
