"""Cleaning and de-duplication of structured content blocks.

Operates on the ``content_blocks`` of a record after :mod:`cleaning.text` has normalized
the raw strings. Responsibilities:

* normalize each block's text/items/rows according to its ``type``;
* drop blocks that became empty after cleaning; and
* suppress repeated long paragraphs/lists (common when a page repeats a callout or a
  shared sidebar leaks into content), keyed on the cleaned text.

``code`` blocks pass through untouched here — their bodies are normalized separately as
out-of-line :class:`CodeBlock` entries on the record.
"""
from __future__ import annotations

import copy

from domain.records import ContentBlock
from cleaning.text import clean_prose

#: Minimum length before a paragraph/list is considered for duplicate suppression.
#: Short fragments (labels, "Note", etc.) legitimately repeat and are never dropped.
_DEDUP_MIN_LENGTH = 40


def clean_content_blocks(blocks: list[ContentBlock]) -> list[ContentBlock]:
    """Return a cleaned, de-duplicated copy of ``blocks`` (input is not mutated)."""
    cleaned_blocks: list[ContentBlock] = []
    seen_prose: set[tuple[str, str]] = set()

    for block in blocks:
        cleaned_block: ContentBlock = copy.deepcopy(block)
        block_type = cleaned_block.get("type")

        if block_type in {"heading", "paragraph"}:
            cleaned_block["text"] = clean_prose(cleaned_block.get("text", ""))
        elif block_type == "list":
            cleaned_block["items"] = [
                item
                for item in (clean_prose(item) for item in cleaned_block.get("items") or [])
                if item
            ]
            cleaned_block["text"] = clean_prose(cleaned_block.get("text", ""))
        elif block_type == "table":
            rows = cleaned_block.get("rows") or []
            cleaned_block["rows"] = [[clean_prose(cell) for cell in row] for row in rows]
            cleaned_block["text"] = clean_prose(cleaned_block.get("text", ""))
        elif block_type == "code":
            cleaned_blocks.append(cleaned_block)
            continue

        if not _has_content(cleaned_block):
            continue
        if _is_duplicate_prose(cleaned_block, seen_prose):
            continue

        cleaned_blocks.append(cleaned_block)

    return cleaned_blocks


def _is_duplicate_prose(block: ContentBlock, seen_prose: set[tuple[str, str]]) -> bool:
    """Track and detect repeated long paragraphs/lists; mutates ``seen_prose``."""
    block_type = block.get("type")
    if block_type == "paragraph":
        text = block.get("text", "")
        if len(text) < _DEDUP_MIN_LENGTH:
            return False
        key = ("paragraph", text)
    elif block_type == "list":
        items = block.get("items") or []
        text = "\n".join(items)
        if len(text) < _DEDUP_MIN_LENGTH:
            return False
        key = ("list", text)
    else:
        return False

    if key in seen_prose:
        return True
    seen_prose.add(key)
    return False


def _has_content(block: ContentBlock) -> bool:
    """Whether a block still carries renderable content after cleaning."""
    block_type = block.get("type")
    if block_type in {"heading", "paragraph"}:
        return bool(block.get("text"))
    if block_type == "list":
        return bool(block.get("items"))
    if block_type == "table":
        return any(any(row) for row in block.get("rows") or [])
    return True


__all__ = ["clean_content_blocks"]
