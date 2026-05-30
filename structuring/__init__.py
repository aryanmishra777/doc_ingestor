"""Rendering layer: turn cleaned records into NotebookLM-ready Markdown.

Public API: :func:`structure_records_to_markdown` (full document) and
:func:`derive_title` (document-title heuristic, also used by the chunk writer). The
implementation is split into :mod:`structuring.document` (document assembly) and
:mod:`structuring.blocks` (per-block renderers). The module name is kept as
``structuring`` for backward-compatible imports.
"""
from __future__ import annotations

from structuring.document import derive_title, structure_records_to_markdown

__all__ = ["structure_records_to_markdown", "derive_title"]
