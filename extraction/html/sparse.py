"""Sparse-content detection.

A parse result is "sparse" when it contains almost no prose — typically a navigation
index or a page whose real content sits in a container the structure-aware pass missed.
:func:`is_sparse_content` measures non-heading prose (paragraphs, list items, table
cells, code) and compares it against :data:`SPARSE_CONTENT_CHAR_THRESHOLD`; the
orchestrator uses the verdict to decide whether to try richer extraction strategies.
"""
from __future__ import annotations

from extraction.heuristics import SPARSE_CONTENT_CHAR_THRESHOLD
from extraction.html.parser import DocumentationHTMLParser
from extraction.text_utils import squash_text


def is_sparse_content(parser: DocumentationHTMLParser) -> bool:
    """Return True when the parser captured less than the prose threshold.

    Headings are intentionally excluded — a page that is all headings and no body is
    still sparse and should trigger a fallback.
    """
    prose_parts: list[str] = []
    for block in parser.content_blocks:
        if block.get("type") == "heading":
            continue
        prose_parts.append(block.get("text", ""))
        prose_parts.extend(block.get("items") or [])
        for row in block.get("rows") or []:
            prose_parts.extend(row)
    for code_block in parser.code_blocks:
        prose_parts.append(code_block.get("text", ""))
    prose_text = squash_text(" ".join(prose_parts))
    return len(prose_text) < SPARSE_CONTENT_CHAR_THRESHOLD


__all__ = ["is_sparse_content"]
