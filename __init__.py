"""Documentation ingestion package.

Import strategy
---------------
The codebase is organized as flat top-level packages (``domain``, ``net``, ``llm``,
``extraction``, ``pipeline``, ``seeds``, ``adaptive`` …) that import one another by their
plain names (``from net import http_get``). For that to resolve no matter how the project
is launched — ``python cli.py``, ``python -m doc_ingestor.cli``, ``import adaptive`` from a
test, or ``import doc_ingestor`` from outside — this package idempotently puts its own
directory on ``sys.path`` *before* re-exporting anything. That single bootstrap replaces
the old ``try: from .x import … except ImportError: from x import …`` dance that used to
clutter every module.
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_PACKAGE_DIR = str(_Path(__file__).resolve().parent)
if _PACKAGE_DIR not in _sys.path:
    _sys.path.insert(0, _PACKAGE_DIR)

from cleaning import clean_record
from extraction import extract_from_html, extract_page
from pipeline import run_pipeline
from structuring import structure_records_to_markdown
from traversal import LinkTraversalFrontier

__all__ = [
    "LinkTraversalFrontier",
    "clean_record",
    "extract_from_html",
    "extract_page",
    "run_pipeline",
    "structure_records_to_markdown",
]
