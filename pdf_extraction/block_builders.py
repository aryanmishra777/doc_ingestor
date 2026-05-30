"""Helpers that append typographically-classified blocks to a page's output.

Each function encapsulates one block-construction decision so the page walker stays
readable: monospace text → out-of-line code block (+ marker), large text → heading whose
level is chosen from the size ratio, everything else → a paragraph.
"""
from __future__ import annotations

from domain.records import CodeBlock, ContentBlock


def append_code_block(
    content: list[ContentBlock], code: list[CodeBlock], text: str, code_offset: int
) -> None:
    """Append a code block and a content marker pointing at its (offset) index."""
    idx = len(code) + code_offset
    code.append({"language": None, "text": text})
    content.append({
        "type": "code", "level": None, "text": "",
        "items": None, "rows": None, "code_block_index": idx,
    })


def append_heading_block(content: list[ContentBlock], text: str, ratio: float) -> None:
    """Append a heading whose level (1–4) is derived from its font-size ratio."""
    if ratio > 2.0:
        level = 1
    elif ratio > 1.6:
        level = 2
    elif ratio > 1.3:
        level = 3
    else:
        level = 4
    content.append({
        "type": "heading", "level": level, "text": text,
        "items": None, "rows": None, "code_block_index": None,
    })


def append_paragraph_block(content: list[ContentBlock], text: str) -> None:
    """Append a plain paragraph block."""
    content.append({
        "type": "paragraph", "level": None, "text": text,
        "items": None, "rows": None, "code_block_index": None,
    })


__all__ = ["append_code_block", "append_heading_block", "append_paragraph_block"]
