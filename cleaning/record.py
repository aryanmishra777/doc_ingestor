"""The public cleaning entry point: :func:`clean_record`.

Sits between extraction and rendering. Given a freshly-extracted (and possibly messy)
:class:`DocPageRecord`, it returns a normalized deep copy: title and content blocks are
cleaned, code blocks are normalized in place, and — importantly — a record that ends up
with no content at all is annotated with an ``errors`` note rather than silently emitting
an empty section. The input record is never mutated.
"""
from __future__ import annotations

import copy

from domain.records import DocPageRecord
from cleaning.blocks import clean_content_blocks
from cleaning.text import clean_code, clean_prose


def clean_record(record: DocPageRecord) -> DocPageRecord:
    """Return a normalized deep copy of ``record``.

    The ``"cleaner: empty content after cleaning"`` note is appended when both content
    and code blocks are empty, so the rendering layer can surface an extraction note and
    downstream consumers can distinguish "fetched but empty" from "never fetched".
    """
    cleaned = copy.deepcopy(record)
    cleaned.setdefault("errors", [])
    cleaned["title"] = clean_prose(cleaned.get("title", ""))
    cleaned["content_blocks"] = clean_content_blocks(cleaned.get("content_blocks", []))
    cleaned["code_blocks"] = [
        {
            "language": clean_prose(code_block.get("language") or "") or None,
            "text": clean_code(code_block.get("text", "")),
        }
        for code_block in cleaned.get("code_blocks", [])
    ]

    if not cleaned["content_blocks"] and not cleaned["code_blocks"]:
        cleaned["errors"].append("cleaner: empty content after cleaning")

    return cleaned


__all__ = ["clean_record"]
